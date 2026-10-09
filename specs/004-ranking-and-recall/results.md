# Cycle 4 — Optimising recall and ranking on 55 real regressions

Goal ("keep going until the result is the best"): never miss a regression, name the function that later had to
be fixed, and put it as high as possible in the list a reviewer reads — measured, not guessed.

## Benchmark

| Project | Pairs | Source of ground truth |
|---|---|---|
| RocksDB (898 k LOC) | 21 (16 scorable) | fix commits naming the PR that introduced the bug |
| COVESA vsomeip (133 k LOC) | 40 (39 scorable) | SZZ (`git blame` of lines the fix removes) |

`scripts/pilot_regressions.py` prepares one worktree + CMake build + codegraph index per introducing commit once
(the slow part: ~1–2 min each), then every evaluation only re-runs the analysis (~1 min per pair, 2 in
parallel). Even rows = **dev**, odd rows = **holdout**; ranking choices were made on the combination and checked
on both halves to avoid over-fitting. Ground truth = functions containing the lines the fix changed (brace-aware
scan; git hunk headers were found to name the *preceding* function and were replaced).

## Results (55 scorable regressions)

| | baseline (cycle 3) | after ranking (C) | **final (E)** |
|---|---|---|---|
| fixed function named (symbol level) | 49 | 50 | **51** |
| only its file named | 6 | 5 | **4** (3 are `#include` fixes: the file *is* the right granularity) |
| completely missed | 0 | 0 | **0** |
| fixed function in the first 10 cases | 15 | 26 | **26** |
| fixed function in the first 20 cases | 22 | 29 | **29** |
| MRR (mean 1/rank) | ~0.12 | ~0.28 | **~0.35** |
| median rank — RocksDB / vsomeip | 10.5 / 50 | 2.5 / 22 | **2 / 22** |
| median analysis time per commit — RocksDB / vsomeip | 48 s / 150 s | 56 s / 139 s | 55 s / 140 s |

Per project (final): RocksDB MRR 0.256 → **0.496** (dev 0.506 / holdout 0.482), top-10 8 → 10 of 16;
vsomeip MRR 0.064 → **0.290** (dev 0.168 / holdout 0.406), top-10 7 → 16 of 39.
(Raw: `data/*-summary.json`; per-pair tables `data/*-baseline.md`, `data/*-iterC.md`, `data/*-final.md`.)

## What changed (and what the data said)

1. **Relevance order** — offline *rank lab* (`scripts/rank_lab.py`) re-orders existing reports with candidate
   functions in seconds. Winner on dev *and* holdout: distance → substantive before recompile-only/log/test →
   log2(changed lines) → risk severity → fan-in. Change size was the strongest single signal (MRR 0.16 → 0.28);
   counting risk groups and grouping cases by symbol made it *worse* and were dropped.
2. **Precise ownership rules** — `const T&` parameters and `const char*` are not lifetime risks; `reset` is no
   longer a pointer-ownership token. These were the largest noise source in P1.
3. **Callers of a changed signature** rank low (the compiler checks every call site).
4. **Downstream edges** (`called_by_change`): a function called differently on a changed line becomes a direct,
   terminal impact (motivated by the RocksDB blob-file regression).
5. **Bug-fix history** (iteration E): files with more fix commits in the 12 months before the change rank
   higher inside the same distance/size bucket (one `git log`, local; `--no-history` disables it). Rank lab and
   the real run agree: MRR 0.28 → 0.35, both halves improve. The count is shown on each case.
6. **Constructor calls through factories**: `make_unique<T>(args)` / `make_shared` / `new T(...)` on a changed line
   reach `T`'s constructor — this turned the RocksDB blob-file regression from file level into symbol level.
7. **Code the parser never saw** (inactive `#if` branch, tool not in the build): changed lines are attributed to
   the enclosing function by a text scan, so impact can still be traced by name and the regression is named at
   symbol level (+2 RocksDB regressions, e.g. `db_stress` built only with gflags).

## Does AI verification help? (measured on the C ranking, 46 reports, $11.77, 222 calls)

`scripts/ai_rank_eval.py`: verify the first 40 cases of every report (Haiku per batch + one Sonnet synthesis) and
compare the deterministic order with an **AI-triaged view** (confirmed > needs_info > unverified > weak, stable).

| | deterministic | AI-triaged view |
|---|---|---|
| fixed function in the first 10 | 26 | **29** |
| MRR | 0.283 | **0.328** |
| median rank | 14 | **8** |

- When the fixed function was inside the verified window (33 cases) the AI said confirmed 24, needs_info 3,
  **weak 6** — it would have hidden 18 % of the real regressions if it were allowed to drop cases. The
  constitution rule "AI annotates, never removes" is therefore kept; the AI order is an optional *view*
  (HTML "Order: AI-triaged", VS Code `tcCoverage.ai.order`), the deterministic order stays canonical.
- In 27/55 reports an AI "also check" item named the later-fixed function with the right file.

## Remaining gaps (next cycle)

- 1 RocksDB regression only at file level: an MSVC-only code path (`crc32c` on Windows) that no Linux build
  sees (would need a Windows compile database). The blob-file data-flow regression is now found (via the
  constructor), but ranks low inside a 2,700-case commit.
- vsomeip ranking is weaker than RocksDB because SZZ intro commits are large (median 629 cases); a per-commit
  "top N + N more" budget in the brief/VS Code tree would help reviewers.
- Re-run the benchmark in CI (prepared worktrees are cacheable) to guard recall and ranking.
