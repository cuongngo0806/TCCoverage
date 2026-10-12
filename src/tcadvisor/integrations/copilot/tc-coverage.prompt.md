---
description: "Find the test cases a C++ change must be checked against (impacted callers, side effects, corner cases) with tcadvisor"
argument-hint: "working-tree | HEAD~1..HEAD | main..my-branch | ns::Class::method"
agent: agent
---

# TC Coverage: change impact → test cases

The deterministic `tcadvisor` CLI does all dependency tracing. **Never trace dependencies yourself and never read
the whole code base.** Run the tool, read its brief output and turn it into a clear checklist for the user.

Change to analyse: `${input:change:working-tree}`

## 1. Run one command (terminal, repository root)

```
python -m tcadvisor analyze --repo . <mode> --print brief -q
```

- `<mode>`: `working-tree` or empty → `--working-tree`; `A..B` → `--commit-range A..B`; a branch name →
  `--commit-range <merge-base with main>..<branch>`; names with `::` or identifiers → `--symbols a,b`
  (never a file path).
- Use the Python that has tcadvisor installed (`python` on Windows, `python3` elsewhere).
- Do **not** pass `--graph`, `--language`, `--build-dir`, `--output-dir`, `--targets` or `--max-hop-depth`
  unless the user asks: they come from `.tcadvisor/config.json` (shared with the VS Code extension).
- Exit code `1` = a prerequisite is missing (e.g. codegraph not installed, stale compile database): show the
  message with its fix and stop — never switch to another `--graph` yourself. `2` = wrong arguments (fix and
  retry once). `3` = internal error: show stderr and stop.

## 2. Token discipline

- Read **only** the brief printed in the terminal. Do not open `report.json`, `report.md` or `report.html`.
- For details of a P1 case, read at most ~30 lines of code around its evidence `file:line`.
- Line tags (`CHANGED`, `UNCERTAIN`, `TEST-GAP`, `SOURCES`, `NOTE`, `REPORT`) are markers; the text after them is
  in the configured report language.

## 3. Answer

Write the whole answer in the **same language as the brief's text** (the report language set by `language` in
`.tcadvisor/config.json`: `vi` = Vietnamese, `en` = English).

1. One-line summary (cases by priority, uncertain count, targets to rebuild/retest) and the brief's test-plan
   line (TARGET = test on the device, REVIEW = reading code may close it, CLOSED = closed by code review).
2. **P1 checklist**: for each P1 case its id, symbol `file:line` and concrete test scenarios (inputs / states,
   expected result) derived from its corner cases and the evidence code.
3. P2/P3: one line each (or "N more" with the report path).
4. Every `UNCERTAIN` line: category and reason as given. Never drop one.
5. Targets to rebuild / retest, and the `RERUN --gtest_filter=...` line if present.
6. Point to `report.html` in the `REPORT` directory: the visual impact flow, and a form to record each case's
   test result (verdict + evidence). AI verification of the cases: `/tc-verify`.

## Rules

Output is a list of cases to check, never test code. Do not add, remove or re-prioritise cases: they come from
the deterministic analysis. Do not edit the user's source code.
