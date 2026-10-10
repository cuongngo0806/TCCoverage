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
| median seconds | 42.4 | 44.5 (**+5%**) | 84.6 | 97.4 (**+15%**) |

Gate (no surfaced regression lost; dev and holdout MRR not lower; time ≤ +25%): **passed** on both projects.

New cases over all benchmark commits (run *on*): RocksDB 5 data-path emitter, 3 forwarder, 16 sibling-source,
155 other pattern cases, 102 reasons folded into existing cases; vsomeip 50 emitter, 15 forwarder,
457 other pattern cases, 296 folded.

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
   changed files, ≤ 40 `git grep` per run → final numbers above.

## Known limitations (follow-ups)

- `sibling_source` on widely used utilities (e.g. RocksDB `RecordTick`, dozens of callers) is mostly noise:
  only the 8 most relevant sources are expanded, but a fan-in threshold would remove these entirely.
- Data paths beyond 4 extra translation units are reported as a flag ("not traced: budget"), not traced;
  raise `--flow-max-tus` for a deeper review of a single change.
- `same_code_elsewhere`, `shared_state`, `config_reader` are text heuristics (bounded `git grep`); they are
  ranked low and need the reviewer's judgement.
