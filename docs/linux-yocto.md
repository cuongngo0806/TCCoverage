# tcadvisor on Linux for Yocto / autotools modules

This guide covers modules built with **autotools** (`configure.ac` + `Makefile.am`), usually by a **Yocto** recipe.
Commands are for a Linux build host or the Yocto build container. CMake modules are covered in the
[README](../README.md); the report, the AI skill and the build profile work the same for both.

The tool only **reads**: the module's source, its `configure.ac` / `Makefile.am`, and the build logs and
`config.status` / `config.h` of builds you already ran. It never runs `bitbake`, `configure` or `make`, and it
never edits the module (its own files live in `<module>/.tcadvisor/`, git-ignored locally).

## 1. Install (once per host)

```bash
sudo apt install -y python3-venv python3-pip git          # Debian / Ubuntu; Fedora: dnf install python3 git
python3 -m venv ~/.venvs/tcadvisor
~/.venvs/tcadvisor/bin/pip install "git+https://github.com/cuongngo0806/tccoverage"
echo 'export PATH="$HOME/.venvs/tcadvisor/bin:$PATH"' >> ~/.bashrc && . ~/.bashrc
tcadvisor --version                                      # 0.2.0 or newer
# update later: ~/.venvs/tcadvisor/bin/pip install -U "git+…"; then `tcadvisor init --upgrade` in each workspace
# impact source (default): needs Node.js >= 18
npm i -g @colbymchenry/codegraph
```

No system clang is needed (libclang comes with the Python package). Without Node.js, set `"graph": "clang"` in
the config (built-in graph; then a compile database is required).

## 2. The module's workspace

The workspace is the git repository of the module, e.g.

| How the source is checked out | Workspace (`--repo`) | Yocto `${S}` |
|---|---|---|
| `devtool modify <recipe>` | `<build>/workspace/sources/<recipe>` | the same directory |
| `externalsrc` (`EXTERNALSRC = "/path/module"`) | `/path/module` | the same directory |
| plain `git clone` next to the build | your clone | `${WORKDIR}/git` (different: map it, step 3) |

```bash
cd <workspace> && tcadvisor init        # writes .tcadvisor/config.json and the AI skill; prints next steps
git add .tcadvisor/config.json .claude .github && git commit -m "tcadvisor setup"   # optional, keeps --working-tree clean
```

Reports (`.tcadvisor/reports/`) and generated compile databases (`.tcadvisor/build/`) are already git-ignored
locally; the config and the skill files are yours to commit (then the whole team shares the settings).

## 3. Compile flags: from the recipe's build log (once per variant)

The compile database (`compile_commands.json`) gives exact flags, include paths and defines. Yocto already keeps
every compiler command line of the last build in the recipe's `log.do_compile` (OE's `autotools.bbclass`
configures with `--disable-silent-rules`):

```bash
bitbake -c compile -f <recipe>                                   # if the recipe came from sstate (no log yet)
WORKDIR=$(bitbake -e <recipe> | sed -n 's/^WORKDIR="\(.*\)"/\1/p')
tcadvisor compile-db --repo . --from-log "$WORKDIR/temp/log.do_compile" --variant <name>
```

- `<name>`: the build variant this log belongs to (e.g. `imx8-basic`). It is recorded in the build profile.
- Source not in the workspace (plain clone): add `--src "$(bitbake -e <recipe> | sed -n 's/^S="\(.*\)"/\1/p')"`;
  without it the tool maps the longest path whose tail exists in the workspace and prints the mapping.
- Run it on the host that has the Yocto `tmp/` directory: include paths into the recipe sysroot must exist.
- Local build instead of Yocto: `autoreconf -fi && mkdir -p b && cd b && ../configure <options> && make V=1 2>&1 |
  tee ../build-<name>.log`, then `--from-log build-<name>.log`.

### The module does not build on the host (target-only headers such as `dlt/dlt.h`)

The tool needs the compiler **command lines**, not a successful build. In order of accuracy:

1. **Yocto `log.do_compile`** (above): the real cross build, include paths into the recipe sysroot.
2. **Yocto SDK** (`bitbake <image> -c populate_sdk`, installed once): `source /opt/<sdk>/environment-setup-*`,
   then configure with the SDK's flags and print the commands without compiling:
   `mkdir -p ../rc-build && cd ../rc-build && <workspace>/configure $CONFIGURE_FLAGS && make -n V=1 > dry.log`.
   Headers like `dlt/dlt.h` resolve from the SDK sysroot.
3. **Host configure + dry run**, when `configure` passes on the host but `make` stops at a missing header:
   `make -n V=1 > dry.log` (prints every compile command, compiles nothing) or `make -k V=1 > keep.log 2>&1`
   (keeps going after errors). Then `tcadvisor compile-db --from-log dry.log --variant <name>`. Flags and defines
   are exact; files that include the missing headers are parsed with errors, which only lowers accuracy around
   those headers.
4. **No configure at all**: skip the compile database. With the default codegraph impact source the analysis
   still runs (marked *reduced accuracy*), and products / sources still come from `Makefile.am`.

Keep build directories outside the workspace (`../rc-build`), or the build files show up as changes in
`--working-tree` analyses.
- Other recorders work too (`bear -- make`, `compiledb make`): point a variant's `compile_db` at their output.

Output: `.tcadvisor/build/<name>/compile_commands.json`. Re-run the command after the build flags change.

- Cross compilers (`arm-oe-linux-gnueabi-g++`, `aarch64-poky-linux-gcc`, …): the code is parsed for that target
  (`--target=<triple>`, ARM flags and `--sysroot` kept), so sysroot headers such as `dlt/dlt.h` resolve as in the
  real build.
- The Yocto build may compile another revision than your workspace (`${S}` is a copy). A source your
  `Makefile.am` lists but the log does not compile is parsed with the flags of a sibling source of the same
  product (run note); re-run `compile-db` after a new `bitbake -c compile` for exact flags.

## 4. Build variants: confirm once

One module is often built for several machines / product types / configure options. Build each variant you ship
once (another `MACHINE`, `PACKAGECONFIG`, `EXTRA_OECONF`), record its log with `compile-db --variant`, then:

```bash
tcadvisor profile            # interactive: shows each variant and the switch values found in its build
```

Switch values come from the build itself: automake conditionals (`config.status`), the `configure` command line
(`config.log`), `config.h` (`#define` / `#undef`) and the `-D` / `-U` flags of the variant's compile database. You
answer which variants are really built / shipped, their names, and values the build does not reveal. The answer
is saved in `.tcadvisor/config.json` (`build` key).

From then on, a case whose code is provably **not compiled in any confirmed variant** (a source only built
`if FEATURE_X` in `Makefile.am`, a source absent from every variant's build, an `#ifdef` branch that is off in all
of them, or a caller only reached through such code) moves to the report section *Not built in the confirmed
variants*, with the excluding condition. Nothing is deleted (report.json keeps it), and a condition the tool
cannot evaluate keeps the case with an uncertainty flag.

- AI assistant: the `tc-coverage` skill asks you the same questions in chat (`profile --detect --json`, then
  `profile --save -`).
- Non-interactive runs (CI) without a confirmed profile never block: nothing is filtered and a note says so.
- One run for one variant: `--variants imx8-basic`; ignore the profile: `--no-variant-filter`.
- `tcadvisor profile --show` prints the profile; `stale` means `configure.ac` / `Makefile.am` changed since it was
  confirmed — run `tcadvisor profile` again.

## 5. Analyse a change

```bash
tcadvisor analyze --commit-range HEAD~1..HEAD        # or --working-tree, or --symbols remote_send
# report: <workspace>/.tcadvisor/reports/20261012-101530-a1b2c3d_e4f5a6b/
xdg-open .tcadvisor/reports/latest/report.html
```

Or in Claude Code / Copilot: `/tc-coverage HEAD~1..HEAD`. Cases name the autotools products (`bin_PROGRAMS`,
`lib_LTLIBRARIES`, …) that contain the impacted code; `check_*` products count as unit tests (left out unless
`include_tests`). Every analysis writes a new run folder; the newest is `.tcadvisor/reports/latest`. Results filled
in the latest report (verdict, comment, pasted screenshots) carry over to the next run by case key.

Cleaning old runs: `ls .tcadvisor/reports` and remove the folders you no longer need (the tool never deletes them).

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `compile-db`: *no compiler command found* | the build used silent rules: add `EXTRA_OEMAKE += "V=1"` (Yocto) or `make V=1`; or the recipe came from sstate: `bitbake -c compile -f <recipe>` |
| *N source(s) not found in the workspace* | pass `--src <${S}>` or `--map OLD=NEW` |
| `analyze` exit 1 naming `tcadvisor compile-db` | `graph: clang` needs the compile database: step 3 |
| *reduced accuracy* note | no compile database: codegraph still traces impact, defines / headers use fallback flags |
| `build_description_unresolved` flags | `Makefile.am` uses `$(shell …)`, variables set by `configure`, or files generated by m4: those products / sources are not mapped; check them by hand |
| profile `stale` | `tcadvisor profile` again |
| report not where expected | `tcadvisor config` (key `output_dir`) and the last line `report: …` of `analyze` |
