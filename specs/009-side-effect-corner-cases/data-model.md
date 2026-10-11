# Data model — spec 009

## EditShape (in memory, classify/edits.py)
| field | type | note |
|---|---|---|
| kind | str | operator_flip, logical_flip, constant_change, removed_guard, return_change, reorder, removed_call, removed_assignment |
| old | str | old line / statement (normalised) |
| new | str | new line / statement, "" when removed |
| hint | str | text appended to the changed symbol's corner_cases |

## Report additions
- `test_case_candidates[].sub_reason`: new values `removed_guard`, `removed_write`, `setter_readers`,
  `lock_coupling`, `changed_default`, `class_consumer` (existing schema: free string).
- `test_case_candidates[].pattern`: same values for the US2 kinds.
- `test_gaps`: list of `{symbol: SymbolRef, reason: str}`.

## SymbolChange additions
- `old_body: list[str]`, `new_body: list[str]` — text of the symbol on each side (empty when absent).
