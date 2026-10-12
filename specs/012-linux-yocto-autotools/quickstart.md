# Quickstart / validation: spec 012

Prerequisites (Linux): `sudo apt install python3-venv git clang cmake autoconf automake libtool make`;
`pip install -e '.[dev]'`.

## V1 — Run folders (US1, SC-001)

```bash
cd <analysed repo>                  # e.g. the autotools fixture of V2
for i in 1 2 3; do tcadvisor analyze --working-tree --print brief -q | tail -1; done
ls .tcadvisor/reports                # 3 distinct folders + latest
git status --porcelain               # empty
```
Expected: three `report: …/.tcadvisor/reports/<stamp>-working-tree[-N]` lines, earlier folders unchanged
(compare `sha256sum` before/after).

## V2 — Autotools module (US2, SC-002)

Fixture `tests/conftest.py::autotools_project`: `configure.ac` with `AM_CONDITIONAL([FEATURE_X], …)`,
`AC_ARG_ENABLE([feature-x])`; `Makefile.am` `SUBDIRS = lib app`; `lib/Makefile.am` `lib_LTLIBRARIES =
libremote.la`, `if FEATURE_X libremote_la_SOURCES += pro.c endif`; `app/Makefile.am` `bin_PROGRAMS = remoteapp`,
`remoteapp_LDADD = ../lib/libremote.la`.

```bash
autoreconf -fi && ./configure --disable-feature-x && make V=1 > build-basic.log 2>&1
tcadvisor compile-db --from-log build-basic.log --variant basic
tcadvisor analyze --commit-range HEAD~1..HEAD --print brief
```
Expected: cases on callers in `app/` name target `remoteapp`, lib callers name `libremote`; no "reduced accuracy".
Without a compile DB: one note with the `compile-db --from-log` command and the uncertainty flag.

## V3 — Profile and filtering (US3, SC-003)

```bash
make distclean && ./configure --enable-feature-x && make V=1 > build-pro.log 2>&1
tcadvisor compile-db --from-log build-pro.log --variant pro
printf 'y\n' | script -qc 'tcadvisor profile' /dev/null   # or: tcadvisor profile --save profile.json
# edit lib/pro.c (only built with FEATURE_X) and a line under #ifdef FEATURE_X in lib/remote.c
tcadvisor analyze --working-tree --variants basic --print brief   # cases moved to "not built" (count > 0)
tcadvisor analyze --working-tree --print brief                    # basic+pro: same cases in the main list
tcadvisor analyze --working-tree --no-variant-filter --print brief
```
Also: change under `#if SOME_UNKNOWN > 2` ⇒ case kept + `build_config_incomplete_macro` flag; edit
`lib/Makefile.am` ⇒ build-configuration change + profile state `stale`; non-TTY without profile ⇒ note, nothing
filtered.

## V4 — Docs (US4, SC-005)

Follow `docs/linux-yocto.md` on a clean container; every command in the main path is a Linux shell command;
`scripts/l10n_check.py` passes.

## V5 — Paste evidence (US5, SC-006)

`python3 -m pytest -q tests/integration/test_us12_evidence_paste.py` (Playwright, Chromium at
`/opt/pw-browsers` or system): dispatches a `paste` event with a PNG `File` on a case's evidence zone, saves,
reopens the saved HTML offline ⇒ `img.evimg` present with `naturalWidth > 0`, overlay opens on click, print
media shows it.

## V6 — No regression (SC-007)

```bash
python3 -m pytest -q
python3 scripts/eval_real_project.py --quiet
python3 scripts/seeded_regressions.py
```
Expected: same numbers as on `main` (no profile ⇒ no filtering on CMake benchmarks).
