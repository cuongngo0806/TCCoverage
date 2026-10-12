---
name: tc-coverage
description: "Find the test cases (corner cases, side effects, impacted callers, risk groups) a C++/CMake change must be checked against, AI-filter the ones that need no real test, and point to the visual impact-flow report. Use when the user asks what to test for a commit / diff / branch / function, wants test coverage of a change, impact analysis, blast radius, or side-effect review. Args: a commit range (A..B), 'working-tree', or symbol names."
argument-hint: "[HEAD~1..HEAD | working-tree | ns::Class::method,...]"
---

# TC Coverage: change impact → test cases to check on the real system

The deterministic `tcadvisor` CLI does all dependency tracing. **Never trace dependencies yourself and never read
the whole code base.** Run the tool, read its brief, (optionally) let an AI close the cases that need no real test,
and turn what is left into a checklist for the user. Installed by `tcadvisor init`; works the same in Claude Code
(`/tc-coverage`) and GitHub Copilot agent mode (skill, or the `/tc-coverage` prompt).

## User input

```text
$ARGUMENTS
```

## 0. Setup (only when something is missing)

- `tcadvisor` not installed: `pip install "git+https://github.com/cuongngo0806/tccoverage"` (Python ≥ 3.10).
  Use the Python that has it (`python` on Windows, `python3` elsewhere): `python -m tcadvisor ...`.
- Settings live in `.tcadvisor/config.json` of the analysed repository (`graph`, `language`, `build_dir`,
  `output_dir`, `targets`, `max_hop_depth`, `include_tests`, `test_paths`, `ai_verify`). `python -m tcadvisor config
  --repo .` prints the effective values. No file and the defaults do not fit → `python -m tcadvisor init --repo .`.
- Impact source codegraph missing (exit code 1 says so): `npm i -g @colbymchenry/codegraph`. Never switch to
  another `--graph` yourself.
- Better accuracy: a build dir with `compile_commands.json` and the CMake File API reply:
  `mkdir -p build/.cmake/api/v1/query && touch build/.cmake/api/v1/query/codemodel-v2 &&
  cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`.

## 1. Analyse (one command, brief output only)

```
python -m tcadvisor analyze --repo . <mode> --print brief -q
```

- `<mode>`: `working-tree` or empty → `--working-tree`; `A..B` → `--commit-range A..B`; a branch name →
  `--commit-range <merge-base with main>..<branch>`; names with `::` or identifiers → `--symbols a,b` (never a
  file path).
- Do **not** pass `--graph`, `--language`, `--build-dir`, `--output-dir`, `--targets`, `--include-tests` or
  `--max-hop-depth` unless the user asks: they come from the config. Unit-test code is left out unless
  `include_tests` is true (the report is about the product, not its unit tests).
- Exit `1` = prerequisite missing: show the message with its fix and stop. `2` = wrong arguments: fix once.
  `3` = internal error: show stderr and stop.
- The last lines: `REPORT <dir>` (where report.json / report.html are) and, when `ai_verify` is `chat`,
  `AI-VERIFY required`.

## 2. AI filter (when the brief says `AI-VERIFY required`, or the user asks to verify / reduce the list)

Goal: keep in the main report only the cases that really need a test on the real system. The AI closes the
others with a reason; they move to `report.ai-verified.md` / `.html` (never deleted, report.json keeps them).
Only packed code windows are read — never explore the repository.

1. `python -m tcadvisor verify-pack --repo .` prints a manifest: `report`, `verdicts` (where to write the
   result), `report_language` and the `batches` files (≤ 8 packets each).
2. For each batch file (read only that file; in Claude Code you may give each batch to a `tc-case-verifier`
   subagent in parallel), decide for **every** case id:
   - `confirmed` — the code shows the risk is real for this symbol: it needs a real test run.
   - `not_needed` — no real test is needed, and `note` says what settles it: a clean build alone (recompile-only
     includer, removed macro / symbol with no remaining user, unchanged declaration), or the change cannot reach
     this symbol's behaviour (value passed through unchanged, changed branch unreachable from here, identical
     semantics). Not when the risk shows at run time (concurrency, timing, hardware, memory lifetime, a changed
     value this code reads and acts on) unless the code shows it is unaffected.
   - `pass_by_review` — only for `verify_by: review` cases, and only when the code **proves** the case cannot
     fail for every input and state; give `proof`: 1-3 `file:line` from the code window.
   - `needs_info` — the window is not enough: say what is missing in `note` (you may read ≤ 20 more lines of
     that file once per packet). The case stays to test.

   A wrong close hides a regression; a missing close only costs one test run: any doubt → `confirmed` or
   `needs_info`. Add up to 3 `extra_corner_cases` per case, concrete to the code you saw (inputs, states,
   ordering, boundary values, interleavings, error paths). No generic advice, no test code.
3. Write the manifest's `verdicts` file (in Claude Code the `tc-verify-synthesizer` subagent can merge the batch
   results and do this step):

   ```json
   {"cases": {"TC-0001": {"verdict": "confirmed", "note": "<=25 words", "extra_corner_cases": ["..."]},
              "TC-0002": {"verdict": "not_needed", "note": "header only re-included: a clean build settles it"},
              "TC-0003": {"verdict": "pass_by_review", "note": "...", "proof": ["src/a.cpp:42"]}},
    "summary": "<=80 words: what really needs testing and why",
    "additional_checks": [{"title": "...", "why": "...", "evidence": "file:line"}],
    "models": ["<the model(s) you are>"]}
   ```

   `note`, `extra_corner_cases`, `summary` and `additional_checks` in the manifest's `report_language`
   (`vi` = Vietnamese, `en` = English); ids, verdict values, symbols and `file:line` unchanged.
   `additional_checks` (max 8): cross-cutting risks visible only when combining packets, each citing a
   `file:line` from the batches; never a repeat of a case.
4. `python -m tcadvisor annotate <report> <verdicts>`; report its warnings. Then read `<REPORT dir>/report.brief.txt`
   again: it now lists only the cases left to test, and an `AI-CLOSED n` line.

## 3. Token discipline

- Read **only** the brief. Do not open `report.json`, `report.md` or `report.html` in full.
- Details of one case: `python -c "import json;r=json.load(open('<dir>/report.json'));print([c for c in
  r['test_case_candidates'] if c['id']=='TC-0003'])"`. Code: at most ~30 lines around an evidence `file:line`,
  only for P1 cases.
- Line tags (`CHANGED`, `UNCERTAIN`, `SOURCES`, `AI-ALSO`, `AI-CLOSED`, `NOTE`, `REPORT`) are markers; the text
  after them is in the report language. In Claude Code, a brief with > 40 cases can be summarised by the
  `tc-coverage-analyst` subagent.

## 4. Answer (in the report language: `language` in the config, `vi` by default)

1. One-line summary and the brief's test-plan line (TARGET = test on the device, REVIEW = reading code may close
   it; cases closed by AI are counted, listed in `report.ai-verified.md`).
2. **P1 checklist**: id, symbol `file:line`, concrete test scenarios (inputs / states, expected result) from the
   corner cases (also the AI ones) and the evidence code.
3. P2/P3: one line each (or "N more" with the report path).
4. Every `UNCERTAIN` line: category and reason as given. Never drop one.
5. `AI-ALSO` checks, then the targets to rebuild / retest.
6. `report.html` in the `REPORT` dir: visual impact flow and a form to record each case's result (verdict +
   evidence; `--previous-report <filled.html>` carries results over, `tcadvisor results <filled.html>` checks
   completeness). `report.ai-verified.html`: the cases the AI closed, with its reasons.

## Rules

Output is a list of cases to check, never test code. Only cases the tool emitted: keep their ids, priority and
risk group; you may word them more concretely, never invent symbols, files or dependencies. A case leaves the main
list only through a verdict written to `verdicts.json` and `tcadvisor annotate`. Do not edit the user's source
code and do not run tests.
