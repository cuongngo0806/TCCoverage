# Data model: spec 012

## RunFolder

| Field | Type | Rule |
|---|---|---|
| `root` | path | `output_dir` from config/flag, default `<repo>/.tcadvisor/reports` |
| `name` | str | `<YYYYMMDD-HHMMSS>-<change>[-N]`; `<change>` ∈ `<old7>_<new7>`, `working-tree`, `symbols` |
| `path` | path | `root/name`; created exclusively; never written by a later run |
| `latest` | symlink / `latest.txt` | points at the newest completed run (updated after the write succeeds) |

Recorded in report.json as `run: {name, path, created_at, change}`.

## BuildProduct (autotools; same `TargetInfo` as CMake)

`name`, `type` (`program` | `ltlibrary` | `library`), `source_dir`, `sources` (set of paths),
`dependencies` (internal products from `_LDADD`/`_LIBADD`), `conditions` (per source: list of automake
conditional names with polarity, e.g. `["ENABLE_X", "!USE_Y"]`), `defined_at` (Makefile.am:line), `is_test`
(`check_*`).

## BuildModel

`system` (`cmake` | `autotools`), `targets` (`TargetModel`), `unresolved` (list of `{file, line, construct}` →
uncertainty flags), `build_files` (paths whose change = build-configuration change), `fingerprint` (sha256 of
`configure.ac` + all `Makefile.am`/`*.am`; profile staleness).

## Switch

| Field | Type | Rule |
|---|---|---|
| `name` | str | `AM:<COND>` for automake conditionals, `--enable-x`/`--with-y` for configure options, plain macro name for preprocessor |
| `kind` | `am_conditional` \| `configure_option` \| `macro` | |
| `declared_at` | str | file:line |

## Variant

| Field | Type | Rule |
|---|---|---|
| `name` | str | unique in profile, `[A-Za-z0-9._-]+` |
| `compile_db` | path? | relative to repo or absolute; generated or user-provided |
| `build_log` | path? | source of the generated compile DB; `log_sha256` stored |
| `build_dir` | path? | where `config.status` / `config.log` / `config.h` were read |
| `values` | map name → str \| bool \| null | from build artefacts first, then user; `null` = unknown |
| `value_source` | map name → `build` \| `user` | |

## BuildProfile (config key `build`)

`system` (`auto` | `cmake` | `autotools`), `confirmed` (bool), `confirmed_at`, `variants` (≥1 Variant),
`fingerprint` (BuildModel.fingerprint at confirmation). States: *absent* → (`profile` / first TTY run) →
*confirmed* → (build files change: fingerprint differs) → *stale* (still applied, report warns) → re-confirm →
*confirmed*. Schema: [contracts/config-build-profile.schema.json](contracts/config-build-profile.schema.json).

## NotBuiltEntry (report.json `not_built`)

`case` (the full case object as it would have been emitted), `excluded_by`: list of
`{variant, reason: "source_not_in_product" | "conditional_dir" | "preprocessor", condition, where}`; and
`not_built_changes`: `{path, symbol, line, excluded_by}` for root changes that produced no case.

## Attachment (unchanged shape)

`{name, type, size, sha256, data, added_at}` + optional `origin: "paste" | "drop" | "file"`.
