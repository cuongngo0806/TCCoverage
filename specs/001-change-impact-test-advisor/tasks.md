---
description: "Task list for Change Impact & Test Case Advisor (MVP)"
---

# Tasks: Change Impact & Test Case Advisor (MVP)

**Input**: Design documents from `/specs/001-change-impact-test-advisor/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — plan.md (Technical Context → Testing) requires a pytest suite with synthetic
C++/CMake fixtures, one per risk-group rule.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested
independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story the task belongs to (US1..US4)

## Design amendments recorded during task generation

- `ImpactEdge.relation` gains `uses_type` (function → class it reads/constructs/accesses fields of)
  and `macro_expand` (symbol → macro it expands). Without them, class-member (ABI/layout) and macro
  (build-config) changes have no deterministic path to their dependents, which would silently
  lower recall (Principle VII). `contracts/output-schema.json` is updated accordingly.
- `SymbolRef.kind` gains `enum`, `macro`, `variable`, `file` so file-level and preprocessor
  changes can carry concrete evidence (Principle II) instead of being dropped.
- The JSON report gains `impact_nodes`, `affected_targets`, `out_of_scope`, `run_notes` and
  `no_detected_impact` so the visual report (Phase 7) is rendered from the same JSON (FR-008).
- Delivery surfaces (Phase 7) — HTML flow visualization, Claude Code skill/agent, VS Code
  extension — are thin viewers/launchers over `tcadvisor analyze`; none of them mutate source,
  run tests, or author tests (Principle VIII).

## Phase 1: Setup (Shared Infrastructure)

- [x] T001 Create package skeleton `src/tcadvisor/{cli,ingest,index,graph,classify,llm,cache,evidence,report}/` and `tests/{unit,integration}/` per plan.md
- [x] T002 Create `pyproject.toml` (Python ≥3.11, deps: `libclang`; dev: `pytest`, `jsonschema`; console script `tcadvisor`)
- [x] T003 [P] Add `.gitignore` entries for `.tcadvisor-cache/`, `tcadvisor-report*/`, `node_modules/`, `out/`, `__pycache__/`

## Phase 2: Foundational (Blocking Prerequisites)

- [x] T004 Implement data model dataclasses (ChangeInput, SymbolRef, ImpactEdge, ImpactNode, RiskClassification, TestCaseCandidate, UncertaintyFlag, AnalysisRun) in `src/tcadvisor/models.py`; `TestCaseCandidate.evidence` "MUST be non-empty"; `priority` enum `P1|P2|P3`
- [x] T005 [P] Implement compile database loader + FR-013 prerequisite/staleness checks in `src/tcadvisor/index/compile_db.py`
- [x] T006 [P] Implement CMake File API codemodel-v2 reader (file → targets, target source dirs) in `src/tcadvisor/index/cmake_targets.py`
- [x] T007 Implement libclang indexer (symbols, call / inherit_override / uses_type / instantiate / macro_expand / include edges, address-taken functions) in `src/tcadvisor/index/clang_index.py`
- [x] T008 Implement SQLite cache (per-TU facts keyed by content hash of TU + its repo-local includes; per-run results keyed by resolved change + options) in `src/tcadvisor/cache/store.py`
- [x] T009 [P] Implement git subprocess helpers (resolve revs, diff hunks, file content at rev, untracked files) in `src/tcadvisor/ingest/git.py`

**Checkpoint**: index + cache + git ingestion usable from Python.

## Phase 3: User Story 1 — Impact map + test case list (P1) 🎯 MVP

**Goal**: diff or explicit symbols → impact map (direct/indirect) → evidence-backed cases → MD + JSON.

**Independent Test**: `tests/integration/test_us1_impact.py` on a synthetic CMake fixture.

- [x] T010 [P] [US1] Integration tests: function body change → callers at hop 1/2; comment-only change → "no detected impact"; explicit symbol mode equals diff mode shape; second run is `cache_hit: true` in `tests/integration/test_us1_impact.py`
- [x] T011 [US1] Implement changed-symbol detection (old/new AST token signatures by USR, residual file-level hunks, comment/format-only suppression) in `src/tcadvisor/ingest/changes.py`
- [x] T012 [US1] Implement explicit symbol input (`--symbols`, `--symbols-file`; bare file paths rejected per FR-001a) in `src/tcadvisor/ingest/symbols.py`
- [x] T013 [US1] Implement graph build + bounded BFS traversal (default depth 2, all justifying edges kept) in `src/tcadvisor/graph/impact.py`
- [x] T014 [US1] Implement case generation + deterministic priority `(hop, severity)` + stable ids in `src/tcadvisor/classify/cases.py`
- [x] T015 [US1] Implement evidence gate (every case resolves against the current index; failures routed to uncertainty or raised) in `src/tcadvisor/evidence/gate.py`
- [x] T016 [US1] Implement Markdown (+ Mermaid flow) / JSON / brief renderers in `src/tcadvisor/report/render.py`
- [x] T017 [US1] Implement pipeline orchestration + module splitting above `--split-threshold` (FR-010a) in `src/tcadvisor/pipeline.py`
- [x] T018 [US1] Implement CLI per `contracts/cli-contract.md` (exit codes 0/1/2/3, output-dir outside repo, `cache clear`) in `src/tcadvisor/cli/main.py`

## Phase 4: User Story 2 — Risk category behind each case (P2)

**Independent Test**: one fixture diff per risk group in `tests/integration/test_us2_risk.py`.

- [x] T019 [P] [US2] Integration tests for abi_layout (member reorder), thread_safety (new `std::mutex`), exception_safety (`noexcept` removed), ownership_lifetime (raw `new`/`std::move`), build_config (`#ifdef`) in `tests/integration/test_us2_risk.py`
- [x] T020 [US2] Implement additive rule engine for all six risk groups with sub-reasons + corner-case hints (boundary values from changed comparisons) in `src/tcadvisor/classify/rules.py`
- [x] T021 [P] [US2] Unit tests for rules and priority in `tests/unit/test_rules.py`

## Phase 5: User Story 3 — Affected build targets (P2)

- [x] T022 [P] [US3] Integration test: shared header used by two targets lists both targets in `tests/integration/test_us3_targets.py`
- [x] T023 [US3] Map impacted files to targets (sources + transitive includers), `link_to_target` edges, `--targets` scope with out-of-scope reporting in `src/tcadvisor/graph/impact.py`

## Phase 6: User Story 4 — Uncertainty flags (P3)

- [x] T024 [P] [US4] Integration tests: uninstantiated template and DI-only virtual method are flagged and not fabricated into cases in `tests/integration/test_us4_uncertainty.py`
- [x] T025 [US4] Implement uncertainty detectors (uninstantiated_template, di_config_routing, dynamic_runtime_dependency, build_config_incomplete_macro) in `src/tcadvisor/evidence/uncertainty.py`

## Phase 7: Delivery surfaces & visualization

- [x] T026 [P] Optional bounded LLM enrichment (local Ollama default, external requires `--llm-external-approved`, token usage + prompt log, graceful degradation FR-012a) in `src/tcadvisor/llm/enrich.py`
- [x] T027 [P] Self-contained interactive HTML report (impact flow graph by hop, case table with filters, flags) in `src/tcadvisor/report/html.py`
- [x] T028 [P] Claude Code integration: `CLAUDE.md`, `.claude/skills/tc-coverage/SKILL.md`, `.claude/agents/tc-coverage-analyst.md`, speckit skills ported to `.claude/skills/`
- [x] T029 [P] VS Code extension (commands, tree view of cases, webview report) in `vscode-extension/`

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T030 Validate `report.json` against `contracts/output-schema.json` in tests (`tests/integration/test_schema.py`)
- [x] T031 [P] README with install, quickstart, Claude + VS Code usage in `README.md`
- [ ] T032 Pilot smoke run against `remotecontrolapp` (`RemoteDoorLock`, `RemoteDoorUnlock`) — requires the team's Windows machine and the curated regression list (SC-005); see quickstart.md Scenario 8

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1 (MVP) → {US2, US3, US4 in parallel} → Phase 7 → Phase 8.
- US2/US3/US4 only extend modules introduced in US1; each has its own fixture-based test file.

## Parallel Example

```text
T005 compile_db.py  |  T006 cmake_targets.py  |  T009 git.py
T019 test_us2_risk.py  |  T022 test_us3_targets.py  |  T024 test_us4_uncertainty.py
```

## Implementation Strategy

MVP = Phases 1–3 (diff → evidence-backed case list). Then add risk rules, target mapping and
uncertainty flags, then the delivery surfaces. T032 is the acceptance gate on real pilot data.
