# Tasks: Linux-first, Yocto/autotools, build-variant profile, per-run reports, image evidence

**Input**: design documents in `specs/012-linux-yocto-autotools/` (plan.md, spec.md, research.md, data-model.md,
contracts/, quickstart.md). Constitution 1.4.0.

**Tests**: included — project rule: every behaviour change lands with pytest coverage (CLAUDE.md, quickstart V1–V6).

Format: `- [ ] Txxx [P?] [USn?] description with file path`. [P] = different files, no open dependency.

## Phase 1: Setup

- [ ] T001 Add the synthetic autotools fixture builder `autotools_project` to tests/conftest.py: `configure.ac` with `AC_ARG_ENABLE([feature-x])`, `AM_CONDITIONAL([FEATURE_X], [test "x$enable_feature_x" = xyes])`, `AC_CONFIG_HEADERS([config.h])`, `AC_DEFINE` of `HAVE_FEATURE_X` when enabled; top `Makefile.am` `SUBDIRS = lib app`; `lib/Makefile.am` `lib_LTLIBRARIES = libremote.la`, `libremote_la_SOURCES = remote.c remote.h`, `if FEATURE_X` / `libremote_la_SOURCES += pro.c` / `endif`; `app/Makefile.am` `bin_PROGRAMS = remoteapp`, `remoteapp_SOURCES = main.c`, `remoteapp_LDADD = ../lib/libremote.la`; `remote.c` has a block under `#ifdef HAVE_FEATURE_X`; git repo with an initial commit; skip the fixture when `autoreconf`/`libtoolize` are missing
- [ ] T002 [P] Install `autoconf automake libtool make` in both jobs of .github/workflows/ci.yml (apt line next to `clang cmake ninja-build`)
- [ ] T003 [P] Move `exclude_index_dir` from src/tcadvisor/graph/providers/base.py into a shared helper `git_exclude(repo, entry)` in src/tcadvisor/ingest/git.py and call it from the provider (behaviour unchanged)

## Phase 2: Foundational (blocks US1–US3)

- [ ] T004 Extend src/tcadvisor/config.py: default `output_dir` = `<repo>/.tcadvisor/reports` (`default_output_dir`), drop the "must resolve outside the repository" rule for `output_dir`; add key `build` validated against contracts/config-build-profile.schema.json rules (`system` ∈ `auto|cmake|autotools`; `variants` 1–16 items, `name` matches `^[A-Za-z0-9._-]+$` and is unique; `values` map to string|bool|null; `value_source` ∈ `build|user`); add `build_system` resolution (flag > config > `auto`)
- [ ] T005 In src/tcadvisor/pipeline.py remove the `--output-dir` part of the `_is_within` check (keep `--cache-dir`), add `Options.build_system`, `Options.variants`, `Options.variant_filter`
- [ ] T006 Extend specs/001-change-impact-test-advisor/contracts/output-schema.json with optional `run`, `build_model`, `build_profile`, `not_built`, `not_built_changes` (shapes in contracts/report-additions.md) and the uncertainty category `build_description_unresolved`
- [ ] T007 Add `UncertaintyFlag` category `build_description_unresolved` to src/tcadvisor/models.py and its vi text to src/tcadvisor/report/l10n/vi_notes.py

**Checkpoint**: config + schema accept the new keys; `python3 -m pytest -q` still green.

## Phase 3: US1 — Each run leaves its own report inside the workspace (P1) 🎯 MVP

Independent test: quickstart V1 (3 runs ⇒ 3 folders + `latest`, earlier files unchanged, `git status` clean).

- [ ] T008 [P] [US1] Unit tests tests/unit/test_run_folder.py: name `<YYYYMMDD-HHMMSS>-<change>` for range (`a1b2c3d_e4f5a6b`), `working-tree`, `symbols`; collision ⇒ `-2`, `-3`; `latest` symlink replaced atomically; `latest.txt` fallback when `os.symlink` raises
- [ ] T009 [US1] Implement `new_run_folder(root, change, now)` (exclusive `mkdir`, suffix on `FileExistsError`) and `update_latest(root, folder)` (temp symlink + `os.replace`, else `latest.txt`) in src/tcadvisor/report/render.py
- [ ] T010 [US1] In src/tcadvisor/report/render.py `write_outputs`: write only into the given run folder, remove the `report.results-backup-*` copy path for new runs (keep it for `same_analysis=True` re-renders into an existing folder), record `run` in the report
- [ ] T011 [US1] In src/tcadvisor/cli/main.py `_analyze`: create the run folder under `cfg["output_dir"]`, call `git_exclude(repo, ".tcadvisor/reports/")` when the root is inside the repo, write there, update `latest`, print `REPORT <run folder>` and as last line `report: <run folder>` in every `--print` mode; `--output-dir` help text = report root
- [ ] T011a [US1] Read-only workspace / run folder cannot be created ⇒ `UsageError` naming the folder and the `output_dir` override, no fallback location (src/tcadvisor/cli/main.py), with a test in tests/unit/test_run_folder.py
- [ ] T012 [US1] Default `--previous-report` in src/tcadvisor/cli/main.py: when omitted and `latest/report.html` holds test results, carry them over (note in run notes); explicit flag still wins
- [ ] T013 [US1] `verify-pack` default report path = `<output_dir>/latest/report.json` in src/tcadvisor/cli/main.py (~line 266); `verify`/`results`/`render` keep their required path argument (help text mentions `latest/`)
- [ ] T014 [US1] `tcadvisor init` in src/tcadvisor/integrations/init.py: accept an `--output-dir` inside the repo, add `.tcadvisor/reports/` to `.git/info/exclude`; update `--output-dir` help in src/tcadvisor/cli/main.py
- [ ] T015 [US1] Integration test tests/integration/test_us12_reports.py on the CMake fixture: three analyses ⇒ three folders, sha256 of first folder unchanged, `latest` = newest, `git status --porcelain` empty, results carried over by default from `latest`
- [ ] T016 [US1] Update existing tests that assume a fixed output dir or the outside-repo rule (tests/integration/test_config_init.py, tests/integration/test_us6_report.py) to the run-folder layout

**Checkpoint**: US1 complete and shippable alone.

## Phase 4: US2 — Analyse a Yocto-built autotools module (P1)

Independent test: quickstart V2 (cases name `remoteapp` / `libremote`; missing compile DB ⇒ one note + flag).

- [ ] T017 [P] [US2] Unit tests tests/unit/test_automake.py: continuations, comments, `$(VAR)`/`@VAR@` expansion, all primaries in research R3, default `<canon>.c`, `_LDADD`/`_LIBADD` internal deps, `SUBDIRS` recursion incl. `SUBDIRS` under an `if COND` (whole directory tagged), `if/else/endif` (nested) tagging, `include`, `check_*` ⇒ `is_test`, `$(shell …)` ⇒ unresolved with file:line, duplicate product names ⇒ `dir/` prefix
- [ ] T018 [P] [US2] Unit tests tests/unit/test_build_log.py: gcc/clang/cross `arm-poky-linux-gnueabi-gcc` lines, `libtool: compile:` lines, `make[N]: Entering directory` tracking, `--src/--build` remap and auto prefix map, non-compile lines ignored, empty log ⇒ error message naming `V=1` / `--disable-silent-rules`
- [ ] T019 [US2] Implement src/tcadvisor/index/automake.py: `load_automake_model(repo) -> BuildModel` (data-model.md: `BuildProduct` with `name`, `type` program|ltlibrary|library, `sources`, `dependencies`, per-source `conditions`, `defined_at`, `is_test`; `BuildModel.system`, `targets: TargetModel`, `unresolved`, `build_files`, `fingerprint` = sha256 of `configure.ac` + all `*.am`), reading `AC_CONFIG_FILES`, `AM_CONDITIONAL`, `AC_ARG_ENABLE/WITH`, `AC_DEFINE`, `AC_CONFIG_HEADERS` from configure.ac
- [ ] T020 [US2] Implement src/tcadvisor/index/build_log.py: `parse_build_log(text, src_map) -> list[dict]` + `write_compile_db(entries, out)`; cache by log sha256
- [ ] T021 [US2] Add `tcadvisor compile-db --from-log LOG [--repo] [--src] [--build] [--variant] [--out]` to src/tcadvisor/cli/main.py per contracts/cli.md (default out `<repo>/.tcadvisor/build/<variant|default>/compile_commands.json`, exit 1 when nothing found, updates the variant's `compile_db`/`build_log`/`log_sha256` when `--variant`)
- [ ] T022 [US2] Build-system dispatch in src/tcadvisor/pipeline.py `_run`: `auto` ⇒ `CMakeLists.txt` → `load_target_model`, `configure.ac` → `load_automake_model`; compile DB from the profile's variant(s) (first variant for indexing, all for filtering) else `build_dir`; missing compile DB ⇒ note naming the exact `tcadvisor compile-db --from-log …` command for this module + a reduced-accuracy uncertainty flag of category `build_description_unresolved` (construct `no compile database`); `unresolved` ⇒ `build_description_unresolved` flags
- [ ] T023 [US2] Build-file changes: generalise `is_cmake` to `is_build_file` (`configure.ac`, `*.am`, `*.m4`, `*.bb`, `*.bbappend`, CMake files) in src/tcadvisor/classify/rules.py and the file filter in src/tcadvisor/ingest/changes.py (~line 500); `targets_for_cmake_file` equivalent for `Makefile.am` dirs in src/tcadvisor/index/automake.py
- [ ] T024 [US2] Sources listed by no product ⇒ `out_of_scope` entry "not built by any product" in src/tcadvisor/pipeline.py (~line 340); `check_*` product sources follow `is_test_file` scope
- [ ] T025 [US2] Parse C headers as C in src/tcadvisor/index/clang_index.py `parse`: `-x c-header` when every compile command including the header is C (research R8)
- [ ] T026 [US2] Integration test tests/integration/test_us12_autotools.py on `autotools_project`: build with `make V=1`, `compile-db --from-log`, change a lib function ⇒ app caller case names target `remoteapp`, lib case `libremote`; no compile DB ⇒ note + flag; source in no product ⇒ out_of_scope; `Makefile.am` edit ⇒ build-configuration change
- [ ] T027 [US2] Make `--targets` / config `targets` accept autotools product names (validation message in src/tcadvisor/config.py says "build targets / products")

**Checkpoint**: US2 complete; CMake suite unchanged.

## Phase 5: US3 — Confirm the build flow once, filter what is not built (P2)

Independent test: quickstart V3 (variant `basic` only ⇒ FEATURE_X cases in `not_built`; `basic,pro` ⇒ back in the main list; unknown macro ⇒ kept + flag).

- [ ] T028 [P] [US3] Unit tests tests/unit/test_variants.py: evaluator (`defined X`, `defined(X)`, ints dec/hex/suffix, `! && || == != < <= > >= + -`, parentheses, three-valued unknown, function-like macro ⇒ unknown, `#ifdef/#ifndef` normalisation); switch detection from configure.ac / `config.status` (`S["X_TRUE"]=""` ⇒ true, `"#"` ⇒ false) / `config.log` `$ ./configure` line / `config.h` / compile-DB `-D`
- [ ] T029 [US3] Implement src/tcadvisor/index/variants.py: `detect(repo, model, build_dirs) -> Proposal` (switches with `name`, `kind` am_conditional|configure_option|macro, `declared_at`; variants with `name`, `compile_db`, `build_log`, `build_dir`, `values`, `value_source`; search places from research R4 incl. `$BUILDDIR/tmp*/work/*/<recipe>/*/` when `BUILDDIR` is set; fallback single `default` variant)
- [ ] T030 [US3] Implement src/tcadvisor/classify/variants.py: `evaluate(cond, values) -> True|False|None`; `location_built(file, line, variant, model, cdb, include_scan) -> (bool|None, reason)`; `apply_profile(cases, changes, profile) -> (kept, not_built, not_built_changes, flags)` — a case moves only if every evidence location is not built in every selected variant; `None` anywhere ⇒ kept + `build_config_incomplete_macro` flag; `excluded_by` entries `{variant, reason: source_not_in_product|conditional_dir|preprocessor, condition, where}`
- [ ] T031 [US3] Collect enclosing `#if` chains for impacted-caller evidence lines (reuse `conditional_stack` in src/tcadvisor/ingest/changes.py) and pass them to the filter stage in src/tcadvisor/pipeline.py after case assembly, before the evidence gate output; add `build_profile` state (`confirmed|stale|absent|overridden`) and profile hash to the run-cache key
- [ ] T032 [US3] `tcadvisor profile` (interactive, `--detect --json`, `--save FILE|-`, `--show`) in src/tcadvisor/cli/main.py per contracts/cli.md; prompts: keep/rename/remove each variant, set unset switch values, save with `confirmed_at` + `fingerprint`
- [ ] T033 [US3] First-run prompt in `_analyze` (src/tcadvisor/cli/main.py): TTY + no confirmed profile ⇒ run the `profile` flow then analyse; non-TTY ⇒ note "no confirmed build profile: nothing filtered; run 'tcadvisor profile' …"; `--variants A,B` and `--no-variant-filter` overrides; unknown variant name ⇒ warn (TTY: ask, batch: ignore)
- [ ] T034 [US3] Stale profile: fingerprint differs or a build file changed in the analysed diff ⇒ state `stale` + note in src/tcadvisor/pipeline.py
- [ ] T035 [US3] Render `not_built` / `not_built_changes` and the profile header line in src/tcadvisor/report/render.py (md + brief `not built (profile): N`) and src/tcadvisor/report/html.py (collapsible section with condition and variant); vi entries in src/tcadvisor/report/l10n/vi_ui.py / vi_html.py / vi_notes.py
- [ ] T036 [US3] Integration test tests/integration/test_us12_profile.py on `autotools_project` built twice (`basic`, `pro`): `profile --save`; edits in `lib/pro.c` and under `#ifdef HAVE_FEATURE_X` ⇒ moved with `basic`; kept with `basic,pro`; `#if UNKNOWN_X > 2` ⇒ kept + flag; non-TTY without profile ⇒ nothing filtered + note; `Makefile.am` edit ⇒ `stale`; report.json validates against the extended schema
- [ ] T037 [US3] Same filter for CMake projects (variant = compile DB; source not in that DB and not included by a built TU ⇒ not built) with a test case in tests/integration/test_us12_profile.py on the CMake fixture

## Phase 6: US4 — Linux-first installation and usage guide (P2)

Independent test: quickstart V4 (guide followed on a clean Linux container).

- [ ] T038 [P] [US4] Rewrite README.md "Install" + "Quick start" Linux-first (apt packages, venv, `pip install -e .`, Node only for codegraph), config table: `output_dir` default `.tcadvisor/reports`, new `build` key; "Test report" section: run folders, `latest`, no backup copies; best-effort note for macOS/Windows
- [ ] T039 [P] [US4] New docs/linux-yocto.md: module source (`devtool modify`, externalsrc, plain checkout), per-`MACHINE` `bitbake -c compile <recipe>`, `tcadvisor compile-db --from-log $BUILDDIR/tmp/work/<arch>/<recipe>/<ver>/temp/log.do_compile --src … --variant …`, local build `make V=1 2>&1 | tee build.log`, `bear`/`compiledb` alternatives, `tcadvisor profile`, analyse, open `.tcadvisor/reports/latest/report.html`, cleaning old runs, troubleshooting (silent rules, path mapping)
- [ ] T040 [US4] Update packaged front-ends: src/tcadvisor/integrations/skills/tc-coverage/SKILL.md (first run: `profile --detect --json` → ask the user → `profile --save -`; report path from `REPORT` line / `latest`), src/tcadvisor/integrations/claude/agents/*.md, src/tcadvisor/integrations/copilot/*.prompt.md; then `tcadvisor init --repo . --ai claude --force` and delete the generated `.tcadvisor/` (copies test-enforced)
- [ ] T041 [US4] `next_steps` in src/tcadvisor/integrations/init.py: autotools ⇒ `compile-db --from-log …` + `profile`; CMake ⇒ current hint
- [ ] T042 [P] [US4] Update CLAUDE.md layout/commands (spec 012 entry, new modules, `profile`, `compile-db`) and docs/workflow.md report path

## Phase 7: US5 — Paste screenshots as evidence (P3)

Independent test: quickstart V5 (paste ⇒ inline image, survives save/reopen offline, overlay, print).

- [ ] T043 [US5] In src/tcadvisor/report/html.py: evidence zone focusable (`tabindex=0`), `paste` handler reading `clipboardData.items` of kind `file` through the existing add-file path (sha256, size warning), name `pasted-<case>-<YYYYMMDD-HHMMSS>-<n>.<ext>`, `origin: "paste"`; text paste appended to the comment
- [ ] T044 [US5] In src/tcadvisor/report/html.py: image attachments rendered as `img.evimg` (max-width 480 px) in edit and read-only views, click ⇒ full-size overlay (ESC / click closes), `@media print` images at page width and controls hidden
- [ ] T045 [US5] vi strings for the paste hint / overlay in src/tcadvisor/report/l10n/vi_html.py; run scripts/l10n_check.py
- [ ] T046 [US5] Test tests/integration/test_us12_evidence_paste.py (Playwright, `executablePath` `/opt/pw-browsers/chromium` when present, skip if Playwright missing): paste PNG ⇒ inline image; save ⇒ reopen offline ⇒ `naturalWidth > 0`; overlay; print media; also a static assertion that the rendered HTML contains the paste handler (runs without a browser)

## Phase 7b: US6 — Keep every useful setting in the workspace config (P2)

Independent test: config with `verify_model`, `budget_usd`, `graph_bin`, `contracts`, `attachment_warn_mb` ⇒ used by `analyze` (fake `claude` records its arguments) and shown by `tcadvisor config` with source.

- [ ] T050 [P] [US6] Unit tests tests/unit/test_config_keys.py: every new key validated (types/ranges: `budget_usd` > 0, `verify_max_cases` ≥ 1, `verify_parallel` 1–16, `index` ∈ `auto|full|lite`, `format` ∈ `md|json|html|both|all`, `verify_priorities` ⊆ `P1,P2,P3`), unknown key ⇒ `UsageError` with closest match (`difflib.get_close_matches`), precedence flag > config > default
- [ ] T051 [US6] Add keys of FR-026/FR-027/FR-031 (`claude_bin`, `verify_model`, `synth_model`, `budget_usd`, `verify_priorities`, `verify_max_cases`, `verify_parallel`, `graph_bin`, `contracts`, `lessons`, `target_patterns`, `index`, `jobs`, `patterns`, `history`, `flow_max_tus`, `split_threshold`, `attachment_warn_mb`, `cache_dir`, `allow_stale_compile_db`, `format`, `python`) to `DEFAULTS` / `_check` in src/tcadvisor/config.py; reject unknown keys; `resolve()` returns `{key: (value, source)}` for `tcadvisor config`
- [ ] T052 [US6] In src/tcadvisor/cli/main.py change argparse defaults of the matching `analyze` / `verify` / `verify-pack` flags to `None` and fill them from `resolve()`; `_ai_verify` passes `claude_bin`, models, `budget_usd`, priorities, `verify_max_cases`, `verify_parallel` to src/tcadvisor/verify/runner.py `verify`
- [ ] T053 [US6] `tcadvisor config` prints key / value / source table (and `--json`) in src/tcadvisor/cli/main.py
- [ ] T054 [US6] `tcadvisor init` writes every key with its default and `python` = `sys.executable` (src/tcadvisor/integrations/init.py); existing values kept unless `--force`
- [ ] T055 [US6] Skill / agents / prompts read `python` from `tcadvisor config --json` instead of guessing `python`/`python3` (src/tcadvisor/integrations/skills/tc-coverage/SKILL.md, claude/agents/*.md, copilot/*.prompt.md); re-copy into .claude/ as in T040
- [ ] T056 [US6] Integration test tests/integration/test_config_init.py: `init` writes all keys; `ai_verify: claude` with a fake `claude` receives `--model <verify_model>` and `--max-budget-usd <budget_usd>`; `graph_bin` used by the provider; README config table lists every key (test reads the table)
- [ ] T057 [P] [US6] README.md config table grouped (core / build / analysis / AI verification / report) with every key, default and meaning

## Phase 8: Polish & cross-cutting

- [ ] T047 [P] Keep Playwright optional: T046 browser part uses `pytest.importorskip("playwright")`; do not add it to pyproject.toml (no new dependency rule); the static part of T046 always runs
- [ ] T048 Run `python3 -m pytest -q`, `python3 scripts/l10n_check.py`, `python3 scripts/eval_real_project.py --quiet`, `python3 scripts/seeded_regressions.py`; record results (SC-007) in specs/012-linux-yocto-autotools/results.md
- [ ] T049 Measure SC-002 / SC-003 on the autotools fixture (T026/T036 numbers) and, when available, on a real Yocto module from the team; time the first-run confirmation (SC-004) and a fresh-container walkthrough of docs/linux-yocto.md (SC-005); record all in specs/012-linux-yocto-autotools/results.md

## Dependencies

- Phase 1 → Phase 2 → US1 (MVP). US2 needs Phase 2 only. US3 needs US2 (automake model, compile-db) for autotools, T037 only Phase 2. US4 documents US1–US3 (write after them; T038/T039 drafts can start in parallel). US5 needs nothing but Phase 2 (independent of US1–US4).
- US6 needs Phase 2 only (config.py); do it before US3's `build` key work lands in the same file or rebase carefully. US4 docs (T038, T040) should come after US6 so the config table and skill are written once.
- Order: T001–T007 → {US1, US2, US5, US6 in parallel} → US3 → US4 → Polish.

## Parallel examples

- US1: T008 alongside T009 drafting; T015/T016 after T011.
- US2: T017 + T018 (tests) in parallel, then T019 + T020 in parallel (different modules), then T021–T025.
- US3: T028 first, T029 and T030 in parallel, then T031–T035.
- US4: T038, T039, T042 in parallel.
- US5: fully parallel with US1–US3 (only src/tcadvisor/report/html.py; coordinate with T035 which also edits html.py).

## Implementation strategy

1. MVP = Phase 1–2 + US1 (reports in the workspace, never overwritten) — ship.
2. US2 (autotools model + compile-db) — ship; the pilot modules become analysable with targets.
3. US3 (profile + filter) — ship after the recall test (T036) passes.
4. US4 docs + front-ends, US5 paste evidence.
5. Polish: benchmarks must not regress (SC-007) before merge.
