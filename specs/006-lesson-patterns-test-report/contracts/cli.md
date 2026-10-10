# CLI contract additions (spec 006)

Extends `specs/001-change-impact-test-advisor/contracts/cli-contract.md`. Exit codes unchanged
(0 ok, 1 prerequisite, 2 usage, 3 internal).

## `tcadvisor analyze` — new options

| Option | Default | Meaning |
|---|---|---|
| `--previous-report <report.html>` | none | Filled report of an earlier run: results and attachments are carried over by case `key`; changed code → `needs_recheck`. Unreadable / not a tcadvisor report / unknown schema → exit 2. |
| `--lessons <file>` | `<repo>/.tcadvisor/lessons.json` if present | Emitter names (`sinks`) and team lessons. Invalid → exit 2. |
| `--flow-max-tus <int>` | `60` | Max translation units parsed for data-path facts; beyond it data paths are flagged, not traced. |
| `--no-patterns` | off | Disable data paths, trigger sources and lesson patterns (cycle-5 behaviour). |
| `--attachment-warn-mb <int>` | `50` | Report warns when embedded attachments exceed this size. |

## Outputs

- `report.json` (schema extended, see `report-results.schema.json` for the `test_results` block and the
  new case fields in data-model.md): new case fields `key`, `code_fingerprint`, `pattern`, `path`,
  `lessons`, `test_result` (the case's record, when results exist); top-level `test_results` (results block, only when `--previous-report` given).
- `report.html`: fillable form (see `report-form.md`); carries the results block.
- `report.md` / `--print brief`: when results exist, each case line ends with `[PASS|FAIL|N/T|N/O|—]`
  and `(re-check)`; a summary line `test results: 12 pass / 1 fail / 2 n/t / 1 n/o / 4 untested`.

## `tcadvisor results` — new subcommand

`tcadvisor results <report.html> [--json]` prints the summary and incomplete / failing cases of a filled
report (for CI or a reviewer without a browser). Exit 0 when complete, 4 when incomplete or any `fail`
(new exit code, documented here only for this subcommand).
