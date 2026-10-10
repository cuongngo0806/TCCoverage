# CLI Contract: `tcadvisor`

**Scope**: This document specifies the command-line interface contract for the MVP. It is the
"public API" of the tool for this feature, since the advisor has no other external interface
(Principle I: output is a case list, not a library/service API).

## Command: `tcadvisor analyze`

Runs one Analysis Run (see data-model.md `AnalysisRun`) and produces the Markdown + JSON outputs
(FR-008).

### Invocation forms

```text
# Mode A: git commit range
tcadvisor analyze --repo <path> --commit-range <rev>..<rev> [options]

# Mode B: working-tree diff (uncommitted changes)
tcadvisor analyze --repo <path> --working-tree [options]

# Mode C: explicit symbol list (FR-001a: symbols only, never bare file paths)
tcadvisor analyze --repo <path> --symbols <qualified_name>[,<qualified_name>...] [options]
# or, for multiple/complex symbol sets:
tcadvisor analyze --repo <path> --symbols-file <path-to-symbol-list.json> [options]
```

Exactly one of `--commit-range`, `--working-tree`, `--symbols`, `--symbols-file` MUST be
provided. Providing more than one, or none, is a usage error (exit code 2).

### Required options

| Option | Description |
|---|---|
| `--repo <path>` | Absolute path to the analyzed repository root. Read-only access (Principle VIII). |
| `--build-dir <path>` | Path to the CMake build directory containing `compile_commands.json` and the CMake File API reply directory (`.cmake/api/v1/reply/`). If absent or stale, the advisor MUST fail with the FR-013 prerequisite error — it MUST NOT proceed with degraded accuracy. |

### Optional options

| Option | Default | Description |
|---|---|---|
| `--max-hop-depth <int>` | `2` | Indirect-impact traversal depth (FR-002). |
| `--split-threshold <int>` | `50` | File-count threshold above which the diff is split per CMake target (FR-010a). |
| `--contracts <file>` | `<repo>/.tcadvisor/external-contracts.json` if present | Third-party API contracts: `{"<name or pattern>": ["corner case", ...]}` added to `external_call` cases (spec 005). Unreadable → exit 2. |
| `--lessons <file>` | `<repo>/.tcadvisor/lessons.json` if present | Extra emitting points (`sinks`) and team lessons (spec 006). Invalid → exit 2. |
| `--previous-report <report.html>` | none | Filled report of an earlier run; test results + evidence carried over by case `key`, `needs_recheck` when the code behind a case changed (spec 006). Unreadable → exit 2. |
| `--flow-max-tus <int>` | `60` | Max translation units parsed for data-path tracing (spec 006). |
| `--no-patterns` | off | Disable data paths, trigger sources and lesson patterns (spec 006). |
| `--attachment-warn-mb <int>` | `50` | Report warns when embedded evidence exceeds this size (spec 006). |
| `--cache-dir <path>` | `<repo>/../.tcadvisor-cache/<module-name>` (outside the analyzed repo's tracked tree) | Location of the SQLite cache (data-model.md `CachedDependencyIndex`). |
| `--llm` / `--no-llm` | `--no-llm` | Enables/disables the optional LLM enrichment step (FR-011/FR-012). Disabled by default (Principle VI). |
| `--llm-endpoint <url>` | `http://localhost:11434` (local Ollama default) | Only used when `--llm` is set. Any non-localhost endpoint requires `--llm-external-approved` to also be set (Principle VI enforcement). |
| `--llm-external-approved` | unset | Explicit opt-in flag acknowledging team approval to send data to a non-local LLM endpoint. Required alongside any non-localhost `--llm-endpoint`. |
| `--output-dir <path>` | `./tcadvisor-report/` | Where `report.md` and `report.json` are written. MUST NOT resolve inside the analyzed `--repo` path (Principle VIII). |
| `--format <md\|json\|both>` | `both` | Which output artifact(s) to generate (FR-008). |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success — report(s) generated (may include confirmed cases and/or uncertainty flags). |
| `1` | Analysis prerequisite failure (e.g., missing/stale `compile_commands.json` or CMake File API reply — FR-013). |
| `2` | Usage error (invalid/conflicting CLI arguments). |
| `3` | Internal error (unexpected exception during analysis; always logged, never silently swallowed). |

### Stdout/stderr contract

- Stdout: run summary (files analyzed, cache hit/miss, number of confirmed cases, number of
  uncertainty flags, LLM status — enabled/disabled/degraded, run time) — all in English
  (Principle IX).
- Stderr: warnings and errors only (e.g., FR-013 prerequisite failure details naming the specific
  missing/stale module).

## Command: `tcadvisor cache clear`

```text
tcadvisor cache clear --repo <path> [--cache-dir <path>]
```

Deletes the cached index for the specified repository/module. Provided for explicit cold-start
testing and troubleshooting; never invoked automatically by `analyze`.

## Non-goals (explicitly out of CLI scope, per constitution Principle VIII)

- No `tcadvisor fix` / `tcadvisor apply` command — the tool never mutates source.
- No `tcadvisor run-tests` command — the tool never executes tests on any target/device.
- No `tcadvisor generate-tests` command — the tool never authors test code.
