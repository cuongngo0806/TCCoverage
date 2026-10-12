# Results: spec 012

## Tests

`python3 -m pytest -q`: 211 passed, 2 skipped (both skips predate this spec: GitNexus / codegraph binaries absent).
New: `tests/unit/test_run_folder.py`, `test_automake.py`, `test_build_log.py`, `test_variants.py`,
`tests/integration/test_us12_reports.py`, `test_us12_autotools.py`, `test_us12_profile.py`,
`test_us12_evidence_paste.py` (Chromium via Playwright when installed; static part always), and US6 checks in
`test_config_init.py`. The session l10n gate reports no untranslated sentence.

## Success criteria

| SC | Result |
|---|---|
| SC-001 run folders | 3 analyses (same change twice in one second + working tree) → 3 folders, first folder byte-identical afterwards, `git status --porcelain` empty (`test_us12_reports.py`); same by hand on a fresh autotools module (`…-f541f31_fa93b03`, `…-2`) |
| SC-002 products as targets | autotools fixture: every impacted caller names its product (`libremote`, `remoteapp`): 3/3 nodes, 100 % |
| SC-003 variant filter | fixture, variant `basic` only: 6/6 cases on FEATURE_X-only code moved (hop 0 under `#ifdef`, callers reached only through it, `pro.c` change); union `basic,pro`: 0 moved; `#if UNKNOWN_LIMIT > 2`: kept + flag; CMake fixture: 4/4 cases under an off `#ifdef` moved, 0 built ones |
| SC-004 confirmation < 2 min | dialog asks 1 keep/name question per variant + only switches the build does not reveal (0 on the fixture); timing with real users still to do |
| SC-005 new user < 30 min | `docs/linux-yocto.md` written; walkthrough with a new team member still to do |
| SC-006 paste evidence | one paste → inline image (≤ 480 px), full-size viewer, printed, survives Save + offline reopen (`test_us12_evidence_paste.py`, Chromium) |
| SC-007 no regression | see below |
| SC-008 settings | 17 extension settings: 6 were config keys, 1 lives in the HTML report, 3 editor-only, 7 restored (+ explicit keys for every former `extraArgs` option); unknown keys rejected with the closest name |

## Benchmarks (SC-007)

- `scripts/eval_real_project.py --quiet`: `EVAL leveldb@bb74ef7: providers run=clang; all expectations hold`.
- `scripts/seeded_regressions.py` (this branch):
  leveldb dev 12/12 victims, 12/12 corners, MRR 0.397; holdout 10/10, 10/10, MRR 0.348; yaml-cpp 9/9, 9/9, MRR 0.365.
- Same benchmark on the commit before spec 012 (`85d0007`): identical per scenario (cases, victim rank, victims,
  corners, P1) and in every summary line — the 0.402 → 0.397 dev MRR difference against spec 010's table predates
  this spec. Benchmarks run without a build profile, so the variant filter never applies to them.
