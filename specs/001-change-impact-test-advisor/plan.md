# Implementation Plan: Change Impact & Test Case Advisor (MVP)

**Branch**: `001-change-impact-test-advisor` | **Date**: 2026-10-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-change-impact-test-advisor/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Build a locally-run CLI tool ("the advisor") that takes a C++/CMake change (git diff or an
explicit symbol list) and produces an **evidence-backed list of test cases to check** — never test
code. A deterministic pipeline (libclang AST parsing + CMake File API target mapping) builds the
dependency graph and classifies each change into risk groups (logic, ABI/layout, ownership/
lifetime, thread safety, exception safety, build config); an optional, bounded, local-first LLM
step only writes the human-readable description and refines risk labeling over the
already-filtered node set, with a fully deterministic rule-based fallback when the LLM is
unavailable. Results are cached per commit in a local SQLite index so repeat runs are incremental,
not full re-scans. The MVP is validated against two small, closely-related CMake targets in the
Honda `remotecontrolapp` pilot module: `RemoteDoorLock` and `RemoteDoorUnlock`.

Cost/quality strategy for this plan (per user request to optimize both):
- **Cost**: maximize deterministic tooling (libclang + CMake File API, both local and free),
  keep the LLM step optional/off-by-default with a zero-cost rule-based fallback, cache aggressively
  per commit+file-hash, and cap per-run LLM input to only the pre-filtered node set (bounded token
  usage, tracked per FR-012).
- **Quality**: evidence gate before any case is emitted (Principle II), explicit uncertainty
  channel instead of silent drops (Principle IV), deterministic priority/risk rules so results are
  reproducible and auditable (FR-004a, FR-011), and a pytest-based test suite with synthetic C++/
  CMake fixtures that exercise each risk-group rule in isolation before validating against the real
  pilot module.

## Technical Context

**Language/Version**: Python 3.11+ for the advisor tool itself. Analyzes C++11/C++14 CMake
projects (the pilot module's `unittests/CMakeLists.txt` targets C++11; the production
`Makefile.am` library build targets C++14) — the advisor must tolerate both standards via Clang's
own language-standard detection from `compile_commands.json` per-file flags.

**Primary Dependencies**:
- `libclang` (Python bindings, `clang.cindex`) — deterministic AST parsing: calls, inheritance/
  overrides, includes, template instantiations, signatures, `noexcept`/`throw`, pointer/reference/
  move usage.
- CMake **File API** (`cmake-file-api(7)`, codemodel-v2 query) — deterministic file→target mapping;
  more reliable than inferring targets from `compile_commands.json` alone.
- `compile_commands.json` (enabled via `CMAKE_EXPORT_COMPILE_COMMANDS=ON`) — per-file compiler
  invocation (flags, defines, include paths) consumed by libclang.
- `git` CLI (invoked as a subprocess; no heavyweight git library dependency) — diff/commit-range
  extraction.
- `sqlite3` (Python stdlib) — per-commit, per-file-hash dependency index and analysis result cache.
- Optional, bounded LLM client (local endpoint such as Ollama by default; any other endpoint only
  if explicitly team-approved and configured) — used only for case description text and risk-label
  refinement over the pre-filtered node set (Principle III/VI). Disabled by default; the advisor
  is fully functional without it via the deterministic rule-based fallback (FR-012a).

**Storage**: Local SQLite cache file (e.g., `.tcadvisor/cache.sqlite3`), one per analyzed
repository/module, keyed by commit hash + per-file content hash for incremental invalidation. No
external database, no network storage.

**Testing**: `pytest` for the advisor's own unit and integration tests, using small synthetic
C++/CMake fixture projects (one fixture per risk-group rule) plus a read-only integration smoke
test against the pilot module. The advisor's own tests are unrelated to — and must never invoke —
GoogleTest, which belongs solely to the analyzed `remotecontrolapp` repository.

**Target Platform**: Cross-platform local CLI (Windows and Linux dev machines / CI runners).
Requires the analyzed module to have a CMake build directory configured with
`CMAKE_EXPORT_COMPILE_COMMANDS=ON` and CMake File API query files present.

**Project Type**: Single-project CLI/library tool (Option 1 structure) — not a web/mobile app.

**Performance Goals**: Complete analysis of a ~50-file diff in the pilot module within the SC-001
budget (target: under 10 minutes end-to-end on a warm/cached index); cache-hit re-runs on an
unchanged commit (SC-003) complete without a full re-index (target: low-single-digit seconds for
cache lookup + report re-render).

**Constraints**: Fully local execution by default (Principle VI, FR-009, SC-006); LLM usage bounded
to the pre-filtered node set only, never the full codebase (Principle III, FR-011); must degrade
gracefully to a fully deterministic path when the LLM is unavailable (FR-012a); diffs over ~50
files MUST be split and analyzed per CMake target/module (FR-010a); the tool MUST NOT write to, or
otherwise mutate, any tracked file inside the analyzed repository (Principle VIII) — its cache and
output artifacts are written to a dedicated local directory outside the analyzed repo's tracked
tree by default (e.g., this workspace's `.tcadvisor/` or a user-specified path), never silently
inside the target repo.

**Scale/Scope**: MVP validated against exactly 2 CMake targets in one pilot module
(`RemoteDoorLock`, `RemoteDoorUnlock` in `remotecontrolapp`); architecture must not hard-code
assumptions that block extending to additional targets/modules in a later phase, but no additional
targets are validated in this MVP.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Plan compliance |
|---|---|
| I. Test-Case-List-Only Output | The `report` module emits only Markdown + JSON test-case lists (id, description, activation condition, evidence, priority, risk group). No test-code generation module exists anywhere in the design. **PASS** |
| II. Evidence-Backed Traceability | An explicit evidence-gate step runs before output assembly; any candidate case without a resolving file/symbol reference is rejected (or rerouted to the uncertainty channel if it matches the Principle IV taxonomy). **PASS** |
| III. Deterministic-First, Bounded LLM | Dependency graph (calls/inherit/include/instantiate/link-to-target) is built exclusively by libclang + CMake File API. The optional LLM step runs strictly after this pass, only on the already-filtered node set, only for description text and risk-label refinement — never for dependency discovery. **PASS** |
| IV. Explicit Uncertainty Flagging | Dedicated "uncertain / needs manual review" output channel, populated for uninstantiated templates, dynamic/DI/config-driven routing, and build-config-incomplete macros — kept distinct from confirmed cases, never silently dropped. **PASS** |
| V. Cost-Aware Incremental Analysis | SQLite cache keyed by commit + file-hash; re-analysis limited to the changed subgraph; diffs over ~50 files split per CMake target (FR-010a). **PASS** |
| VI. Local-First Execution & Privacy | No network calls by default; LLM step defaults to a local endpoint or is fully disabled (rule-based fallback); any external endpoint requires explicit, documented opt-in configuration. **PASS** |
| VII. Recall Over Volume | Deterministic rules are designed to err toward flagging (inclusion) for any matched risk signal rather than suppressing borderline cases; SC-005 miss-rate measurement against the pilot module's curated regression list is the acceptance gate, not case count. **PASS** |
| VIII. Fixed Scope | The advisor only reads the analyzed repository; all writes (cache, reports) target a separate local directory; no device/test execution code path exists; no test-authoring module exists. **PASS** |
| IX. English-Only | All CLI messages, report text, and documentation produced by the tool are English-only, regardless of analyzed source language. **PASS** |

No violations. Complexity Tracking table is not needed for this plan.

### Post-Design Re-Check (after Phase 1: data-model.md, contracts/, quickstart.md)

| Principle | Post-design verification |
|---|---|
| I. Test-Case-List-Only Output | `output-schema.json` defines only `test_case_candidates` (id/description/activation_condition/evidence/priority/risk_group) and `uncertainty_flags` as emitted artifacts; `cli-contract.md`'s Non-goals section explicitly excludes any `fix`/`apply`/`generate-tests`/`run-tests` command. **PASS, unchanged**. |
| II. Evidence-Backed Traceability | `TestCaseCandidate.evidence` is schema-enforced as `minItems: 1` in `output-schema.json`; data-model.md states a candidate failing this is never emitted. **PASS, confirmed by schema**. |
| III. Deterministic-First, Bounded LLM | `cli-contract.md` defaults to `--no-llm`; when enabled, `AnalysisRun.llm_token_usage` is tracked and the LLM only ever touches pre-filtered evidence fields per research.md §4. **PASS, confirmed**. |
| IV. Explicit Uncertainty Flagging | `UncertaintyFlag` is a first-class schema object, structurally separate from `TestCaseCandidate`, with a fixed 4-category enum matching the constitution's minimum taxonomy. quickstart.md Scenario 6 explicitly tests that flagged symbols do not also appear as fabricated cases. **PASS, confirmed**. |
| V. Cost-Aware Incremental Analysis | `CachedDependencyIndex` (data-model.md) + `--split-threshold` CLI option (default 50, matching FR-010a) implement subgraph-only invalidation and module-splitting. quickstart.md Scenario 4 validates cache-hit behavior. **PASS, confirmed**. |
| VI. Local-First Execution & Privacy | `cli-contract.md` requires `--llm-external-approved` as an explicit additional flag before any non-localhost `--llm-endpoint` is accepted — approval is enforced at the CLI parsing layer, not just documented. **PASS, strengthened**. |
| VII. Recall Over Volume | data-model.md's `RiskClassification` is explicitly additive (multiple risk groups per symbol allowed); quickstart.md Scenario 8 defines the SC-005 baseline-capture process without a hard numeric gate that could pressure premature filtering. **PASS, confirmed**. |
| VIII. Fixed Scope | `cli-contract.md`'s `--output-dir`/`--cache-dir` contract requires paths outside the analyzed `--repo`; Non-goals section reiterates no mutation/execution/authoring commands exist. **PASS, confirmed**. |
| IX. English-Only | All schema string fields (`description`, `activation_condition`, `reason`) are documented as English-only outputs; CLI stdout/stderr contract specifies English. **PASS, confirmed**. |

**Result**: No new violations introduced during Phase 1 design. Gate passes; proceeding is
approved. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-change-impact-test-advisor/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── cli-contract.md
│   └── output-schema.json
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
# Option 1: Single project (DEFAULT) — this feature uses this structure
src/
└── tcadvisor/
    ├── cli/                # CLI entry point & argument parsing (git-diff mode, explicit-symbol mode)
    ├── ingest/              # Git diff extraction; explicit symbol-list parsing (FR-001, FR-001a)
    ├── index/
    │   ├── clang_index.py   # libclang-based AST parsing: symbols, calls, inherit/override, includes, instantiations
    │   └── cmake_targets.py # CMake File API codemodel-v2 parsing → file-to-target map (FR-005)
    ├── graph/               # Dependency/call graph construction + direct/indirect traversal (FR-002)
    ├── classify/            # Deterministic risk-group rule engine (FR-003) + deterministic priority (FR-004a)
    ├── llm/                 # Optional, bounded description/risk-label enrichment (FR-011/FR-012/FR-012a)
    ├── cache/               # SQLite-backed per-commit, per-file-hash index & result cache (FR-010, FR-010a)
    ├── evidence/            # Evidence-gate validation (FR-006) + uncertainty-flag routing (FR-007)
    └── report/              # Markdown + structured JSON output assembly (FR-008)

tests/
├── unit/                    # Rule-by-rule unit tests per risk group, cache invalidation, evidence gate
├── integration/             # Synthetic C++/CMake fixture projects exercising full pipeline end-to-end
└── pilot/                   # Read-only smoke test against the remotecontrolapp pilot module (SC-001/002/004)
```

**Structure Decision**: Single-project CLI/library layout (Option 1). The advisor's own source and
tests live in this workspace (`TCCoverage`), fully separate from the analyzed
`remotecontrolapp` repository, which the advisor only ever reads from (Principle VIII). Cache and
report output default to a local directory outside the analyzed repo's tracked tree.

## Complexity Tracking

> No Constitution Check violations were found; this section is intentionally empty.
