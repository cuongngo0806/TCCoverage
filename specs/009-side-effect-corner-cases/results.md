# Spec 009 — results (T724)

Harness: `scripts/seeded_regressions.py` on google/leveldb `bb74ef7`, clang graph, one edit per scenario,
`--working-tree`, no run cache. *dev* = the 12 scenarios written before implementation (used while building);
*holdout* = 10 scenarios written after the first implementation and never used to tune hints or rules.
Ground truth (victims + corner regex) was written before each set was first run.

| | baseline f0e2fb3 dev | spec 009 dev | baseline holdout | spec 009 holdout |
|---|---|---|---|---|
| victim named | 8 / 12 | **12 / 12** | 9 / 10 | **10 / 10** |
| concrete corner case hinted | 3 / 12 | **12 / 12** | 2 / 10 | **10 / 10** |
| victim MRR | 0.295 | **0.402** | 0.327 | **0.347** |
| median cases | 13 | 12 | 9 | 11 |
| total seconds, 22 scenarios (2 interleaved runs) | 76.1 / 78.7 | 77.8 / 78.4 | | |

Gate SC-701..SC-704: **passed** (victims ≥ 11/12, corners ≥ 10/12, MRR not lower, median cases +≤50 %, time
+≤15 %, `scripts/eval_real_project.py` passes, full suite 140 passed).

## What the evaluation found (and what changed)

| Missed / noisy before | Cause | Now |
|---|---|---|
| readers of `background_compaction_scheduled_` after the write was removed | only *added* writes were followed | `removed_write` |
| `WriteBatch::Iterate` after `SetCount(...)` was dropped | removed calls ignored | `setter_readers` (getter of the same class) |
| `ReleaseSnapshot` after `GetSnapshot` lost its lock | lock change only classified, no readers | `lock_coupling` |
| `SanitizeOptions` / `MakeRoomForWrite` after `write_buffer_size` default changed | struct initialiser had no readers | `changed_default` |
| `MemTable::Get` after `MemTable::Add` changed the encoding | same class, not a caller | `class_consumer` |
| `left < right` → `<=` hinted "boundary values" | hints were generic per risk group | `operator_flip`: "`left <= right` now also holds when `left == right`" |
| use-after-free from swapped statements | no order analysis | `reorder` |
| error return replaced by `Status::OK()` | return values only checked for new constants | `return_change` |
| 10 "sibling source" cases ahead of the real callers for a loop-condition tweak | every changed condition was a "new guard" | loops and same-identifier tweaks are not guards |
| "inline change: rebuild every includer" for class-body methods in `.cc` | `is_inline` without header check | header definitions only |

Holdout analysis (after its first run, reported honestly): baseline named `LRUCache::Insert` only through the
sibling-source misfire; the principled replacement is `guard_removed_callee` (callees of a removed / weakened
condition). `Arena::MemoryUsage` was missed because in-class-body readers had no class in their name; readers are now
qualified through the graph. Both are generic fixes; the holdout numbers above include them.

## Independent review (T726)

A review subagent probed the diff with adversarial input; all confirmed findings were fixed with regression tests
(`tests/unit/test_edits.py`, "review findings"): template members in the text scan, inverted advice for removed early
exits, false P1 on equivalent refactors and removed asserts, quadratic regex on long literal lines, O(n·m) pairing on
huge rewrites, operand extraction, digit separators, function-pointer parameters, setter / global heuristics.
A second round on the fixes found and we fixed: exponential backtracking in the new template-aware head regex
(replaced by a linear bracket scan), nested template names, "still checked" filters that looked at unrelated
conditions in the body (now only the paired / added lines), narrowing `a || b` → `a` reported as a removed guard,
and the `guard_removed_callee` wording for early exits. Benchmark and eval numbers above are after both rounds.

## Known limitations

- The spec 004 RocksDB / vsomeip pilot was not re-run (prepared worktrees unavailable here). New case kinds sit in the
  low pattern tier (ranked after substantive cases of the same distance) and US2 readers are capped at P2; the only
  change to existing order is `removed_guard` raising the changed symbol's own case to P1.
- A guard deleted outright (no paired new line) gets the corner hint and P1 but no `guard_removed_callee` cases.
- Readers of members are found by bounded text search in the class's own files (constitution V); members with very
  generic names may produce a false reader (ranked low, stated as "read at file:line").
