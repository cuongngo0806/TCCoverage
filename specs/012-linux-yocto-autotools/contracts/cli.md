# CLI contract additions (spec 012)

## `tcadvisor analyze` (changed)

| Flag | Meaning |
|---|---|
| `--output-dir DIR` | report **root**; a new run folder is created inside it (default `<repo>/.tcadvisor/reports`). May be inside the repo. |
| `--build-system auto\|cmake\|autotools` | override detection (default: config `build.system`, else `auto`: `CMakeLists.txt` → cmake, `configure.ac` → autotools) |
| `--variants A,B` | use only these profile variants for this run |
| `--no-variant-filter` | ignore the profile for this run |
| `--previous-report` | default when omitted: `latest/report.html` if it contains test results |
| `--exact-output-dir` | no run folder (scripts / benchmarks keep their fixed paths) |

Behaviour: first run in an interactive terminal with no confirmed profile ⇒ runs the `profile` confirmation, then
analyses. Non-TTY ⇒ no prompt, no filter, note `no confirmed build profile: nothing filtered; run 'tcadvisor
profile' to confirm the build variants`. Last stdout line (`summary` and `brief`): `report: <run folder>`
(`--print json` keeps stdout pure JSON; the run folder is in `report.run.path`). `--exact-output-dir`: write
straight into `--output-dir` without a run folder (scripts, benchmarks).
Exit codes unchanged.

## `tcadvisor profile` (new)

```
tcadvisor profile [--repo R]                 # interactive: detect, show, confirm, save
tcadvisor profile --detect --json            # proposal only (AI front-ends), no write
tcadvisor profile --save FILE|-              # validate + save a profile JSON (schema: config-build-profile)
tcadvisor profile --show                     # current profile + stale/confirmed state
```

Exit 0 saved/shown, 2 invalid input, 1 nothing detectable (message names what to build / which log to give).

## `tcadvisor compile-db` (new)

```
tcadvisor compile-db --from-log LOG [--repo R] [--src YOCTO_S] [--build YOCTO_B] [--variant NAME] [--out FILE]
```

Writes `compile_commands.json` (default `<repo>/.tcadvisor/build/<variant|default>/compile_commands.json`), prints
entry count and unmapped paths; with `--variant` updates that variant's `compile_db`/`build_log`/`log_sha256`.
Exit 1 when no compile command is found (message: build with `V=1` / check `--disable-silent-rules`).

## `tcadvisor init` (changed)

`--output-dir` no longer must resolve outside the repository. Writes `.tcadvisor/reports/` to `.git/info/exclude`.
Next steps printed for autotools: `compile-db --from-log …`, `profile`.
