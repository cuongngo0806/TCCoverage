# Tasks: spec 008 — readers behind accessors, robust text scan, CI recall gate

## Phase 1: Setup
- [x] T801 yaml-cpp set (9 scenarios) in `scripts/seeded_regressions.py`; baseline recorded in spec.md

## Phase 2: User Story 1 — Robust text scan (P1)
- [ ] T802 [US1] `mask_literals()` in `ingest/changes.py`; `textual_functions` counts braces and matches heads on masked text
- [ ] T803 [US1] `_FN_HEAD` rules: no head for lines starting `:`/`,`; prefix-less heads only for `A::f`, `A::~A`, `~A`
- [ ] T804 [US1] `graph/sources.py` `guard_scope` and `_function_text` use masked text for brace counting
- [ ] T805 [P] [US1] `tests/unit/test_textscan.py`: braces in strings/chars/escaped quotes, multi-line init lists, plain calls, templates, destructors

## Phase 3: User Story 2 — Readers behind accessors (P1)
- [ ] T806 [US2] `patterns._accessor_callers()`: detect trivial accessor readers and expand to graph callers (cap 4, overflow stated, description names the accessor)
- [ ] T807 [US2] use it in `removed_write`, `lock_coupling`, `changed_default`, `class_consumer` readers
- [ ] T808 [P] [US2] integration test (fixture with inline getter in header and callers in another file)

## Phase 4: User Story 3 — State written under a changed condition (P2)
- [ ] T809 [US3] `conditional_write` in `patterns.coupling()` (condition-shaped edits, writes inside scope, field readers incl. `->field`)
- [ ] T810 [US3] add to `PATTERN_LOW_SUBS` and `STATE_READER_SUBS`; README pattern table row
- [ ] T811 [P] [US3] integration test

## Phase 5: User Story 4 — CI recall gate (P2)
- [ ] T812 [US4] `--min-victims SET=N` / `--min-corners SET=N` in `scripts/seeded_regressions.py`
- [ ] T813 [US4] `.github/workflows/ci.yml` (pytest, eval, seeded with thresholds, vscode-extension compile)

## Phase 6: Polish & gate
- [ ] T814 Full suite, leveldb eval, seeded benchmark all sets meet SC-801..SC-803; write `results.md`
- [ ] T815 Docs: CLAUDE.md commands (thresholds, yaml-cpp set), README
