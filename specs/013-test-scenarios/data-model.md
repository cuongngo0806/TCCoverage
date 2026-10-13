# Data model — spec 013

## TestScenario (report.json `test_scenarios[]`, English)

| Field | Type | Notes |
|---|---|---|
| `id` | str | `S1`, `S2`, … in plan order (stable for the same input) |
| `kind` | `flow` \| `group` | call path vs. family of a non-call relation |
| `priority` | `P1`–`P3` | best priority of the covered cases |
| `action` | `test_on_target` \| `review` \| `closed_by_review` \| `not_needed` | strongest action of its cases (target > review > closed) |
| `entry` | SymbolRef | where to trigger the test (flow: outermost caller; group: representative) |
| `steps` | list[{symbol, cases[], changed}] | flow: entry → … → changed symbol; group: [representative, changed dependency] |
| `relation` | str | `call` for flows, else the grouped relation |
| `members` | list[SymbolRef] | group: every covered symbol (flow: empty) |
| `cases` | list[str] | covered case ids (report order) |
| `keys` | list[str] | covered case keys (results contract) |
| `sub_reasons` | list[str] | distinct sub-reasons of the covered cases (e.g. `removed_guard`) |
| `risk_groups` | list[str] | distinct risk groups |
| `checks` | list[{text, source}] | de-duplicated; `source` `ai` (shown verbatim) or `rule` (translated at render time) |

Invariants: every case of the part is in exactly one scenario; scenarios sorted by (action, priority, −#cases,
entry name); `checks` has no duplicate text.
