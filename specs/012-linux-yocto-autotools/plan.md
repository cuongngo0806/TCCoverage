# Implementation Plan: Linux-first, Yocto/autotools, build-variant profile, per-run reports, image evidence

**Branch**: `claude/project-improvements-post-test-saoygs` | **Date**: 2026-10-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-linux-yocto-autotools/spec.md`

## Summary

Five field-test fixes. (1) Reports move into `<repo>/.tcadvisor/reports/<stamp>-<change>/` (one immutable run folder
per analysis, `latest` symlink, `.git/info/exclude` entry) — `pipeline.run` drops its "outside the repo" check for
the output dir, `report/render.write` stops overwriting. (2) Autotools becomes a second build model next to CMake:
new `index/automake.py` reads `configure.ac` / `Makefile.am` (products, sources, `if` conditionals, `SUBDIRS`) and
returns the same `TargetModel` the CMake File API reader returns; new `index/build_log.py` turns a Yocto
`log.do_compile` (or any make/libtool build log) into `compile_commands.json`, so no extra tool is needed on the
build host. (3) A build profile (`build` key in `.tcadvisor/config.json`) is detected (`index/variants.py`),
confirmed once (`tcadvisor profile`, interactive prompt on first `analyze` in a TTY, AI front-ends via
`profile --detect --json` / `--save`), and applied after case assembly (`classify/variants.py`): cases whose
evidence is provably not built in any confirmed variant move to `not_built`. (4) README + new
`docs/linux-yocto.md` become the Linux-first guide; the packaged skill/agents/prompts follow. (5) The HTML report
gets clipboard paste, inline images at readable size, a full-size viewer and print styles (`report/html.py`).
(6) Settings that only the removed VS Code extension could set (AI verification binary / models / budget, impact-
source binary, extra analysis options) become config keys with flag > config > default precedence; `init` writes
all keys, unknown keys are rejected, `tcadvisor config` shows value + source.

## Technical Context

**Language/Version**: Python ≥ 3.10 (existing package)

**Primary Dependencies**: libclang wheel, git CLI (existing); no new dependency. Autotools files are parsed by the
tool itself (no `automake` run); `bear` / `compiledb` are documented alternatives, never required.

**Storage**: files — `<repo>/.tcadvisor/config.json` (new `build` key), `<repo>/.tcadvisor/reports/<run>/`
(report.* as today), generated `compile_commands.json` under `<repo>/.tcadvisor/build/<variant>/`.

**Testing**: pytest — unit (`automake` parser, build-log parser, `#if` evaluator, run-folder naming, profile
validation), integration on a new synthetic autotools fixture (`tests/conftest.py`: `autoreconf -i && ./configure
&& make V=1` with two variants), HTML paste via the existing JS-free assertions on the rendered page plus one
Playwright check (Chromium is available); benchmarks `scripts/eval_real_project.py`, `scripts/seeded_regressions.py`
unchanged (CMake path).

**Target Platform**: Linux (primary: Ubuntu/Debian build hosts, Yocto build containers); macOS / Windows
best-effort.

**Project Type**: CLI + library with AI front-ends (skill, agents, prompts) and a self-contained HTML report.

**Performance Goals**: autotools model + build-log conversion ≤ 2 s on a 300-source module; variant filter ≤ 5 %
of analysis time; first-run confirmation ≤ 2 min of user time (SC-004).

**Constraints**: constitution 1.4.0 — evidence per case, deterministic, uncertainty never dropped, local-first,
tool never runs `configure`/`make`/`bitbake`, writes only inside `<repo>/.tcadvisor/`.

**Scale/Scope**: modules up to ~1M lines, ≤ 8 variants per profile, ≤ 200 `Makefile.am` per module.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status |
|---|---|
| I Case list only | ✅ no test code; new sections (`not_built`, profile note) are case metadata |
| II Evidence | ✅ autotools products give the same file→target evidence as CMake; filtered cases keep their evidence and add the excluding condition |
| III Deterministic first | ✅ parsers + expression evaluator; the AI front-ends only relay the confirmation question, the saved profile is plain data |
| IV Uncertainty | ✅ unparsable `Makefile.am` constructs, `m4` macros, unevaluable `#if` → `uncertainty_flags` (`build_description_unresolved`, existing `build_config_incomplete_macro`); nothing is filtered on doubt |
| V Cost aware | ✅ parsers are linear; generated compile DB cached by log hash; run cache key gains the profile hash |
| VI Local first | ✅ nothing leaves the machine |
| VII Recall over volume | ✅ filter = union of variants, provable-only; SC-003 requires 0 built cases removed; benchmarks gate |
| VIII Fixed scope | ✅ never runs builds; writes only the tool's locally-ignored folder (constitution 1.4.0 workspace footprint) |
| IX English / report language | ✅ new report sentences get `vi_*.py` entries (`scripts/l10n_check.py`) |

Post-design re-check: no violation (see research §R7 for the recall argument).

## Project Structure

### Documentation (this feature)

```text
specs/012-linux-yocto-autotools/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── cli.md           # new/changed commands and flags
│   ├── config-build-profile.schema.json
│   └── report-additions.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/tcadvisor/
├── config.py                 # + build key, restored extension settings (US6), unknown-key check; output_dir default → .tcadvisor/reports
├── pipeline.py               # run folder creation, build-system dispatch, variant filter stage, profile hash in run key
├── index/
│   ├── automake.py           # NEW configure.ac + Makefile.am → TargetModel (+ conditionals, unresolved constructs)
│   ├── build_log.py          # NEW make / libtool / Yocto log.do_compile → compile_commands.json
│   ├── variants.py           # NEW detect switches + proposed variants (configure.ac, config.log, config.h, cdb defines)
│   ├── cmake_targets.py      # unchanged API (TargetModel shared)
│   └── clang_index.py        # C headers parsed as C when the owning TU is C
├── classify/variants.py      # NEW #if evaluator + case filter → not_built
├── report/
│   ├── render.py             # run folder write, latest pointer, no overwrite/backup path; not_built section
│   ├── html.py               # paste, inline images, lightbox, print CSS; not_built section
│   └── l10n/vi_*.py          # new sentences
├── cli/main.py               # profile subcommand, compile-db subcommand, --variants/--no-variant-filter, TTY prompt
└── integrations/             # skill / agents / prompts: Linux + autotools + profile confirmation + latest run
docs/linux-yocto.md           # NEW Linux / Yocto / autotools guide
README.md                     # Linux-first install + usage
tests/conftest.py             # + autotools fixture
tests/unit/test_automake.py, test_build_log.py, test_variants.py, test_run_folder.py
tests/integration/test_us12_autotools.py, test_us12_profile.py, test_us12_reports.py, test_us12_evidence_paste.py
specs/001-change-impact-test-advisor/contracts/output-schema.json   # + not_built, run, build_profile
```

**Structure Decision**: single package as today; three new index modules and one classify module, each a set of
plain functions + dataclasses, mirroring `index/cmake_targets.py` and `classify/edits.py`.

## Complexity Tracking

No constitution violation to justify.
