<!--
Sync Impact Report
===================
Version change: (unratified template) → 1.0.0
Rationale: Initial ratification of the project constitution. No prior concrete
version existed (file contained only unfilled template placeholders), so this
is treated as the founding adoption (MAJOR bump to 1.0.0 per "initial
adoption" convention).

Modified principles: N/A (initial adoption — all 9 principles newly defined)

Principles established:
  1. Test-Case-List-Only Output (NON-NEGOTIABLE)
  2. Evidence-Backed Traceability (NON-NEGOTIABLE)
  3. Deterministic-First Analysis, Bounded LLM Role (NON-NEGOTIABLE)
  4. Explicit Uncertainty Flagging (NON-NEGOTIABLE)
  5. Cost-Aware Incremental Analysis
  6. Local-First Execution & Data Privacy (NON-NEGOTIABLE)
  7. Recall Over Volume (Missed-Regression Priority)
  8. Fixed Scope — No Code Mutation, No Test Execution, No Test Authoring (NON-NEGOTIABLE)
  9. English-Only Documentation & Output

Added sections:
  - Core Principles (9 principles, mapped 1:1 to the user-supplied binding principles)
  - Technology & Tooling Constraints (Section 2)
  - Analysis Workflow & Quality Gates (Section 3)
  - Governance

Removed sections: None (template placeholders only; no prior concrete content existed)

Templates requiring follow-up review (not modified by this command — read constitution at runtime):
  - .specify/templates/plan-template.md ⚠ pending manual review for alignment with
    Principles 3/4/5 (deterministic-tool-first pipeline, uncertainty flags, caching)
  - .specify/templates/spec-template.md ⚠ pending manual review for alignment with
    Principle 1/2 (output shape = test-case list with evidence fields)
  - .specify/templates/tasks-template.md ⚠ pending manual review for alignment with
    Principle 5 (incremental/cached analysis tasks) and Principle 8 (scope fence)
  - .specify/templates/checklist-template.md ⚠ pending manual review
  - .github/skills/speckit-plan/SKILL.md, speckit-tasks/SKILL.md, speckit-analyze/SKILL.md
    ⚠ no changes made (out of scope for this command); recommend a follow-up
    `/speckit-analyze` pass once a spec/plan exist for this feature.

Follow-up TODOs: None — all placeholders resolved. Ratification date set to the
date this constitution was first adopted (today), since no earlier adoption date
exists.
-->

# Change Impact & Test Case Advisor Constitution

## Core Principles

### I. Test-Case-List-Only Output (NON-NEGOTIABLE)
The tool's only deliverable is a **list of test cases to check**, where each entry contains:
a description, an activation condition (when/why this case becomes relevant for the current
diff), and supporting evidence (see Principle II). The tool MUST NOT generate test code, test
scaffolding, or fixtures, and MUST NOT depend on or assume any specific test framework (GoogleTest,
Catch2, CTest, etc.). Output format and structure may evolve, but the semantic contract — "a list
of cases to check, not code" — is fixed and MUST be preserved by every feature built on this tool.
Rationale: the tool's value is in directing human/CI attention to the right regression risk areas;
generating test code would couple the tool to a framework, inflate scope, and shift responsibility
for correctness onto generated code no one asked for.

### II. Evidence-Backed Traceability (NON-NEGOTIABLE)
Every emitted test case MUST trace back to at least one concrete file path or symbol
(function/class/target) in the codebase that is actually impacted by the analyzed change. A case
that cannot be tied to such evidence MUST NOT be emitted — not with a disclaimer, not as a "best
guess." Evidence fields must be concrete and checkable (e.g., file path + symbol name + the
dependency edge or call path that justifies inclusion), not vague prose. Rationale: untraceable
suggestions erode trust faster than an incomplete list; a reviewer must be able to verify in
seconds why a case was proposed.

### III. Deterministic-First Analysis, Bounded LLM Role (NON-NEGOTIABLE)
Dependency tracing is performed exclusively by deterministic tooling: source parsers, the
dependency/call graph, and build-system metadata (CMake targets, `compile_commands.json`). The LLM
MAY be used only after this deterministic pass has already filtered the candidate node set, and
only for two tasks: (a) writing a human-readable description of a case, and (b) classifying its
risk level. The LLM MUST NOT be used to discover dependencies, decide inclusion/exclusion, or
invent evidence. The full codebase MUST NEVER be loaded into the LLM context — only the
already-filtered, bounded set of nodes relevant to the current diff. Rationale: determinism keeps
the tool auditable, reproducible, and cheap; an LLM given free rein over the whole repo would be
slow, expensive, non-reproducible, and prone to fabricating evidence.

### IV. Explicit Uncertainty Flagging (NON-NEGOTIABLE)
Analysis blind spots — uninstantiated templates, dynamic/runtime dependencies, dependency
injection or configuration-driven routing, and macros whose expansion depends on build
configuration — MUST be explicitly flagged in the output as "uncertain / needs manual review."
They MUST NEVER be silently dropped from consideration. A flagged-uncertain item is an acceptable
output; a silently-omitted one is a constitution violation. Rationale: silent drops create false
confidence ("the tool said nothing, so it must be fine") which is more dangerous than an admitted
gap.

### V. Cost-Aware Incremental Analysis
Cost is a first-class design constraint, not an afterthought. The tool MUST: cache the dependency
index and prior analysis results keyed per commit; re-analyze only the parts of the graph affected
by the current change (no full-repo re-index on every run unless the cache is invalid or absent);
and split large diffs by module/target so that any single analysis unit stays within a bounded,
predictable size and runtime. Rationale: without these constraints, analysis cost grows with
repository size and diff size without bound, making the tool impractical for CI or large
monorepos.

### VI. Local-First Execution & Data Privacy (NON-NEGOTIABLE)
The tool runs locally by default. Source code, symbols, or diffs MUST NOT be sent to any external
service (including third-party LLM APIs) without explicit, prior approval from the team. Any
feature that would transmit code or derived artifacts off-machine MUST be opt-in, clearly
documented, and gated behind an explicit configuration flag — never a silent default. Rationale:
automotive/embedded C++ codebases are frequently under strict confidentiality and export-control
constraints; local-first is the safe default and external transmission is the exception requiring
sign-off.

### VII. Recall Over Volume (Missed-Regression Priority)
Completeness and accuracy of the case list take priority over the raw number of cases produced. A
shorter list that correctly flags the areas a real regression would have hit is strictly better
than a longer list padded with low-value or speculative entries. The tool's primary success
metric is the **miss rate** — the fraction of real regression bugs whose impacted area was not
surfaced by the tool — and this metric MUST be the one optimized when tuning heuristics, risk
classification, or filtering thresholds. Precision/noise reduction is a secondary concern that
MUST NOT be pursued at the expense of recall. Rationale: a missed regression that reaches
production is far costlier than a reviewer skimming a few extra, lower-value suggestions.

### VIII. Fixed Scope — No Code Mutation, No Device Test Execution, No Test Authoring (NON-NEGOTIABLE)
The tool's scope is fixed to: analyzing change impact and recommending test cases to check. It
MUST NOT modify application source code, MUST NOT run or orchestrate tests on devices/targets, and
MUST NOT author test code. Any proposed feature that falls outside this scope (e.g., auto-fixing
code, triggering CI test runs, generating test stubs) MUST be proposed separately and explicitly
approved before any implementation work begins — it MUST NOT be bundled into or silently added
under this project. Rationale: scope creep from "helpful" adjacent features is how focused
analysis tools turn into unreliable, unmaintainable do-everything systems; a hard scope fence keeps
the tool trustworthy and reviewable.

### IX. English-Only Documentation & Output
All documentation (specs, plans, READMEs, in-tool help) and all tool output presented to users
(case descriptions, risk labels, evidence annotations, CLI/log messages) MUST be written in
English. This applies regardless of the language of the source code being analyzed. Rationale: a
single documentation/output language keeps the tool consistent and reviewable across a mixed-team,
multi-repo environment.

## Technology & Tooling Constraints

- **Target codebases**: C++ and CMake-based projects. The dependency/build model MUST be derived
  from CMake target metadata and `compile_commands.json` (or an equivalent deterministic compile
  database) — never guessed from file naming conventions or directory structure alone.
- **No test-framework coupling**: the tool's analysis and output layers MUST NOT import, assume,
  or require any specific test framework (GoogleTest, Catch2, CTest, doctest, etc.). Framework
  adapters, if ever added, are a separate, explicitly-approved concern (see Principle VIII) and
  MUST remain optional/pluggable, never a hard dependency of the core analyzer.
- **Caching**: the on-disk index/result cache MUST be keyed by commit (or equivalent content hash)
  so that re-running on an unchanged commit is a cache hit, and changed files invalidate only the
  affected subgraph of the cache — not the entire cache.
- **LLM usage boundary**: any LLM integration MUST operate strictly on the pre-filtered node set
  produced by the deterministic pipeline (Principle III) and MUST run through a local or
  explicitly team-approved endpoint (Principle VI). Prompts and context sent to the LLM MUST be
  logged or reproducible so a reviewer can audit exactly what the LLM saw.
- **Uncertainty taxonomy**: the categories listed in Principle IV (uninstantiated templates,
  dynamic/runtime dependencies, DI/config-driven routing, build-config-dependent macros) are the
  minimum required set of blind spots the tool must detect and flag; this list may only grow, not
  shrink, without a constitution amendment.

## Analysis Workflow & Quality Gates

- **Pipeline order is fixed**: deterministic parse/graph-build → deterministic diff-to-node
  impact filtering → (optional) LLM description/risk classification over the filtered set →
  evidence-validated output assembly. Steps MUST NOT be reordered such that the LLM participates
  before deterministic filtering has bounded its input.
- **Evidence gate**: before any case is emitted, it MUST pass an automated check that at least one
  concrete file/symbol reference resolves against the current index. Cases failing this check are
  dropped from the "confirmed" list and, if they stem from one of the Principle IV categories,
  routed to the "uncertain / needs manual review" list instead — never dropped silently.
  ⚠ If a candidate fails evidence resolution for a reason outside the Principle IV taxonomy, the
  implementation MUST treat this as a bug to fix (tighten the taxonomy or the resolver), not as a
  license to drop the case.
- **Incrementality check**: any change to the analyzer MUST preserve (or improve) cache-hit
  behavior on re-runs against an unchanged commit, and MUST preserve module-splitting behavior on
  large diffs (Principle V). A change that forces full-repo re-analysis on every run is a
  regression against this constitution and MUST be rejected in review.
- **Scope review**: any pull request or proposal touching this tool MUST be checked against
  Principle VIII before merge. If it adds code mutation, device test execution, or test
  authoring/generation capability, it MUST be rejected or split out into a separately-approved
  proposal.
- **Recall tracking**: when real regression bugs are found in the field or in CI that a change
  impact analysis should have flagged, the miss MUST be recorded and used to improve the
  deterministic graph/heuristics (Principle VII) — not patched over with LLM prompt tweaks alone.

## Governance

This constitution supersedes any conflicting practice, template default, or prior informal
convention used in this project. All specs, plans, and tasks produced via Spec Kit commands for
this project MUST be checked for compliance with the 9 Core Principles above before being marked
ready for implementation.

**Amendment procedure**: amendments are proposed by editing this file (or via the
`/speckit-constitution` command), MUST include an updated Sync Impact Report, and MUST state which
principle(s) are added, removed, or redefined and why. Removing or materially weakening a
NON-NEGOTIABLE principle (I, II, III, IV, VI, VIII) requires explicit team sign-off recorded in the
amendment's rationale, in addition to the version bump.

**Versioning policy**: semantic versioning applies to this document —
MAJOR for backward-incompatible governance changes (removing/redefining a principle),
MINOR for adding a new principle or materially expanding existing guidance,
PATCH for clarifications and non-semantic wording fixes.

**Compliance review**: every `/speckit-plan` and `/speckit-analyze` pass for this project MUST
include an explicit check that the planned output remains a test-case list with evidence
(Principles I–II), that the LLM role stays bounded (Principle III), that uncertainty is flagged
rather than dropped (Principle IV), and that scope stays fixed (Principle VIII). Violations found
during review block progression to implementation until resolved or the constitution is amended.

**Version**: 1.0.0 | **Ratified**: 2026-10-08 | **Last Amended**: 2026-10-08
