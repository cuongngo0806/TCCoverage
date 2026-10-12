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

- Settings live in the analysed repo's `.tcadvisor/config.json` (`graph`, `language`, `build_dir`, `output_dir`,
  `targets`, `max_hop_depth`; shared with the VS Code extension and Copilot). `python3 -m tcadvisor config --repo <repo>`
  prints the effective values; if the file is missing and the defaults do not fit, offer `tcadvisor init --repo <repo>`.
- Build dir must contain `compile_commands.json` and `.cmake/api/v1/reply/` (without them the run works with
  codegraph but is marked reduced accuracy). To create them:
  `mkdir -p <build>/.cmake/api/v1/query && touch <build>/.cmake/api/v1/query/codemodel-v2 && cmake -S <src> -B <build> -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`
- Map `$ARGUMENTS`: `A..B` → `--commit-range A..B`; `working-tree`/empty → `--working-tree`; a
  branch name → `--commit-range $(git merge-base origin/main <branch>)..<branch>`; names with `::` or
  identifiers → `--symbols a,b`. Never pass a file path as a symbol (the tool rejects it).

## 2. Run (one command, brief output only)

```bash
python3 -m tcadvisor analyze --repo <repo> <mode> --print brief -q
```

Build dir, output dir, targets, depth, impact source and language come from `.tcadvisor/config.json`: do not pass
`--build-dir`, `--output-dir`, `--targets`, `--graph` or `--language` unless the user asks. The last brief line
`REPORT <dir>` is where report.json / report.html are. Impact comes from the configured source (else codegraph). If it is missing the run stops with the install command — tell the user,
never switch to another `--graph` on your own; `--graph gitnexus` only if the user opted in — PolyForm-Noncommercial license). **You never trace
impact yourself; you only verify it** (step 3b).

(If `tcadvisor` is not installed: `pip install -e <this TCCoverage repo>` first.)
Exit codes: `1` prerequisite (compile db / File API missing or stale → explain the fix, stop),
`2` usage (fix arguments), `3` internal (show stderr, stop).

## 3. Token discipline (mandatory)

- Read **only** the brief stdout. Do **not** open `report.json` / `report.html` / `report.md` in full.
- The brief follows the report language (`language` in `.tcadvisor/config.json`, default `vi`): its text may be
  Vietnamese while the line tags (CHANGED, UNCERTAIN, TEST-GAP, NOTE, ...) stay English. Answer in the user's language.
- Need details of one case? `python3 -c "import json;r=json.load(open('<out>/report.json'));print(json.dumps([c for c in r['test_case_candidates'] if c['id']=='TC-0003'],indent=1))"`
- Need code? Read only the evidence window: `sed -n '<line-3>,<line+25>p' <file>` — for at most the P1 cases.
- If the brief has > 40 cases, delegate the reading/summarising to the `tc-coverage-analyst` subagent and keep only its summary.

## 3b. Verify (only when the user wants verification or there are P1 cases)

Cheapest path — never read the code base, only packets:

1. `python3 -m tcadvisor verify-pack <out>/report.json` → `<out>/verify/batch-NN.json` (≤8 packets each).
   For a large change where the user only wants the list of cases to run on the real device, add
   `--scope review` (only the `REVIEW` cases, the ones code reading can close; add `--priorities P1,P2,P3`
   to cover all of them).
2. For each batch launch the `tc-case-verifier` subagent (Haiku) **in parallel** with the batch path.
3. Launch one `tc-verify-synthesizer` subagent (Sonnet) with the report path, verify dir and the batch
   results; it writes `verdicts.json` and runs `tcadvisor annotate` (report/HTML/VS Code then show verdicts).

Or run the saved workflow `tc-verify` (Workflow tool, name `tc-verify`) which does exactly this.

## 4. Answer

1. One-line summary (cases by priority, uncertain count, targets to rebuild/retest) and the brief's
   `Test plan:` line (TARGET = test on the device, REVIEW = may be closed by reading code, CLOSED = an AI
   proved it from the code; CLOSED cases stay listed with their proof, never hidden).
2. **P1 checklist** — for each P1 case: `TC-id`, symbol `file:line`, *what to test* as concrete scenarios
   (inputs/states, expected result) derived from the corner cases + the evidence code you read.
3. P2/P3 grouped compactly (one line each, or "N more" with the report path).
4. **Uncertain / manual review** — every flag, verbatim category + reason. Never drop one.
   Cases with `sub_reason: external_call` are third-party API boundaries: turn their corner cases into
   stub/mock scenarios (make the API fail, return null, throw, call back late). If the user knows library
   behaviour the declaration cannot show, suggest recording it in `.tcadvisor/external-contracts.json`.
   Lesson-pattern cases (`pattern` set): explain the lesson in one line — `data_path_emitter`: show the path
   A → … → C and ask whether C validates what it sends; `sibling_source`: list the other trigger sources and
   whether each has the guard; others: name the counterpart (decode, readers, switch sites, …).
5. Rebuild/retest scope: targets list.
6. Test report: remind the user that `report.html` is fillable (verdict + evidence per case, *Save report*),
   and that `--previous-report <filled.html>` carries results over on the next run; `tcadvisor results
   <filled.html>` checks completeness.
7. Point to `report.html` for the visual impact flow (open in a browser or VS Code "TC Coverage: Show Report").

## Rules (constitution)

- Only cases the tool emitted; keep their ids, priority and risk group unchanged. You may make the wording
  more concrete, never invent symbols, files or dependencies.
- No test code, no running tests, no edits to the analysed repository.
- English for report text; reply to the user in their language.
