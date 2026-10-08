# Feature Specification: Change Impact & Test Case Advisor (MVP)

**Feature Branch**: `001-change-impact-test-advisor`

**Created**: 2026-10-08

**Status**: Draft

**Input**: User description: "Write the specification for the \"Change Impact & Test Case Advisor\" tool (MVP). Context: the project is C++ using CMake. It does not yet have compile_commands.json (we will enable CMAKE_EXPORT_COMPILE_COMMANDS=ON). Current tests use GoogleTest, and some tests run directly on devices. Developers cannot see the full blast radius of their changes and need to know which cases to check after modifying code. [R1-R8 functional requirements, NFRs, out-of-scope items, and MVP acceptance criteria as supplied by the user]"

## Clarifications

### Session 2026-10-08

- Q: When the LLM used for case description and risk classification (FR-011) is unavailable or
  errors during a run, what should the advisor do? → A: Degrade gracefully — still emit the full
  evidence-backed test case list, using rule-based risk classification and template-based
  descriptions derived from evidence, and mark the run as "degraded (LLM unavailable)" in its
  metrics output rather than failing the whole run.
- Q: What diff-size threshold triggers splitting the analysis by module/target (per constitution
  Principle V)? → A: Use the same ~50-file threshold already referenced as the MVP's target diff
  size in SC-001 — diffs at or below ~50 files are analyzed as a single unit; diffs exceeding ~50
  files are split and analyzed per affected CMake target/module.
- Q: What determines the priority assigned to each test case (FR-004)? → A: Deterministic rule:
  priority is derived from hop distance (direct outranks indirect) combined with risk group
  severity (ABI/layout, thread-safety, exception-safety, ownership/lifetime outrank logic and
  build-config) — never assigned freely by the LLM.
- Q: Who is responsible for providing the curated set of real regression bugs used to compute the
  missed-case rate in SC-005? → A: The team owning the pilot module (Honda remotecontrolapp)
  manually prepares a list of known regression bugs (e.g., from historical JIRA/Harmony tickets)
  before the MVP acceptance run; the advisor only consumes this list as comparison input and does
  not auto-retrieve it.
- Q: In explicit input mode (FR-001, part b), when a user specifies a target to analyze, what granularity
  should the advisor treat as "changed"? → A: Symbol-level only — a specific function/method or
  class, never a whole file. Whole-file granularity is explicitly rejected: the advisor MUST let
  the user name a function (or other symbol), and treats exactly that symbol (not its entire
  containing file) as the changed root node for impact traversal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get an Impact Map and Test Case List for a Change (Priority: P1)

A developer has modified one or more C++ files (or is about to, and wants to preview the effect of
a working-tree diff). They run the advisor against their change and receive, for each affected
area, a list of concrete test cases they should check before submitting — each case clearly tied
to the file/function/class that justifies it.

**Why this priority**: This is the core value proposition of the tool. Without this, there is no
product — everything else (classification detail, build-target mapping, uncertainty flags) is an
enrichment of this base capability. A developer who only gets this still gains the primary benefit:
knowing what to check instead of guessing.

**Independent Test**: Can be fully tested by pointing the tool at a commit range or working-tree
diff in the pilot module and verifying that a non-empty, evidence-backed test case list is produced
(or an empty list with a clear "no impact detected" result for a no-op change) — delivers
standalone value even if risk classification, CMake target mapping, and uncertainty flagging are
not yet present.

**Acceptance Scenarios**:

1. **Given** a git commit range or working-tree diff that changes a function's implementation,
   **When** the developer runs the advisor, **Then** the advisor returns a list of test cases, each
   referencing at least one concrete file or symbol affected by the change (direct, 1 hop) or
   reachable from it (indirect, up to the configured depth, default 2 hops).
2. **Given** a diff that touches only comments or formatting with no semantic effect on any
   indexed symbol, **When** the developer runs the advisor, **Then** the advisor reports zero test
   cases with an explicit "no detected impact" result rather than fabricating cases.
3. **Given** a list of explicit symbols (functions/methods or classes) provided instead of a git
   diff, **When** the developer runs the advisor, **Then** the advisor treats exactly those symbols
   (not their entire containing files) as the changed root nodes, and produces the same shape of
   impact map and test case list as it would for an equivalent diff.
4. **Given** the advisor has previously analyzed a commit and its cached index is still valid,
   **When** the developer re-runs the advisor on the same commit, **Then** the advisor reuses the
   cached index instead of rebuilding it from scratch.

---

### User Story 2 - Understand the Risk Category Behind Each Case (Priority: P2)

A developer or reviewer wants to understand *why* a given test case was suggested — whether the
change is a plain logic change, an ABI/layout change, an ownership/lifetime concern, a thread-safety
concern, an exception-safety concern, or a build-configuration-dependent change — so they can judge
how carefully to check it and who should review it.

**Why this priority**: Builds directly on User Story 1. The raw case list is useful on its own, but
pairing each case with a risk category is what lets a reviewer triage quickly (e.g., treat a
thread-safety flag with more caution than a comment-adjacent logic tweak).

**Independent Test**: Can be tested independently by feeding the advisor diffs that each represent
a single known risk category (e.g., a header member reorder for ABI/layout, a `noexcept` removal
for exception safety, a new `std::mutex` for thread safety) and verifying each resulting case is
tagged with the expected risk group.

**Acceptance Scenarios**:

1. **Given** a diff that changes a class member's type/order in a header, **When** the advisor
   analyzes it, **Then** at least one resulting case is tagged with the ABI/layout risk group and
   references the specific header and member.
2. **Given** a diff that introduces a `std::mutex`, atomic variable, or changes lock acquisition
   order, **When** the advisor analyzes it, **Then** at least one resulting case is tagged with the
   thread-safety risk group.
3. **Given** a diff that adds, removes, or changes a `noexcept` specifier or introduces a new
   `throw`, **When** the advisor analyzes it, **Then** at least one resulting case is tagged with
   the exception-safety risk group.
4. **Given** a diff gated by a macro whose expansion differs between build configurations (e.g.,
   Debug vs. Release), **When** the advisor analyzes it, **Then** at least one resulting case is
   tagged with the build-config risk group and names the affected configuration(s) if determinable.

---

### User Story 3 - Know Which Build Targets Are Affected (Priority: P2)

A developer wants to know which CMake targets are touched by their change, so they (or CI) know
the minimum build/test scope to rerun instead of rebuilding the entire project.

**Why this priority**: Equally valuable alongside risk classification — it answers the practical
"what do I rebuild/retest" question — but depends on the impact map from User Story 1 already
existing, so it is sequenced after it.

**Independent Test**: Can be tested independently by analyzing a diff touching files that belong
to two different CMake targets and verifying the advisor's output lists exactly those two targets
(no more, no fewer) as the build/test scope to rerun.

**Acceptance Scenarios**:

1. **Given** a diff touching files that belong to a single CMake target, **When** the advisor
   analyzes it, **Then** the output names that target as the build/test scope to rerun.
2. **Given** a diff touching files that belong to multiple CMake targets (e.g., a shared header
   consumed by two libraries), **When** the advisor analyzes it, **Then** the output lists every
   affected target, not just the target of the directly-edited file.

---

### User Story 4 - See Flagged Uncertain Areas Instead of Silence (Priority: P3)

A reviewer wants to be explicitly warned when the advisor's analysis hits a blind spot (dynamic
dependency, uninstantiated template, DI/config-driven routing, or a build-config-dependent macro it
could not fully resolve) rather than have that area quietly omitted from the results.

**Why this priority**: This is a safety-net enrichment on top of User Stories 1-3. It materially
increases trust in the tool but the tool already delivers value without it (an MVP that never hits
these blind spots in the pilot module would still be useful) — hence P3.

**Independent Test**: Can be tested independently by crafting a diff that changes a function used
only through a dependency-injected interface (or an uninstantiated template, or a dynamically
dispatched/config-driven call path) and verifying the advisor emits an explicit "uncertain / needs
manual review" entry naming the reason, instead of omitting that area from the report.

**Acceptance Scenarios**:

1. **Given** a diff that changes a template that has no current instantiations visible to the
   indexer, **When** the advisor analyzes it, **Then** the output includes an uncertainty entry
   stating the template is uninstantiated/unresolved, rather than omitting it silently.
2. **Given** a diff that changes a method only reachable through dependency injection or
   configuration-driven routing the indexer cannot statically resolve, **When** the advisor
   analyzes it, **Then** the output includes an uncertainty entry identifying the unresolved
   routing, rather than omitting it silently.

---

### Edge Cases

- What happens when `compile_commands.json` is missing or stale for the analyzed module? The
  advisor MUST report this clearly as a blocking prerequisite issue, not silently fall back to a
  lower-fidelity heuristic and present results as if they were fully resolved.
- What happens when the diff touches zero symbols the indexer tracks (e.g., pure comment,
  whitespace, or non-C++ file changes)? The advisor MUST report "no detected impact" rather than
  an empty result indistinguishable from a tool failure.
- How does the tool behave on a cold start (no prior cached index exists for the repository or
  module)? It MUST build the index from scratch once, cache it, and report the one-time cost
  separately from steady-state incremental run time.
- What happens when a diff spans files belonging to modules/targets outside the designated pilot
  scope? The advisor MUST still report impact within the targets it can resolve and explicitly flag
  any out-of-scope targets it skipped, rather than silently ignoring them.
- What happens when a previously-cached evidence file/symbol referenced by the index has since
  been deleted or renamed? The advisor MUST detect the stale reference, invalidate that part of the
  cache, and avoid emitting a case whose evidence no longer resolves.
- How does the tool handle a change to a macro whose effect depends on a build configuration that
  was not present in the available `compile_commands.json` entries (e.g., only Release was
  configured)? The advisor MUST flag this as an uncertainty rather than assume the missing
  configuration behaves identically.
- What happens when a test case's only available verification is a device-only GoogleTest case
  (per project context, some tests run directly on devices)? The advisor MUST still include it in
  the test case list (since running it is a separate, out-of-scope manual/CI step) and MUST NOT
  attempt to execute it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The advisor MUST accept either (a) a git diff expressed as a commit range or the
  current working-tree changes, or (b) an explicit list of symbols (functions/methods or classes),
  as the input describing "the change" to analyze.
- **FR-001a**: In explicit input mode (FR-001, part b), each entry in the list MUST identify a specific
  symbol (function/method or class) to be treated as the changed root node for impact traversal.
  Whole-file-level granularity (treating an entire file as "changed") MUST NOT be used as the unit
  of input in this mode; a file path alone, without a symbol, is not an acceptable entry.
- **FR-002**: The advisor MUST produce an impact map of affected files, classes, and functions,
  grouped into **direct** impacts (1 hop from the changed node) and **indirect** impacts (reachable
  within a configurable hop depth, default 2), where each impact entry states the graph relation
  that justifies it: call, inherit/override, include, instantiate, or link-to-target.
- **FR-003**: The advisor MUST classify each detected change into one or more risk groups: logic,
  ABI/layout (header change, member change, signature change, inline change), ownership/lifetime
  (raw pointer, reference, move semantics), thread safety (mutex, atomic, lock order), exception
  safety (`noexcept`, `throw`), and build config (macro, target, debug/release).
- **FR-004**: For each risk group triggered by a change, the advisor MUST generate one or more test
  case entries, each containing: a unique id, a human-readable description, an activation condition
  (why/when this case applies to the current diff), the related node/file it traces to, a priority,
  and the risk group it belongs to.
- **FR-004a**: Test case priority MUST be derived deterministically from two signals: (1) hop
  distance from the change (direct impacts outrank indirect impacts), and (2) risk group severity
  (ABI/layout, thread-safety, exception-safety, and ownership/lifetime outrank logic and
  build-config). Priority MUST NOT be assigned freely by the language model.
- **FR-005**: The advisor MUST map every affected file to its owning CMake target(s) so that the
  minimum build/test scope to rerun is known and reportable.
- **FR-006**: Every emitted test case MUST reference at least one concrete file or symbol as
  evidence; the advisor MUST NOT emit a case that fails this evidence check.
- **FR-007**: The advisor MUST explicitly flag uncertain analysis areas — dynamic/runtime
  dependencies, uninstantiated templates, and dependency-injection or configuration-driven routing
  it cannot statically resolve — with a stated reason, and MUST NOT silently omit them from the
  report.
- **FR-008**: The advisor MUST produce two output artifacts from the same analysis: a
  human-readable Markdown report suitable for manual review, and a structured JSON document
  carrying the same impact map, classifications, test cases, target mapping, and uncertainty flags
  for future tool integration.
- **FR-009**: The advisor MUST run entirely on the local machine and MUST NOT transmit source code,
  diffs, or derived identifiers to any external service without explicit, documented team approval.
- **FR-010**: The advisor MUST cache its dependency index and prior analysis results keyed per
  commit, and on a subsequent run MUST re-analyze only the parts of the graph affected by the new
  change rather than rebuilding the full index, except on a cold start (no cache present) or when
  the cache is detected to be invalid.
- **FR-010a**: When a Change Input spans more than ~50 files (the same threshold referenced in
  SC-001), the advisor MUST split the analysis by CMake target/module and process each
  module-scoped slice as a separate analysis unit rather than analyzing the entire diff as one
  unbounded unit, per the constitution's cost-aware incremental analysis principle.
- **FR-011**: All dependency tracing (impact map construction, call/inherit/include/instantiate/
  link-to-target relations) MUST be performed by deterministic tooling (source parser, dependency/
  call graph, CMake target metadata, `compile_commands.json`); use of a language model, if any, MUST
  be restricted to writing the human-readable description of an already-identified case and
  assigning/refining its risk classification, and MUST operate only over the pre-filtered node set
  for the current diff — never the full codebase.
- **FR-012**: If a language model is used in a run, the advisor MUST record and report the token
  usage for that run as part of the run's metrics output.
- **FR-012a**: If the language model used for case description and risk classification is
  unavailable or errors during a run, the advisor MUST degrade gracefully: it MUST still emit the
  full evidence-backed test case list using a rule-based fallback for risk classification (derived
  directly from the deterministic change-classification signals in FR-003) and a template-based
  description derived from the case's evidence, and MUST mark the run's metrics output as
  "degraded (LLM unavailable)" rather than failing the run.
- **FR-013**: The advisor MUST verify that a valid, current `compile_commands.json` (or equivalent
  compile database) is available for the module being analyzed before producing results, and MUST
  report a clear, actionable error (naming the missing/stale module) instead of proceeding with
  degraded, unflagged accuracy when it is missing or stale.
- **FR-014**: The advisor MUST NOT generate test code, test scaffolding, or fixtures for any test
  framework, MUST NOT depend on or require GoogleTest (or any other specific test framework) to
  function, MUST NOT execute tests on any device or build target, and MUST NOT modify any source
  file in the analyzed repository.
- **FR-015**: Flow-driven analysis (tracing impact starting from application entry points rather
  than from the changed nodes) and automatic test skeleton generation are explicitly out of scope
  for this MVP and MUST NOT be implemented as part of it.
- **FR-016**: The MVP MUST be validated against the designated pilot module: the
  `remotecontrolapp` repository at `D:\Honda\sourceCode\honda_con_release\remotecontrolapp`
  (CMake-based unit test build under `unittests/CMakeLists.txt`, using GoogleTest). Within this
  repository, the pilot CMake target is **`RemoteDoorLock`** (with `RemoteDoorUnlock` as the
  natural secondary/companion target, since both are small, closely related feature targets with
  existing GoogleTest coverage and a documented requirement set
  `TSU_ECU_Requirements_Remote_Door_Lock_Unlock.xlsx`). `CMAKE_EXPORT_COMPILE_COMMANDS=ON` MUST be
  enabled for this target before the MVP acceptance run (per Assumptions).

### Key Entities

- **Change Input**: The unit of analysis submitted to the advisor — either a git commit range,
  working-tree diff, or an explicit file/symbol list. Carries enough information to resolve to
  concrete changed source locations.
- **Impact Node**: A file, class, or function identified by the dependency graph as directly or
  indirectly affected by the Change Input. Carries a hop distance (direct = 1, indirect ≤ configured
  depth) and the relation(s) that connect it to the change.
- **Impact Edge / Reason**: The specific graph relation (call, inherit/override, include,
  instantiate, link-to-target) that justifies why an Impact Node is considered affected.
- **Risk Classification**: One or more risk groups (logic, ABI/layout, ownership/lifetime, thread
  safety, exception safety, build config) assigned to a change, each with its specific sub-reason
  (e.g., "member reorder" under ABI/layout).
- **Test Case Candidate**: A single recommended item to check, with id, description, activation
  condition, related node/file (evidence), priority, and risk group. The fundamental output unit of
  the tool.
- **CMake Target Mapping**: The association between an affected file and the CMake target(s) that
  compile/link it, used to report the minimum build/test scope to rerun.
- **Uncertainty Flag**: An explicitly reported blind spot (dynamic dependency, uninstantiated
  template, DI/config-driven routing, build-config-incomplete macro) with a stated reason, kept
  distinct from confirmed Test Case Candidates.
- **Analysis Run**: One execution of the advisor against a Change Input, carrying metrics such as
  run time, cache-hit status, and (if applicable) language-model token usage.
- **Cached Dependency Index**: The persisted, per-commit-keyed representation of the dependency/
  call graph and CMake target metadata that allows incremental re-analysis instead of full rebuilds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a change touching up to ~50 files in the pilot module, a developer receives a
  complete impact map and test case list within a time budget acceptable for routine pre-submit use
  (target: under 10 minutes end-to-end on a warm/cached index).
- **SC-002**: 100% of test cases presented to a reviewer include at least one concrete file/symbol
  reference that the reviewer can locate and verify in under 30 seconds, with zero cases presented
  without such a reference.
- **SC-003**: Re-running the advisor against a commit that was already analyzed (no new changes)
  completes using the cached index, without a full dependency re-index.
- **SC-004**: For every known blind-spot category encountered in the pilot module's analyzed
  diffs (dynamic dependency, uninstantiated template, DI/config-driven routing, build-config
  macro), 100% are surfaced as an explicit flag — zero are silently absent from the report.
- **SC-005**: When compared against a curated set of real regression bugs previously found in the
  pilot module, the advisor's missed-case rate (regressions whose impacted area was not surfaced by
  any emitted test case) is measured and recorded for the MVP baseline, establishing the number to
  drive future improvement — the tool is considered successful for the MVP if this baseline is
  captured and no known pilot-module regression area is silently omitted from the uncertainty-flag
  mechanism either. The curated regression bug list is prepared manually by the team owning the
  pilot module (e.g., sourced from historical JIRA/Harmony tickets for `remotecontrolapp`) prior to
  the MVP acceptance run; the advisor consumes this list as comparison input and is not responsible
  for retrieving or generating it.
- **SC-006**: Zero instances of source code, diff content, or derived file/symbol identifiers being
  transmitted off the local machine occur during any analysis run, unless a run is explicitly
  configured with team-approved external access.

## Assumptions

- **Pilot module confirmed**: `remotecontrolapp`
  (`D:\Honda\sourceCode\honda_con_release\remotecontrolapp`), CMake target `RemoteDoorLock`
  (companion target `RemoteDoorUnlock`), built via `unittests/CMakeLists.txt` with GoogleTest. This
  repository does not yet have `compile_commands.json` generated; the team will enable
  `CMAKE_EXPORT_COMPILE_COMMANDS=ON` on this CMake configuration before the MVP acceptance run. The
  advisor treats a missing/stale compile database as a hard prerequisite failure rather than
  attempting a degraded fallback (FR-013).
- The default indirect-impact traversal depth is 2 hops, matching the value explicitly supplied in
  the input requirements; this is configurable but 2 is the MVP default.
- The 10-minute time budget in SC-001 is a reasonable default for a ~50-file diff on a warm cache,
  chosen to fit routine pre-submit/CI workflows; it is not a hard contractual SLA and may be
  revisited once real measurements from the pilot module are available.
- Device-only GoogleTest cases are still included in the advisor's output list (as a case to
  check), since the out-of-scope boundary excludes the advisor *executing* tests on devices, not
  recommending that a human/CI run them.
- The specific LLM provider/endpoint used for case description and risk-classification text (per
  FR-011/FR-012) is a technical decision deferred to the implementation plan; the constitution's
  local-first/no-external-transmission-without-approval principle governs whichever endpoint is
  chosen.
- The exact file formats/schemas for the explicit symbol-list input mode (FR-001a) and for
  the structured JSON output (FR-008) are deferred to the implementation plan/contracts; this spec
  only fixes their required content (symbol-level granularity; no whole-file entries), not their
  byte-level shape.
- "Logic" changes (per FR-003) are treated as the default/fallback risk group for any change that
  does not match one of the other five specific categories, ensuring every detected change receives
  at least one risk classification.
