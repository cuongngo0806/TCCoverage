# Tasks: Side-effect and corner-case completeness (spec 009)

**Input**: spec.md, plan.md, research.md, data-model.md, contracts/
**Tests**: included (unit per shape/detector, integration on the synthetic fixture, seeded benchmark gate).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [x] T701 Seeded-regression benchmark `scripts/seeded_regressions.py` (12 leveldb scenarios, victims/corner/MRR); baseline recorded in spec.md
- [x] T702 Fix benchmark detail: `victims_named` counts distinct ground-truth victims matched (not distinct names)

## Phase 2: Foundational

- [x] T703 `SymbolChange.old_body` / `new_body` filled in `ingest/changes.py` (parsed and textual symbols)

## Phase 3: User Story 1 — Corner cases from the edit shape (P1) 🎯 MVP

- [x] T704 [US1] `classify/edits.py`: line normalisation + old/new pairing (research R1)
- [x] T705 [US1] edit shapes: operator flip, logical flip, constant change, return change (R2)
- [x] T706 [US1] edit shapes: removed condition / dropped conjunct (`removed_guard`), removed call, removed assignment
- [x] T707 [US1] edit shape: reorder of statements (moved line crossing a neighbour)
- [x] T708 [US1] parameter input classes from the new declaration (R3)
- [x] T709 [US1] `rules.classify` attaches edit hints first in the logic case; `removed_guard` → P1 (`cases.priority`)
- [x] T710 [P] [US1] `tests/unit/test_edits.py` — one test per shape + parameter classes + no-crash on textual code

## Phase 4: User Story 2 — Lost side effects and state coupling (P1)

- [x] T711 [US2] `patterns.removed_write`: removed/changed assignment to member/global → readers
- [x] T712 [US2] `patterns.setter_readers`: removed setter call → callers of paired getter
- [x] T713 [US2] `patterns.lock_coupling`: lock added/removed → other accessors of members used under it
- [x] T714 [US2] `patterns.changed_default`: changed initialiser of field/constant/macro → readers
- [x] T715 [US2] `patterns.class_consumer`: modified method writing members → same-class readers
- [x] T716 [US2] new kinds in `PATTERN_LOW_SUBS`; overflow stated; respects `--no-patterns`
- [x] T717 [P] [US2] `tests/unit/test_coupling.py` + `tests/integration/test_us7_side_effects.py` (fixture project)

## Phase 5: User Story 3 — Noise (P2)

- [x] T718 [US3] `sources.guarded_calls`: ignore `while`/`for`, require a new identifier vs the paired old line
- [x] T719 [US3] `rules.classify`: `inline_change` only when the definition is in a header
- [x] T720 [P] [US3] tests for both (unit)

## Phase 6: User Story 4 — Test gaps (P2)

- [x] T721 [US4] `pipeline`: `test_gaps` in the report
- [x] T722 [US4] brief / Markdown / HTML show test gaps; schema updated if the report schema is validated
- [x] T723 [P] [US4] tests

## Phase 7: Polish & gate

- [x] T724 Full suite + leveldb eval + seeded benchmark meet SC-701..SC-704; record `results.md`
- [x] T725 Docs: CLAUDE.md layout/commands, README / docs mention of new case kinds and test gaps
- [x] T726 Independent review (subagent) of the diff; fix findings; re-run gate

## Dependencies

T703 → US1, US2. US1 ∥ US3 ∥ US4 after T703; US2 after T703. Phase 7 last.

## Phase 8: Convergence (from holdout analysis and review)

- [x] T727 `guard_removed_callee`: callees under a removed / weakened condition
- [x] T728 Readers defined inside a class body qualified through the graph
- [x] T729 Holdout scenarios (10) in `scripts/seeded_regressions.py`, reported separately
