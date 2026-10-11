# Cycle 5 — third-party API boundary cases: benchmark

Harness: `scripts/pilot_regressions.py --graph codegraph --cmake-args=-DCMAKE_CXX_COMPILER=clang++` on the
spec 004 pairs (`specs/004-ranking-and-recall/data/*-pairs.txt`), same prepared worktrees for every run.
*base* = code before spec 005 (cycle 4 + convergence T219/T220, which only add flags). 57 scorable
regressions (RocksDB 18, vsomeip 39; cycle 4 scored 55 — the remaining differences come from re-preparing the
worktrees in a new environment, identical for all runs below).

| Run | RocksDB MRR all / dev / holdout | vsomeip MRR all / dev / holdout | missed | `external_call` cases (vsomeip) |
|---|---|---|---|---|
| base | 0.473 / 0.462 / 0.487 | 0.292 / 0.163 / 0.427 | 0 | — |
| ext (sorted like any hop-0 case, no filtering) | 0.473 / 0.462 / 0.487 | 0.286 / **0.153** / 0.426 | 0 | 238 in 18 commits |
| **ext2 (final)** | **0.473 / 0.462 / 0.487** | **0.292 / 0.163 / 0.427** | 0 | 141 in 13 commits |

- `ext` violated the "dev and holdout must not get worse" rule: the new hop-0 cases pushed hop-1 ground
  truth down (9 pairs lost 1–29 positions).
- Offline re-ordering of the `ext` reports (re-using `evaluate()` of the pilot script) tested five placements;
  only "after all other hop-0 cases" and later reproduced the base MRR exactly. The earliest neutral one was
  kept, then confirmed by the full `ext2` run.
- Noise: operators (`operator==`, `operator->`), constructors and `const` queries (`port()`, `is_v4()`)
  produced meaningless "failure value" hints; filtering them removed 97 cases and 5 commits without losing
  real boundaries (`socket_ops::sync_connect` out-parameter `ec` + `addr/addrlen` buffer, `throw_error`,
  `basic_socket::set_option` error code). Merging all may-throw callees of a case into one hint was applied
  after `ext2`; it only changes hint text (case set and order verified identical on two pairs).
- RocksDB: no third-party call on any changed line (its 5 cycle-4 "outside the repository" flags were
  `fwrite`/`strstr`/`memcpy`, now classified as C standard library and counted in `run_notes`).
- After the benchmark, third-party calls inside logging statements were excluded (T509). This only removes
  cases from the end of the hop-0 block, so no ranked position can get worse. Demo commit vsomeip
  `07b13fa64`: 20 → 18 cases (the two `syscall(SYS_gettid)` cases inside `VSOMEIP_INFO` are gone).
