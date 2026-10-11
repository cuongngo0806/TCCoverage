# Cycle 3 — Pilot on large real C++ projects (replacement for the `remotecontrolapp` pilot)

`remotecontrolapp` is not available, so the SC-005 pilot (quickstart Scenario 8) was run on two public
code bases chosen to resemble it:

| Project | Why | Size | Build |
|---|---|---|---|
| **COVESA vsomeip** | automotive SOME/IP middleware: services, availability/event handlers, callbacks, threads, routing — the closest public analogue of a remote-control app | 133 k lines C++, 112 TUs | CMake + Boost, GoogleTest tests |
| **facebook/rocksdb** | scale test: large, heavily templated, many interfaces and listeners | 898 k lines C++, 973 TUs (239 test TUs) | CMake, GoogleTest |

## Method (scripts/pilot_regressions.py)

Ground truth is "a curated set of real regression bugs" (SC-005), built automatically:

- **RocksDB**: fix commits whose message names the PR that introduced the bug (`introduced by #NNNN`,
  `regression from …`) → 12 pairs (`data/rocksdb-pairs.txt`).
- **vsomeip**: no such references, so the SZZ heuristic (`scripts/szz_pairs.py`: `git blame` of the lines a
  fix removes) → 15 pairs (`data/vsomeip-pairs.txt`).

For each pair the introducing commit is checked out in a private worktree, CMake is configured (compile
db + File API), codegraph is synced, and `tcadvisor analyze --graph codegraph` runs on that commit alone.
A regression is **surfaced** when a function later changed by the fix appears as a changed symbol,
impacted node or uncertainty flag; **file-level** when only its file does; **missed** otherwise. We also
record the **rank** of the first case on that function (what a reviewer working top-down reaches).

## Results (final run, all fixes below applied)

| | vsomeip | RocksDB | total |
|---|---|---|---|
| scored regressions | 14 | 9 | **23** |
| surfaced at the fixed function | 13 | 7 | **20 (87 %)** |
| file-level only | 1 | 2 | 3 |
| completely missed | 0 | 0 | **0** |
| reached only through the graph (not a changed symbol) | 0 | 2 | 2 |
| fixed function within the first 20 cases | 4 | 5 | 9 |
| median rank of the fixed function | 50 | 15 | |
| median time per commit (cmake + graph sync + analysis) | 171 s | 158 s | |
| median cases per commit | 469 | 1117 | |

Per-pair tables: `data/vsomeip-pilot.md`, `data/rocksdb-pilot.md`.

Reading the numbers honestly:
- **Recall is good, but partly by construction for SZZ pairs**: SZZ picks the commit that last touched the
  fixed lines, so the fixed function is usually a changed symbol of that commit. The RocksDB pairs (named
  by the developers) are the stronger evidence; 2 of 7 were found *only* through the code graph
  (e.g. `IODispatcher` memory accounting reached from the MultiScan refactoring, with the
  `IODispatcherTest.*` tests listed for re-run).
- **Ranking is the weak spot**: big commits produce hundreds of cases; the fixed function had median rank
  50 (vsomeip) / 15 (RocksDB). This is where AI verification is meant to help, without removing cases.
- **Missed / file-level**: the blob-file regression (RocksDB #14227 → #15021) flowed through a callback
  (`CompactionOutputs` output-path vector handed to `BlobFileBuilder`): a call graph cannot see it.
  It is the top item of the next-cycle backlog (callback / std::function data-flow edges).

## AI verification on a pilot report (vsomeip `d1e2281` → fix `eec6f1a`)

`tcadvisor verify` on the 60 highest-ranked cases: 5 model calls (4 Haiku + 1 Sonnet), 86 k input / 31 k output
tokens, **$0.13, 83 s**. The synthesis listed as an additional check *"is_offered keys only on service and
instance, so any major/minor version reports as offered"* — exactly the defect the later fix addresses
("duplicate registration warning must match major/minor"). The per-case Haiku verdicts on that function were
`weak` (they only saw the header declaration): this confirms the rule that AI verdicts annotate but never
remove cases.

## Defects found by the pilot and fixed in this cycle

| # | Symptom on the real code base | Fix |
|---|---|---|
| 1 | Full libclang index of 973 TUs needed even when impact comes from codegraph (~25 min) | `--index lite`: `#include` scan only (seconds); parallel libclang index when needed |
| 2 | A provider "miss" on a **removed** symbol triggered a full re-index (1820 s for one commit) | removed roots are not looked up (their callers are roots of the same commit) |
| 3 | Fallback re-index of 861 TUs for unresolved roots (2092 s) | fallback limited to TUs including the root's file / same-stem header, capped by `--fallback-max-tus` (else flagged) |
| 4 | `uses_type` followed transitively → 4,904 impacted nodes | type coupling followed one hop from the changed type only |
| 5 | vsomeip "Log clean-up" (36 files) → 1,510 cases | log-only changes: one P3 case, no propagation (`TCADVISOR_LOG_PATTERN` to adapt) |
| 6 | GoogleTest macro symbols (`*_Test`, `AddToRegistry`) as roots, unresolvable by the graph | changes in test code: P3 "run the changed test", no propagation |
| 7 | `header_change` gave 787 P1 cases and buried real risks | recompile-only sub-reasons rank like logic; within a priority, risk concentration orders cases |
| 8 | One TU libclang cannot load aborted the run | per-TU failure is recorded, not fatal |

Before → after on the worst RocksDB commit (`3b5cb11`): 1820 s / 5053 cases → 161 s / 726 cases.

## How to reproduce

```bash
python3 scripts/szz_pairs.py --repo vsomeip --since 2025-01-01 --max 15 > pairs.txt   # or hand-written pairs
python3 scripts/pilot_regressions.py --repo vsomeip --pairs pairs.txt --work /tmp/pilot --graph codegraph \
        --cmake-args "-DCMAKE_CXX_COMPILER=clang++"
python3 scripts/pilot_regressions.py ... --rescore      # recompute metrics without re-analysing
```

For `remotecontrolapp` later: hand-write `pairs.txt` from the JIRA/Harmony regression list
(`<introducing sha> -> <fix sha> | ticket`) and run the same command with `--cmake-args` of the
`unittests/CMakeLists.txt` configuration.

## Next-cycle backlog (from this pilot)

1. Callback / `std::function` / member-pointer data-flow edges (the blob-file regression).
2. Better ranking inside large commits: weight by changed lines, existing-test proximity, and how many
   changed roots reach a node; measure with the pilot's rank metric.
3. Per-commit case budget in the brief (e.g. top 40 + "N more"), so reviewers and AI start from the top.
4. Run the pilot harness in CI on a fixed set of pairs to guard recall and ranking.
