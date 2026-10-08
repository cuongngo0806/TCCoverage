# Phase 0 Research: Change Impact & Test Case Advisor (MVP)

**Input**: Technical Context unknowns from [plan.md](./plan.md), resolved against the feature
spec ([spec.md](./spec.md)) and the project constitution.

All items below were implicit technical decisions needed to execute the plan; none were left as
`NEEDS CLARIFICATION` in the Technical Context, but each decision is recorded here with rationale
and rejected alternatives so the design is auditable, per the constitution's emphasis on
determinism and reproducibility (Principle III).

## 1. C++ Parsing Approach

**Decision**: Use `libclang` via its official Python bindings (`clang.cindex`), driven entirely by
the project's `compile_commands.json`.

**Rationale**: libclang is the same frontend used by clangd/clang-tidy, so its AST reflects the
*actual* compiled semantics (template instantiation, overload resolution, macro expansion) rather
than a textual approximation — directly required by the constitution's "deterministic tooling"
mandate (Principle III) and by FR-011. It is local, free, has mature Python bindings, and is
already battle-tested on embedded/automotive C++ codebases (it is the engine behind most modern
C++ IDE tooling).

**Alternatives considered**:
- **tree-sitter (C++ grammar)**: Faster and more tolerant of broken builds, but it is a *syntactic*
  parser with no semantic resolution — it cannot reliably resolve overloads, template
  instantiations, or `#include` macro expansion, which the spec requires as impact-edge evidence
  (FR-002: call, inherit/override, instantiate relations). Rejected: insufficient semantic fidelity
  for evidence-backed traceability (Principle II).
- **Custom regex/text-based scanner**: Fastest to build, zero dependencies, but fundamentally
  unable to satisfy FR-006 (evidence-backed cases) for anything beyond trivial textual matches;
  would silently misclassify templates/macros, which Principle IV explicitly requires flagging
  rather than guessing. Rejected.
- **cppcheck's internal AST / other static analyzers**: Possible, but not designed as an embeddable
  library for custom graph construction; would require wrapping its CLI output, losing granularity
  (e.g., individual call-site resolution) needed for FR-002. Rejected for this MVP.

## 2. CMake Target-to-File Mapping

**Decision**: Use the CMake **File API** (`cmake-file-api(7)`), specifically the `codemodel-v2`
query, generated alongside `compile_commands.json` by configuring with
`-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` and requesting the File API query files before running
`cmake --build`/`cmake` configure step.

**Rationale**: `compile_commands.json` lists compiler invocations per translation unit but does
not explicitly name the CMake *target* that owns each file (a file can appear in that JSON without
a direct, named link back to a target when target names are ambiguous, e.g. object libraries).
File API's codemodel gives a precise, versioned, machine-readable target→source-file association
directly from CMake itself — required for FR-005's "map every affected file to its owning CMake
target(s)" without heuristic guessing.

**Alternatives considered**:
- **Parsing `CMakeLists.txt` text directly**: Fragile against `if()`/macro-driven target
  definitions (the pilot module's own `unittests/CMakeLists.txt` uses `IF(EXISTS ...)` branches and
  a `SET(ALL_TARGET ...)` list pattern) — would require re-implementing a chunk of CMake's own
  evaluation logic. Rejected: high maintenance cost, poor determinism guarantee.
- **Inferring target from `compile_commands.json` directory conventions**: Works only when source
  layout conventions are consistent repo-wide; the pilot module mixes MY23/MY25.5 sysroot paths and
  shared `src/` directories across multiple targets (`ALL_TARGET` list), making directory-based
  inference unreliable. Rejected.

## 3. Dependency / Impact Cache Storage

**Decision**: SQLite (Python's built-in `sqlite3` module), one local `.sqlite3` file per analyzed
module, with tables for `symbols`, `edges` (call/inherit/include/instantiate/link-to-target),
`file_hashes` (content hash per tracked file), and `analysis_runs` (commit hash, timestamp, cache
hit/miss, LLM token usage, degraded flag).

**Rationale**: Needs to satisfy FR-010/FR-010a (per-commit, per-file incremental caching) and the
constitution's Cost-Aware Incremental Analysis principle (V) with zero external infra (no
server process, no separate DB install) — consistent with Local-First Execution (Principle VI).
SQLite's per-row content-hash keys make partial invalidation (only changed files' subgraph) simple
to implement correctly, satisfying the Technology & Tooling Constraints section's caching
requirement ("changed files invalidate only the affected subgraph of the cache — not the entire
cache").

**Alternatives considered**:
- **Flat JSON/pickle cache files**: Simpler to start, but partial invalidation (only the changed
  subgraph) becomes a manual, error-prone diffing exercise; full-file rewrites on every update
  risk accidental full-cache invalidation, which the constitution explicitly calls out as a
  regression. Rejected.
- **Embedded graph database (e.g., Kuzu, a local graph DB)**: More natural for graph queries, but
  adds a heavier, less-ubiquitous dependency for marginal benefit at this MVP's scale (two small
  CMake targets); reconsider only if/when the tool scales to large monorepos in a later phase.
  Rejected for MVP; noted as a future optimization if traversal performance becomes a bottleneck.

## 4. LLM Integration Boundary & Fallback

**Decision**: LLM usage is implemented as a pluggable, **disabled-by-default** step. When enabled,
it defaults to a local endpoint (e.g., Ollama running on localhost); any external/cloud endpoint
requires an explicit, separately-documented configuration flag and team approval record (Principle
VI). The LLM receives only: (a) the already-classified risk group, (b) the specific evidence
(file/symbol/line), and (c) the deterministic relation/reason string — never raw surrounding
source beyond the minimal evidence window, and never the full file or repository. When disabled or
erroring, a deterministic template renderer produces the description text directly from the same
evidence fields (FR-012a).

**Rationale**: Directly implements Principle III (bounded LLM role: description + risk-label
refinement only, over a pre-filtered set) and Principle VI (local-first, explicit approval for
external transmission). The rule-based template fallback guarantees FR-012a's graceful-degradation
requirement without any code path ever depending on LLM availability for correctness — only for
prose quality.

**Alternatives considered**:
- **LLM-required architecture** (no fallback): Simpler initially, but violates FR-012a directly and
  creates an availability single-point-of-failure for a tool whose core value (the case list) must
  not depend on an optional enrichment. Rejected.
- **Always-on cloud LLM by default**: Faster to prototype against hosted APIs, but violates
  Principle VI's "local by default" mandate and FR-009/SC-006 (no source transmission without
  approval) outright. Rejected.

## 5. CLI & Git Diff Extraction

**Decision**: Shell out to the system `git` binary (`git diff`, `git log`, `git show`) via
`subprocess`, rather than a Python git library (e.g., `GitPython`, `pygit2`).

**Rationale**: `git diff <range>` / working-tree diff parsing is a well-understood, stable CLI
contract; shelling out avoids a native-extension dependency (`pygit2` requires libgit2 native
bindings, which complicates cross-platform packaging for Windows/Linux dev machines — see Target
Platform) and avoids GitPython's historically slower performance on large diffs. The tool already
depends on CMake and libclang being present locally, so requiring `git` on PATH is a consistent,
low-friction assumption for a C++/CMake developer's environment.

**Alternatives considered**:
- **GitPython**: Pure-Python-friendly but adds a non-trivial dependency surface and is reported to
  be slow on large repos; marginal benefit over shelling out for this MVP's diff-parsing needs.
  Rejected.
- **pygit2 (libgit2 bindings)**: Fast, but native-binding packaging complexity (per-platform
  wheels) outweighs benefit for an MVP whose git usage is limited to `diff`/`log`/`show`. Rejected
  for MVP; could reconsider if the tool later needs deep git object access.

## 6. Risk-Group Classification Rule Design

**Decision**: Each risk group (logic, ABI/layout, ownership/lifetime, thread safety, exception
safety, build config) is implemented as an independent, composable rule module operating on the
libclang AST diff (old vs. new cursor for a changed symbol). Rules are **additive** (a single
changed symbol can trigger multiple risk groups simultaneously) and a change matching none of the
five specific rule sets defaults to "logic" (per spec Assumptions). Priority (FR-004a) is computed
as a pure function of `(hop_distance, max_risk_severity)` with a fixed severity ordering: {ABI/
layout, thread-safety, exception-safety, ownership/lifetime} > {logic, build-config}.

**Rationale**: Directly implements FR-003/FR-004a as deterministic, independently testable units
(each becomes one pytest fixture per Technical Context's Testing section), satisfying Principle
VII's "err toward recall" by allowing overlapping/multiple classifications rather than forcing a
single mutually-exclusive label that could suppress a valid secondary risk signal.

**Alternatives considered**:
- **Single mutually-exclusive classification per change**: Simpler model, but would force an
  arbitrary tie-break when a change is simultaneously, e.g., an ABI change *and* introduces a new
  mutex — directly contradicts "recall over volume" by hiding one of the two legitimate risk
  signals. Rejected.
- **LLM-driven classification**: Would violate Principle III (LLM must not decide
  inclusion/exclusion or discover risk) and FR-011 directly. Rejected outright — not a viable
  alternative under this constitution.

## 7. Pilot Module Build Prerequisite

**Decision**: Before the MVP acceptance run, the pilot module's CMake configuration
(`unittests/CMakeLists.txt` in `remotecontrolapp`) must be (re-)configured with
`-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` plus a CMake File API query directory
(`<build>/.cmake/api/v1/query/codemodel-v2`) created prior to the configure step, so both the
compile database and the target codemodel are emitted into the same build directory
(`<build>/.cmake/api/v1/reply/`).

**Rationale**: Directly satisfies FR-013's hard prerequisite check and the spec's Assumptions
section ("the team will enable `CMAKE_EXPORT_COMPILE_COMMANDS=ON`"). Because the pilot's current
`CMakeLists.txt` cross-compiles for an embedded ARM target (sysroot-based toolchain), the advisor
must consume the compile database *as generated by that cross-compiling configure step* — it does
not need its own host-native build, only the JSON/File API artifacts.

**Alternatives considered**:
- **Advisor runs its own CMake configure pass**: Rejected — the advisor MUST NOT mutate the
  analyzed repository (Principle VIII) and should not assume rights to (re)configure a build
  directory with embedded-toolchain specifics it doesn't own; it only consumes artifacts the team's
  own build/CI process produces.

## Output Summary

All Technical Context items are resolved; no `NEEDS CLARIFICATION` markers remain. Proceeding to
Phase 1 design.
