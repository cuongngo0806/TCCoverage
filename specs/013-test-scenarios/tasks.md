# Tasks: Test scenarios (spec 013)

**Input**: `specs/013-test-scenarios/` (spec, plan, research, data-model, contracts)

## Phase 1: Foundational

- [x] T001 Include guard after leading block / line comments in `src/tcadvisor/ingest/changes.py` (`_include_guard`) + unit test in `tests/unit/test_rules.py` (US3)
- [x] T002 [P] `src/tcadvisor/report/scenarios.py`: `build(cases, impact_nodes)` — flow paths (greedy set cover over call paths), groups per (dependency, relation), checks de-dup, ordering + ids (US1)
- [x] T003 [P] `tests/unit/test_scenarios.py`: chain → 1 scenario; two callers → 2 scenarios, root once; group of `contains`; checks de-dup + generic drop; determinism; every case in exactly one scenario (US1)

## Phase 2: User Story 2 — focused, visual plan

- [x] T004 `report/render.py`: report.json `test_scenarios`; md "Test scenarios" section with mermaid before the case list; case list renamed "Test case details" with scenario tag; same in `to_ai_markdown` (US2)
- [x] T005 `report/render.py` brief: SCENARIO + check lines; TC lines tagged `[S<n>]`, corner lines dropped (US2)
- [x] T006 `report/html.py`: `#planSec` scenario cards (flow boxes, TC chips → filter, checks, record-for-scenario), case details folded (US2)
- [x] T007 l10n: `vi_ui.py`, `vi_html.py` entries for the new sentences; `scripts/l10n_check.py` + `tests/integration/test_l10n.py` green (US2)
- [x] T008 Packaged skill / agent / docs: brief reading order (SCENARIO lines first) in `integrations/skills/tc-coverage/SKILL.md`, `docs/workflow.md`, README; re-sync `.claude` copies via `tcadvisor init --repo . --ai claude --force` (US2)

## Phase 3: Validation

- [x] T009 Re-render the pilot (`human-test/remotecontrolapp/…/report.json`) → results.md with SC-001/SC-002 numbers; all-cases scenario ratio
- [ ] T010 Full pytest; case keys identical before/after on the synthetic project (SC-004); CLAUDE.md layout line
