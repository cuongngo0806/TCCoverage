# Fillable report contract (spec 006, FR-608…FR-612)

## Per case

- Verdict: `Pass` · `Fail` · `Cannot be tested` · `Cannot occur` (stored as `pass`, `fail`,
  `not_testable`, `cannot_occur`); "Clear" returns to untested.
- Comment (multi-line), Tester (pre-filled from the last value in this browser), Date (defaults to today),
  Defect reference.
- Attachments: file picker + drag & drop, any type; images previewed inline; other files listed with name,
  size and a "Save file" action; remove per attachment.
- Rules (blocking "complete" state, shown inline): `Cannot be tested` / `Cannot occur` need a comment;
  `Fail` needs an attachment or a defect reference; any verdict needs tester + date.
- Badges: verdict colour, `needs re-check` (carried over, code changed), `carried over`.

## Report level

- Summary bar: counts per verdict, untested, needs re-check, incomplete; total attachment size with a
  warning above the configured limit; "Incomplete" banner while any case is untested or invalid.
- Filters: by verdict / untested / needs re-check (in addition to the existing priority / group filters).
- "No longer reported" section listing `orphaned_results` read-only.
- **Save report**: produces a new single HTML file containing the updated results block and every
  attachment (base64). Browser: download `report-<short-commit>-<YYYYMMDD-HHMM>.html`. VS Code webview:
  `postMessage({type:"saveReport", html})` → extension shows a save dialog and writes the file.
  Unsaved changes → `beforeunload` warning.
- **Print / PDF**: `@media print` — summary, then every case (id, priority, description, evidence,
  corner cases, verdict, comment, tester, date, defect, inline images, attachment list with sha256, first
  40 lines of text attachments). Interactive controls hidden.
- Offline: no external resources; all logic inline.

## Invariants

- Recording results never changes the case list, order, priorities or keys (FR-613).
- The analysis data block (`#data`) is never modified by the form; only `#results` is.
- A saved file opened again shows exactly the saved state; `tcadvisor analyze --previous-report` and
  `tcadvisor results` read the same block.
