# Implementation Plan: Test scenarios — fewer, focused, visual test plan

**Branch**: `ccr-bfedd45f-artzg9` | **Date**: 2026-10-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-test-scenarios/spec.md`

## Summary

A new render-time module `report/scenarios.py` groups the cases of a report part into **test scenarios**: call
paths through the impact graph (greedy set cover: one test entering at the outermost caller walks every case on the
path) and families of non-call relations (`contains`, `include`, `inherit_override`, …) per changed symbol. Each
scenario carries its covered case ids/keys and de-duplicated checks (AI corner cases, concrete rule corners, generic
hints last). report.json gains `test_scenarios`; report.md / report.ai-verified.md show a scenario-first plan with
a mermaid flow; report.html shows scenario cards (flow boxes, covered-TC chips, a "record for the whole scenario"
action) above a case list whose long fields are folded; the brief lists SCENARIO lines before TC lines and no
longer repeats corner cases per TC. Separately, include-guard detection (`ingest/changes.py`) skips leading
multi-line block comments, which removes the pilot's 20 false `build_config_incomplete_macro` flags.

## Technical Context

**Language/Version**: Python ≥ 3.10 (existing package)

**Primary Dependencies**: none new (stdlib only; HTML stays self-contained, no external script)

**Storage**: report files in the run folder (unchanged layout); `test_scenarios` added to report.json

**Testing**: pytest — `tests/unit/test_scenarios.py` (grouping on synthetic report dicts), rendering tests,
include-guard unit test, `tests/integration/test_l10n.py` (vi catalog)

**Target Platform**: Linux (Windows/macOS unchanged)

**Project Type**: CLI + report renderer

**Performance Goals**: scenario building is O(cases × paths); pilot (244 cases, 126 nodes) < 50 ms

**Constraints**: deterministic, no LLM; case list, ids, keys, priorities and ranking unchanged

**Scale/Scope**: up to a few thousand cases / nodes per report (path enumeration capped per start node)

## Constitution Check

| Principle | Status |
|---|---|
| I Case list only | ✅ scenarios are groupings of cases to check — no test code; "run" names an entry function, not a script |
| II Evidence | ✅ each scenario lists its case ids; every case keeps its evidence; steps carry file:line |
| III Deterministic first | ✅ pure function of cases + impact graph; AI corner cases are only copied from existing verdicts |
| IV Uncertainty | ✅ flags untouched except include guards, which are not build conditions (bug fix, not a silent drop) |
| V Cost | ✅ render-time, no re-index; cache unaffected |
| VI Local-first | ✅ nothing leaves the machine |
| VII Recall | ✅ no case removed; grouping is presentation; SC-004 checks case keys are identical |
| VIII Scope | ✅ no test execution, the HTML only records results like before |
| IX Language | ✅ report.json English; new sentences via `vi_*` catalogs |

Gate: PASS (re-checked after design: PASS).

## Project Structure

### Documentation (this feature)

```text
specs/013-test-scenarios/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/report-additions.md
└── tasks.md
```

### Source Code

```text
src/tcadvisor/report/scenarios.py      # NEW: build(cases, impact_nodes) -> list[dict]; localize helper
src/tcadvisor/report/render.py         # md (scenario plan + mermaid), ai md, brief, report.json test_scenarios
src/tcadvisor/report/html.py           # plan cards, folded case details, record-for-scenario
src/tcadvisor/report/l10n/vi_ui.py     # new md/brief UI strings
src/tcadvisor/report/l10n/vi_html.py   # new HTML strings
src/tcadvisor/ingest/changes.py        # include guard after block comments
tests/unit/test_scenarios.py           # NEW
tests/unit/test_rules.py               # include guard case
```

**Structure Decision**: single package, one new report module; no change to pipeline order.

## Complexity Tracking

None.
