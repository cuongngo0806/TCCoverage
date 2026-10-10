# Tasks: Test cases at third-party API boundaries (cycle 5)

## Phase 1: Signals (US1)
- [x] T501 [US1] Record callee declaration facts and discarded results per call in `src/tcadvisor/ingest/changes.py`
- [x] T502 [P] [US1] `src/tcadvisor/classify/external.py`: standard-library test, signals, one RiskClassification; unit tests in `tests/unit/test_external.py`
- [x] T503 [US1] Collect third-party calls per root in `src/tcadvisor/pipeline.py`; emit hop-0 cases in `src/tcadvisor/classify/cases.py`
- [x] T504 [US1] Integration test with a header-only vendor library outside the repo in `tests/integration/test_us1_impact.py`

## Phase 2: Contracts (US2)
- [x] T505 [US2] `--contracts` + `.tcadvisor/external-contracts.json` loading and hint matching
- [x] T506 [US2] Integration test for contract hints; README + tc-coverage skill docs

## Phase 3: Evaluate
- [ ] T507 Benchmark (spec 004 pairs) before/after; record in `specs/005-external-api-cases/results.md`
- [ ] T508 Full test suite, review diff, commit
