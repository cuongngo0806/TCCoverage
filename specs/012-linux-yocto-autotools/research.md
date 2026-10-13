# Research: spec 012

## R1 — Run folder layout and the "never write into the repo" rule

- **Decision**: default report root `<repo>/.tcadvisor/reports/`; run folder `<YYYYMMDD-HHMMSS>-<change>` where
  `<change>` = `<old7>..<new7>` with `..` → `_` (`a1b2c3d_e4f5a6b`), `working-tree`, or `symbols`; created with
  `mkdir(exist_ok=False)`, on `FileExistsError` append `-2`, `-3`, … (atomic, so two concurrent runs never share a
  folder). `reports/latest` = relative symlink replaced atomically (`os.replace` of a temp symlink); where symlinks
  fail, `reports/latest.txt` holds the folder name. `.tcadvisor/reports/` is appended to `.git/info/exclude` with the
  existing `exclude_index_dir` helper (moved to a shared util). A configured `output_dir` becomes the report root
  (run folders inside it). `verify-pack --out` default stays `<report dir>/verify` = inside the run folder.
- **Rationale**: user request; the `.tcadvisor/` folder already holds config written by `init`; `info/exclude`
  keeps tracked files untouched (Principle VIII). With immutable run folders the `report.results-backup-*` copy is
  no longer needed; `--previous-report` (or the default: the filled `report.html` of `latest`, if any) carries
  results over.
- **Alternatives**: keep `../tcadvisor-report` (rejected by the user); timestamp-only names (not readable);
  UUIDs (unreadable); deleting old runs (spec: never).
- **Cache**: `.tcadvisor-cache` stays next to the repo (not a report; large; shared across runs). Unchanged.

## R2 — Getting a compile database for a Yocto autotools recipe

- **Decision**: built-in converter `tcadvisor compile-db --from-log <log> [--src S --build B] --out <file>` that
  parses compile commands from a make build log: plain `cc/gcc/g++/clang/${CC}` lines and libtool lines
  (`libtool: compile:  <cc> ...`), with `make[N]: Entering directory '…'` tracking for relative paths. Yocto source:
  `${WORKDIR}/temp/log.do_compile` (OE's `autotools.bbclass` configures with `--disable-silent-rules`, so the log
  carries full command lines). Cross-compiler names (`arm-poky-linux-gnueabi-gcc`) are recognised by suffix;
  `--sysroot=` and `-I` into the recipe sysroot are kept (paths exist on the build host). Yocto `${S}`/`${B}` paths
  are mapped to the workspace with `--src`/`--build` (or auto: the longest path prefix whose suffix exists in the
  workspace). Output under `<repo>/.tcadvisor/build/<variant>/compile_commands.json`; profile stores the log path
  and the log hash (re-generated when the log changes).
- **Also accepted**: any existing `compile_commands.json` (`bear -- make`, `compiledb make`, `intercept-build`) via
  `build_dir`/variant `compile_db`. Local builds: documented `make V=1 2>&1 | tee build.log` then `--from-log`.
- **Rationale**: Yocto hosts rarely have `bear`; the log already exists after every `bitbake -c compile`, no
  rebuild and no recipe change; deterministic; no new dependency.
- **Alternatives**: require `bear` (extra install, needs rebuild inside devshell); parse `make -n` (re-runs
  `configure` checks, unreliable with recursive make); `bitbake -e` (environment only, no per-file flags).

## R3 — Reading `configure.ac` + `Makefile.am` without running automake

- **Decision**: own line parser (`index/automake.py`): join `\` continuations, strip comments, expand
  `$(VAR)`/`@VAR@` from variables in the same file (one pass, cycles → unresolved); primaries
  `{bin,sbin,libexec,pkglib,noinst,check,EXTRA}_{PROGRAMS,LTLIBRARIES,LIBRARIES}`; per product
  `<canon>_SOURCES` (+ `nodist_`, `EXTRA_`, default `<canon>.c` when absent), `_LDADD`/`_LIBADD` (internal `.la`/`.a`
  → product dependency); `SUBDIRS` / `DIST_SUBDIRS` recursion; `if COND` / `else` / `endif` nesting recorded per
  assignment (`+=` under a conditional ⇒ sources tagged with the condition); `include file.am` followed. `check_*`
  products are test code (`is_test_file` scope). `configure.ac`: `AC_CONFIG_FILES` (which `Makefile`s exist),
  `AM_CONDITIONAL(NAME, test)`, `AC_ARG_ENABLE/AC_ARG_WITH`, `AC_DEFINE`, `AC_CONFIG_HEADERS`. Anything else used
  in a primary/sources value (`$(shell)`, unknown macros, `m4_include`d fragments) → `uncertainty_flags`
  category `build_description_unresolved` with file:line; the product still exists with the sources that resolved.
- **Product names**: `prog`, `libfoo.la` → shown as `libfoo` (target name in cases), with `dir/` prefix when two
  directories define the same name.
- **Rationale**: automake syntax for these primaries is small and stable; running `automake` would need the right
  autotools versions and writes files into the module (Principle VIII).
- **Alternatives**: parse generated `Makefile` in the build dir (only one variant's view, huge, needs the build
  dir); use the compile DB alone (gives files, not products/link deps).
- **Build-file changes**: `configure.ac`, `Makefile.am`, `*.am`, `*.m4`, `*.bb`/`*.bbappend` changes are classified
  like CMake-file changes today (`classify/rules.py` `is_cmake` → `is_build_file`) and mark the profile stale.

## R4 — Detecting variants and switch values

- **Decision**: `index/variants.py` produces `Switch` items from: `AM_CONDITIONAL` names (values from
  `config.status`: `S["NAME_TRUE"]=""` ⇒ true, `"#"` ⇒ false), `AC_ARG_ENABLE/WITH` (value from the `config.log`
  `$ ./configure …` line), `-D` defines of the variant's compile DB, and `#define`/`#undef` lines of the generated
  `config.h`. A variant = one build directory / compile DB / log (Yocto: one `WORKDIR` per `MACHINE`/recipe
  variant). Proposed variants = every build dir / log the user points at plus those found under conventional
  places (`build*/`, `.tcadvisor/build/*/`, `$BUILDDIR/tmp*/work/*/<recipe>/*/` when `BUILDDIR` is set). Without
  any compile information, one variant `default` is proposed with the switches listed and values unset.
- **Confirmation**: TTY prompt lists build system, variants (name, source, switch count), asks keep/rename/remove,
  then optional manual switch values for unset switches. AI front-ends: `tcadvisor profile --detect --json`
  (proposal), ask the user in chat, `tcadvisor profile --save FILE|-` (validated). Non-TTY without profile ⇒ no
  filter + run note.
- **Rationale**: values come from the real build where possible (deterministic), the user only names variants.
- **Alternatives**: parse Yocto layers / `MACHINE` confs (out of scope, slow, layer-specific); ask the user for every
  switch (too slow for SC-004).

## R5 — Evaluating `#if` per variant

- **Decision**: tiny evaluator in `classify/variants.py` over the existing `SymbolChange.conditions` strings (and the
  same conditions collected for impacted caller lines via `ingest/changes.py` `_conditions_map`): tokens
  `defined(X)`/`defined X`, identifiers, integer literals (dec/hex/suffixes), `! && || == != < <= > >=` `+ -`, `( )`.
  Identifier values: variant defines (cmd line `-D`, then `config.h`); an identifier not known in a variant ⇒
  `unknown` (three-valued logic: `false && unknown = false`, `true || unknown = true`). Function-like macros,
  `__has_include`, character literals ⇒ unknown. `#ifdef X`/`#ifndef X` normalised to `defined`.
- **Rationale**: covers the conditions seen in the pilot modules; three-valued logic keeps the filter provable.
- **Alternatives**: libclang per variant (re-parse cost ×variants); `unifdef` (external tool).

## R6 — Which cases the filter may move

- **Decision**: a location (file, line) is *not built in variant V* when the file is not a source of any product
  active in V (sources under an `if COND` false in V, `SUBDIRS` under a false conditional, or — CMake — not in V's
  compile DB and not a header included by one) or when its enclosing `#if` chain evaluates to false in V. A case is
  moved to `not_built` only if **every** evidence location of the case is not built in **every** confirmed variant;
  the entry keeps the case and adds `excluded_by` (per variant: the condition text and its source). Headers count as
  built when any built TU includes them (include scan). Root changes that are not built get no cases; they are
  listed in `not_built.changes` (never dropped).
- **Rationale**: provable-only + union ⇒ recall cannot drop for built code (SC-003, Principle VII).

## R7 — Recall guard

- Filter runs only with a confirmed profile; benchmarks use no profile ⇒ numbers unchanged (SC-007). New seeded test
  in the autotools fixture: change under `#ifdef FEATURE_X` with variant B only ⇒ moved; A+B ⇒ kept; unknown macro ⇒
  kept + flag.

## R8 — C modules

- C files are already in `CPP_SOURCE_EXT`; headers are forced to `-x c++-header`. Decision: a header is parsed as
  `c-header` when every compile command that includes it is C (`-x c`, `.c` source, `-std=c*`/`gnu*` without `++`).
  Rule texts that say "C++" stay correct for C (they speak about functions/structs).

## R9 — Pasted images in the report

- **Decision**: `paste` listener on each case's evidence drop zone (focusable, `tabindex=0`) reading
  `clipboardData.items` of kind `file` (images and files); name `pasted-<case>-<YYYYMMDD-HHMMSS>-<n>.png`; same
  sha256 / size / warn path as drop. Images shown at max 480 px wide (`.evimg`), click ⇒ full-size overlay (ESC /
  click closes), `@media print` shows images at page width and hides buttons. Text paste ⇒ appended to the comment.
- **Rationale**: one paste (SC-006); report stays a single file (data URIs, as today).
- **Alternatives**: separate `evidence/` folder (breaks single-file sharing; browser cannot write it).

## R10 — Linux-first docs

- README main path: `sudo apt install python3-venv python3-pip git` (libclang comes from the Python wheel;
  `clang cmake autoconf automake libtool make` only to run the test suite) → `python3 -m venv ~/.venvs/tcadvisor
  && ~/.venvs/tcadvisor/bin/pip install -e .`; Node.js only for the codegraph provider. New
  `docs/linux-yocto.md`: workspace from `devtool modify <recipe>` (source in `workspace/sources/<recipe>`) or
  plain checkout; `bitbake -c compile <recipe>` per `MACHINE`; `tcadvisor compile-db --from-log
  $BUILDDIR/tmp/work/<arch>/<recipe>/<ver>/temp/log.do_compile`; `tcadvisor profile`; `analyze`; open
  `.tcadvisor/reports/latest/report.html`; cleaning old runs. Windows/macOS: one best-effort paragraph.
