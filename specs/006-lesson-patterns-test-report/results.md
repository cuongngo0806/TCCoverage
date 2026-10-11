# Spec 006 — benchmark (FR-617 / SC-605, task T634)

Harness: `scripts/pilot_regressions.py --graph codegraph --cmake-args=-DCMAKE_CXX_COMPILER=clang++ --jobs 2` on
the spec 004 pairs, same prepared worktrees for every run, one run at a time. *off* = same code with
`--no-patterns` (`--extra-args`), *on* = default.

| | RocksDB off | RocksDB on | vsomeip off | vsomeip on |
|---|---|---|---|---|
| scored / missed | 18 / 0 | 18 / 0 | 39 / 0 | 39 / 0 |
| MRR all | 0.473 | 0.473 | 0.292 | **0.293** |
| MRR dev | 0.462 | 0.462 | 0.163 | 0.163 |
| MRR holdout | 0.487 | 0.487 | 0.427 | **0.429** |
| fixed function in first 10 | 11 | 11 | 16 | 16 |
| median cases | 287 | 297.5 (+4%) | 629 | 649 (+3%) |
| median seconds | 43.1 | 46.4 (**+8%**) | 87.5 | 103.5 (**+18%**) |

Final code (commit 960da71, after convergence tasks T638–T640), runs `p6doff` / `p6e` (RocksDB) and
`p6doff` / `p6d` (vsomeip), all on the same container after a restart (an earlier `p6d` RocksDB run right after
the restart measured 55.5 s with a cold page cache and was repeated as `p6e`).

Gate (no surfaced regression lost; dev and holdout MRR not lower; time ≤ +25%): **passed** on both projects.

New output over all benchmark commits (run *on*): RocksDB 6 data-path emitter, 5 forwarder, 10 sibling-source,
155 other pattern cases, 104 reasons folded into existing cases, 317 changed functions with their trigger
sources listed; vsomeip 63 emitter, 23 forwarder, 457 other pattern cases, 314 folded, 1268 source listings,
19 data paths flagged where the depth limit stopped them.

## How the gate was reached

1. First run (`p6`, `--flow-max-tus 60`, every function of every parsed TU): MRR unchanged on RocksDB but
   2–4× slower per commit. Profiling: 200 s of 320 s in flow extraction (headers walked, changed files parsed
   twice).
2. Main-file functions only, changed files reuse the ingest parse, budget 24 → RocksDB +29%, vsomeip +64%.
   A review in the same round fixed US2 guard scope (an unrelated `if` protected every later call) and
   excluded moved code from `same_code_elsewhere`; US4 pattern cases were placed after the substantive
   cases of the same distance (`PATTERN_LOW_SUBS`). The offline rank lab (T633) was not needed: MRR held on
   the first full measurement with this placement.
3. Second profiling: lazily parsed TUs (~4 s each on vsomeip) and walking every top-level declaration.
   `clang_Location_isFromMainFile` filter, declaration file instead of `get_definition()`, budget 4 beyond the
   changed files, ≤ 40 `git grep` per run.
4. Convergence (T638–T640): depth/TU-stopped data paths flagged, member/global stores followed to their
   readers, sources of every changed function listed; utilities with more than 12 other sources get one
   summary `sibling_source` case (RocksDB `RecordTick` noise: 16 → 10 sibling cases). Gate re-checked above.

## Known limitations (follow-ups)

- Data paths beyond 4 extra translation units are reported as a flag ("not traced: budget"), not traced;
  raise `--flow-max-tus` for a deeper review of a single change.
- `same_code_elsewhere`, `shared_state`, `config_reader` are text heuristics (bounded `git grep`); they are
  ranked low and need the reviewer's judgement.
