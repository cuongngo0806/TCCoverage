# Report contract additions — spec 013

- `report.json`: new top-level `test_scenarios` (see data-model.md) for the cases still to test. No existing field
  changes; old readers ignore it.
- `report.md`: new section `## Test scenarios` right after the summary: one line "N scenario(s) cover M case(s)",
  a mermaid `flowchart LR` (one subgraph per scenario, changed node red), then per scenario
  `### S<n> · P<x> · <action> — <k> case(s)` with run / covers / why / checks. The previous per-case list follows
  under `## Test case details` (each case tagged with its scenario).
- `report.ai-verified.md`: same plan for the closed cases.
- `report.html`: section `#planSec` (scenario cards) before the impact graph; case cards fold When / Evidence /
  Path / Corner cases / Targets into a `<details>`; "Record for the scenario" sets the same verdict on every
  covered case (per-case results block unchanged).
- `report.brief.txt`: after the plan line, `SCENARIO S<n> P<x> <TAG> <flow arrow text> :: <case ids>` and up to 4
  `   check:` lines; TC lines carry ` [S<n>]` and no `corner:` line when scenarios are shown.
