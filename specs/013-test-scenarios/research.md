# Research — spec 013

## R1 Where to build scenarios
- **Decision**: at render time from the report dict (`report/scenarios.py`), per report part (main / AI-closed);
  `write_outputs` also stores the main part's scenarios in report.json.
- **Rationale**: AI verdicts (annotate / verify) change which cases are open after the analysis; render-time keeps
  scenarios consistent with what is shown, and old report.json files get scenarios without re-analysis.
- **Alternatives**: in `pipeline.py` after case assembly — stale once AI closes cases.

## R2 Which relations mean "one test walks them"
- **Decision**: only `call` edges form flow paths. Other relations (`contains`, `include`, `inherit_override`,
  `uses_type`, `instantiate`, `macro_expand`) form groups per (changed dependency, relation).
- **Rationale**: a call chain is executed by one test entering at the caller; a class member, includer or subclass
  shares the *same* risk (layout / rebuild) but is not executed by another member's test — one representative test
  plus a rebuild is the honest claim.
- Pilot (all 244 cases): 35 `contains` + 24 `include` + 8 `inherit_override` cases collapse to a handful of groups.

## R3 Choosing paths
- **Decision**: enumerate downward call paths (to lower hop only → no cycles) from every flow-case node, capped at
  64 paths per start; greedy set cover: most newly covered cases, then best priority, then fewest steps, then
  names. A path keeps its tail down to the changed symbol even when that tail's cases are covered or closed, so
  the flow always ends at the change.
- **Alternatives**: one scenario per entry point with all reachable callees — over-claims coverage when a caller
  reaches two changed functions in different branches.

## R4 Checks
- **Decision**: order = AI extra corner cases (already concrete, user language), then rule corner cases of the
  cases from the changed end upward; exact-text de-dup; generic rule hints (the static `HINTS` lists of
  `classify/rules.py`) only when nothing concrete remains. Renderers show 6 and count the rest.

## R5 Include guards after license comments
- **Finding**: `_include_guard` strips comments per line, so the inner lines of a `/* … */` license block
  (` * Copyright …`) count as code and the guard is not the first code line → 20 false flags in the pilot.
- **Decision**: blank block comments over the whole text (keeping line numbers) before looking for the first two
  code lines; same function serves the variant judge (`classify/variants.py` uses `conditional_stack`).
