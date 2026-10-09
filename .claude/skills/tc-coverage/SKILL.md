---
name: tc-coverage
description: "Find the test cases (corner cases, side effects, impacted callers, risk groups) a C++/CMake change must be checked against, with a visual impact-flow report. Use when the user asks what to test for a commit / diff / branch / function, wants test coverage of a change, impact analysis, blast radius, or side-effect review. Args: a commit range (A..B), 'working-tree', or symbol names."
argument-hint: "[HEAD~1..HEAD | working-tree | ns::Class::method,...] [--targets T1,T2]"
---

# TC Coverage (change impact → test cases)

The deterministic `tcadvisor` CLI does all dependency tracing (libclang + CMake File API).
**You never trace dependencies yourself and never read the whole codebase.** Your job: run the tool,
read its *brief* output, and turn the evidence into a clear, verified checklist for the user.

## User input

```text
$ARGUMENTS
```

## 1. Resolve inputs (cheap, once)

- Config lives in `.claude/tc-coverage.local.json` (create it if missing, ask the user only for what you cannot detect):
  `{"repo": "<abs path of analysed git repo>", "build_dir": "<cmake build dir>", "targets": "RemoteDoorLock,RemoteDoorUnlock", "python": "python3"}`
- Build dir must contain `compile_commands.json` and `.cmake/api/v1/reply/`. If not, tell the user to run:
  `mkdir -p <build>/.cmake/api/v1/query && touch <build>/.cmake/api/v1/query/codemodel-v2 && cmake -S <src> -B <build> -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`
- Map `$ARGUMENTS`: `A..B` → `--commit-range A..B`; `working-tree`/empty → `--working-tree`; a
  branch name → `--commit-range $(git merge-base origin/main <branch>)..<branch>`; names with `::` or
  identifiers → `--symbols a,b`. Never pass a file path as a symbol (the tool rejects it).

## 2. Run (one command, brief output only)

```bash
<python> -m tcadvisor analyze --repo <repo> --build-dir <build> <mode> [--targets <targets>] \
  --output-dir <repo>/../tcadvisor-report --print brief -q
```

(If `tcadvisor` is not installed: `pip install -e <this TCCoverage repo>` first.)
Exit codes: `1` prerequisite (compile db / File API missing or stale → explain the fix, stop),
`2` usage (fix arguments), `3` internal (show stderr, stop).

## 3. Token discipline (mandatory)

- Read **only** the brief stdout. Do **not** open `report.json` / `report.html` / `report.md` in full.
- Need details of one case? `python3 -c "import json;r=json.load(open('<out>/report.json'));print(json.dumps([c for c in r['test_case_candidates'] if c['id']=='TC-0003'],indent=1))"`
- Need code? Read only the evidence window: `sed -n '<line-3>,<line+25>p' <file>` — for at most the P1 cases.
- If the brief has > 40 cases, delegate the reading/summarising to the `tc-coverage-analyst` subagent and keep only its summary.

## 4. Answer

1. One-line summary (cases by priority, uncertain count, targets to rebuild/retest).
2. **P1 checklist** — for each P1 case: `TC-id`, symbol `file:line`, *what to test* as concrete scenarios
   (inputs/states, expected result) derived from the corner cases + the evidence code you read.
3. P2/P3 grouped compactly (one line each, or "N more" with the report path).
4. **Uncertain / manual review** — every flag, verbatim category + reason. Never drop one.
5. Rebuild/retest scope: targets list.
6. Point to `report.html` for the visual impact flow (open in a browser or VS Code "TC Coverage: Show Report").

## Rules (constitution)

- Only cases the tool emitted; keep their ids, priority and risk group unchanged. You may make the wording
  more concrete, never invent symbols, files or dependencies.
- No test code, no running tests, no edits to the analysed repository.
- English for report text; reply to the user in their language.
