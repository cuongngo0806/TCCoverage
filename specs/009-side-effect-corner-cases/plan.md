# Implementation Plan: Side-effect and corner-case completeness

**Branch**: `ccr-f43a06ec-6132n5` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

## Summary

Close the gaps the seeded-regression benchmark exposed (victims 8/12, corners 3/12): derive concrete corner cases
from the *shape* of each edit (new module `classify/edits.py`), add lost-side-effect / state-coupling detectors to
the spec 006 pattern stage (`classify/patterns.py`), remove two noise sources (`graph/sources.py`, `classify/rules.py`)
and report test gaps (`pipeline.py`, `report/`). All deterministic, no new dependency, pattern tier ranking.

## Technical Context

**Language/Version**: Python 3.10+ (existing package)
**Primary Dependencies**: libclang wheel (existing), git CLI; no new dependency
**Storage**: N/A (report JSON/MD/HTML; no new cache entries)
**Testing**: pytest (unit for edit shapes / detectors, integration on the synthetic CMake fixture),
`scripts/seeded_regressions.py` (leveldb, network), `scripts/eval_real_project.py`
**Target Platform**: Linux / macOS / Windows developer machines and CI
**Project Type**: CLI + library (with VS Code front-end consuming the report)
**Performance Goals**: ≤ +15 % analysis time on the leveldb eval; ≤ 40 bounded `git grep` per run shared with spec 006
**Constraints**: constitution — evidence per case, deterministic tracing, no source leaves the machine
**Scale/Scope**: per changed symbol ≤ 8 edit hints, ≤ 3 coupling items × ≤ 4 readers

## Constitution Check

| Principle | Status |
|---|---|
| I Case list only | ✅ hints and cases only, no test code |
| II Evidence | ✅ every new case's evidence[0] is the reader symbol (file:line found in code); gate unchanged |
| III Deterministic first | ✅ difflib/token/regex + graph facts; no LLM |
| IV Uncertainty | ✅ reader overflow is stated in the case; textual searches are labelled heuristics in the case text |
| V Cost aware | ✅ shares the spec 006 grep budget; edits.py is pure in-memory |
| VI Local first | ✅ unchanged |
| VII Recall over volume | ✅ goal of the spec; volume controlled by caps and low tier |
| VIII Fixed scope | ✅ |
| IX English | ✅ |

Post-design re-check: no violation.

## Project Structure

```text
src/tcadvisor/
├── ingest/changes.py      # + old_body / new_body (symbol text on both sides) on SymbolChange
├── classify/edits.py      # NEW: edit shapes -> corner hints; parameter input classes
├── classify/rules.py      # use edits.py hints in logic case; removed_guard (P1); inline only in headers
├── classify/patterns.py   # + removed_write, setter_readers, lock_coupling, changed_default, class_consumer
├── classify/cases.py      # PATTERN_LOW_SUBS += new kinds; priority for removed_guard
├── graph/sources.py       # guards: no loops, must add a new identifier
├── pipeline.py            # test_gaps
└── report/{render,html}.py# test gaps in brief / md / html
scripts/seeded_regressions.py
tests/unit/test_edits.py, tests/unit/test_coupling.py, tests/integration/test_us7_side_effects.py
```

**Structure Decision**: single project; extend existing modules, one new module for edit shapes.

## Complexity Tracking

None.
