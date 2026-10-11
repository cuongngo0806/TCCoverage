# Implementation Plan: Lesson-learned impact patterns and a fillable test report

**Branch**: `claude/tc-coverage-app-ww14wt` | **Date**: 2026-10-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-lesson-patterns-test-report/spec.md`

## Summary

Three additions on top of the existing deterministic pipeline (index → ingest → graph → classify → evidence →
report):

1. **Data paths (US1)**: a bounded, intraprocedural def-use pass (libclang) over the functions that the
   impact graph already reaches, chained across calls, follows a changed value from its producer through
   forwarding functions to *emitting points* (send/write/publish-like calls, third-party calls of spec 005).
   One case per emitter (full path as evidence), lower-priority cases for forwarders, flags where the chain
   breaks (container, queue, callback, unresolved call).
2. **Trigger sources and lesson patterns (US2, US4)**: per changed function, all distinct sources reaching
   it (caller chains + visible callback registrations), with a textual guard comparison between the fixed
   source and its siblings; seven built-in patterns (symmetric counterpart, same code elsewhere, new enum /
   status value, changed return meaning, shared state, new early exit, configuration readers) and
   team-defined lessons from `.tcadvisor/lessons.json`.
3. **Fillable report (US3)**: `report.html` becomes a self-contained form — verdict / comment / tester /
   date / defect / embedded attachments per case, validation rules, summary, *Save* (writes a new single
   HTML file with results and evidence inside), print-to-PDF layout. Cases get a stable `key`; a re-run
   with `--previous-report filled.html` carries results over and marks "needs re-check" when the code
   behind a case changed.

Every new case goes through the existing evidence gate; ranking changes are accepted only with a benchmark
run that keeps recall and dev + holdout MRR (spec 004 harness).

## Technical Context

**Language/Version**: Python ≥ 3.11 (analyzer); vanilla JavaScript (ES2020) inside the generated HTML;
TypeScript for the VS Code extension

**Primary Dependencies**: existing only — `libclang` wheel, `git`; no new Python or JS dependency
(constitution: no new dependencies; HTML stays offline, no external scripts)

**Storage**: existing SQLite cache (`cache/store.py`) gets a `flow_facts` table keyed like `tu_facts`;
verification results live inside the report HTML (JSON block + embedded base64 attachments)

**Testing**: pytest (unit + integration on the synthetic CMake fixture in `tests/conftest.py`); HTML form
logic tested headless with the pre-installed Chromium via Playwright when available (skipped otherwise);
`scripts/pilot_regressions.py` benchmark for ranking

**Target Platform**: Linux / Windows / macOS developer machines (CLI), any modern browser, VS Code ≥ 1.80

**Project Type**: CLI tool + generated single-file HTML report + VS Code extension

**Performance Goals**: analysis time per commit within +25% of today on the benchmark (median 55 s RocksDB /
140 s vsomeip); report with 50 cases and 20 MB of attachments saves in < 3 s in a browser

**Constraints**: offline; deterministic (same input → same cases, keys and order); bounded cost — data-flow
parsing limited to TUs defining functions already in the impact graph (`--flow-max-tus`, default 4 (changed files are always traced) — lowered from 60 after profiling: ~2–3.5 s parse per TU; changed files reuse the ingest parse; `git grep` calls of the patterns capped at 40 per run);
attachments embedded (FR-611), warning above 50 MB (`--attachment-warn-mb`)

**Scale/Scope**: code bases up to ~1M LOC (RocksDB) with a graph provider; reports up to a few thousand
cases (vsomeip worst case 3 000+) — form fields render lazily

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Status |
|---|---|---|
| I. Case-list-only output | New output is cases + a place for humans to record results; no test code, no scaffolding | PASS |
| II. Evidence-backed | Data-path / source / pattern cases carry the emitter / source / counterpart symbol + the path edges; all go through `evidence/gate.py` | PASS |
| III. Deterministic-first, bounded LLM | Def-use pass, guard comparison and patterns are rule-based on libclang tokens/cursors and git; no model involved | PASS |
| IV. Explicit uncertainty | Every break in a data path / unresolved source becomes an `uncertainty_flags` entry (existing categories) | PASS |
| V. Cost-aware incremental | Flow facts cached per TU content hash; on-demand parsing bounded by `--flow-max-tus`; text scans use `git grep` | PASS |
| VI. Local-first | Report is a local file; attachments stay inside it; nothing uploaded | PASS |
| VII. Recall over volume | Benchmark gate: recall unchanged, dev and holdout MRR not lower; placement chosen with the offline rank lab first | PASS (gated) |
| VIII. No code mutation / test execution / authoring | Tool never runs tests; testers record verdicts manually; analysed repo untouched (report written outside it) | PASS |
| IX. English output | Form labels, verdict names, case texts in English | PASS |
| Taxonomy growth only by amendment | No new risk group or uncertainty category; new `sub_reason` values only | PASS |

No violations → Complexity Tracking empty.

**Post-design re-check (after Phase 1)**: unchanged — the data model adds `key`, `pattern`, `path`,
`test_result` fields; the results block never feeds back into case generation or ranking (FR-613); the
`--previous-report` reader only copies results by key. PASS.

## Project Structure

### Documentation (this feature)

```text
specs/006-lesson-patterns-test-report/
├── plan.md              # this file
├── research.md          # Phase 0 decisions
├── data-model.md        # Phase 1 entities
├── quickstart.md        # Phase 1 validation scenarios
├── contracts/
│   ├── cli.md                    # new CLI options
│   ├── lessons-config.schema.json # .tcadvisor/lessons.json (sinks + team lessons)
│   ├── report-results.schema.json # results block inside report.html
│   └── report-form.md            # behaviour of the fillable HTML / VS Code save
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/tcadvisor/
├── index/flow.py            # NEW: per-function def-use facts (libclang), cached per TU
├── graph/dataflow.py        # NEW: chain flow facts from changed producers to emitters (US1)
├── graph/sources.py         # NEW: distinct trigger sources + guard comparison (US2)
├── classify/patterns.py     # NEW: built-in lesson patterns + team lessons (US4)
├── classify/cases.py        # + pattern/path cases, stable case key, ordering slot
├── evidence/uncertainty.py  # (unchanged API) flags for path breaks / unresolved sources
├── report/html.py           # + fillable form, save, print layout, summary
├── report/results.py        # NEW: read results from a filled report, carry over by key
├── report/render.py         # + verdict columns in MD/brief when results exist
├── pipeline.py              # wire the passes, --previous-report, --flow-max-tus
├── cli/main.py              # new options
└── cache/store.py           # + flow_facts table (SCHEMA_VERSION 2)

tests/
├── unit/test_flow.py, test_sources.py, test_patterns.py, test_results.py
├── integration/test_us6_dataflow.py, test_us6_sources.py, test_us6_patterns.py, test_us6_report.py
└── conftest.py              # + fixture modules A/B/C, four-source function

vscode-extension/src/extension.ts  # webview: save filled report via postMessage + save dialog
```

**Structure Decision**: single project, extending the existing packages along the fixed pipeline order;
three new analysis modules (`index/flow.py`, `graph/dataflow.py`, `graph/sources.py`) and one classifier
module (`classify/patterns.py`) keep each lesson independently testable; report concerns stay in `report/`.

## Implementation phases (for /speckit-tasks)

1. **Stable case key + results round-trip (US3 core)** — `key` on every case; results JSON block; reader
   for `--previous-report`; carry-over + "needs re-check" via a code fingerprint per case. Independent of
   the analysis work, delivers the report the team needs first.
2. **Fillable HTML form (US3 UI)** — form, validation rules, embedded attachments, save, print, summary,
   size warning; VS Code save path.
3. **Trigger sources (US2)** — sources + guard comparison; cases and flags.
4. **Data paths (US1)** — flow facts, chaining, emitter catalogue (built-in + `lessons.json` `sinks`),
   validation detection, cases and flags.
5. **Patterns + team lessons (US4)** — seven detectors, `lessons.json` `lessons`.
6. **Ranking + benchmark** — offline rank lab on new reports to choose the slot of new cases; full
   benchmark run; results in `results.md`.

## Complexity Tracking

None.
