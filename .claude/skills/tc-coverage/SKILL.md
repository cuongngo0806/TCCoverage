---
name: tc-coverage
description: "Find the test cases (corner cases, side effects, impacted callers, risk groups) a C/C++ change (CMake or autotools / Yocto module) must be checked against, AI-filter the ones that need no real test, and point to the visual impact-flow report. Use when the user asks what to test for a commit / diff / branch / function, wants test coverage of a change, impact analysis, blast radius, or side-effect review. Args: a commit range (A..B), 'working-tree', or symbol names."
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

- Interpreter `PY`: the `python` key of `.tcadvisor/config.json` (written by `tcadvisor init`, e.g.
  `~/.venvs/tcadvisor/bin/python`); without it `~/.venvs/tcadvisor/bin/python` if that exists, else `python3`.
- Check first, every session: `PY -m tcadvisor --version` must print **0.2.0 or newer**. Missing or older →
  install / upgrade into a virtual environment (never the system Python: on Ubuntu / Debian a plain `pip install`
  goes to `~/.local` or is refused):

  ```bash
  python3 -m venv ~/.venvs/tcadvisor        # Debian/Ubuntu without venv support: ask the user to run
                                            # `sudo apt install python3-venv` and stop
  ~/.venvs/tcadvisor/bin/pip install -U "git+https://github.com/cuongngo0806/tccoverage" > /tmp/tcadvisor-pip.log 2>&1
  ~/.venvs/tcadvisor/bin/python -m tcadvisor --version || tail -30 /tmp/tcadvisor-pip.log
  ```

  The user may name a branch / tag to install (`…/tccoverage@<branch>`). Show the log tail and stop if it still
  fails (network, proxy, no `git`): never retry the same command. After an install or upgrade run
  `~/.venvs/tcadvisor/bin/python -m tcadvisor init --repo . --upgrade` (refreshes this skill and records the
  interpreter in the config; config values are kept) and use `PY = ~/.venvs/tcadvisor/bin/python` from then on.
- Settings live in `.tcadvisor/config.json` of the analysed repository; `PY -m tcadvisor config --repo .` prints
  every key with its value and source. No file → `PY -m tcadvisor init --repo .` (writes all keys with defaults).
- Impact source codegraph missing (exit code 1 says so): `npm i -g @colbymchenry/codegraph`. Never switch to
  another `--graph` yourself.
- Compile database (better accuracy; required with `graph: clang`):
  - CMake: `mkdir -p build/.cmake/api/v1/query && touch build/.cmake/api/v1/query/codemodel-v2 &&
    cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`.
  - autotools (`configure.ac` + `Makefile.am`, also Yocto recipes): from the build log, never by running the
    build yourself: `PY -m tcadvisor compile-db --repo . --from-log <log> --variant <name>`, where `<log>` is
    `${WORKDIR}/temp/log.do_compile` of the recipe (one per MACHINE / variant) or a local `make V=1` log. Ask the
    user for the log path when it is not known.

### 0b. Build profile (first run in a workspace, or when the brief has a NOTE `no confirmed build profile`)

The module may be built in several variants (machines, product types, configure options). Confirm them once so
cases on code no variant builds are listed apart instead of in the checklist:

1. `PY -m tcadvisor profile --repo . --detect --json` → `system`, `switches`, `variants` (with the switch values
   the builds reveal) and `unset` (switches whose value is unknown per variant).
2. Show the user the variants and their known values in a short table; ask which variants are really built /
   shipped, their names, and the value (on / off / number) of the `unset` switches that matter. Do not guess.
3. Save the confirmed JSON (the proposal with the kept variants and the user's values, `value_source` `user` for
   them): `PY -m tcadvisor profile --repo . --save -` with the JSON on stdin. A NOTE saying the build description
   changed (profile `stale`) → repeat 1-3.

## 1. Analyse (one command, brief output only)

```
PY -m tcadvisor analyze --repo . <mode> --print brief -q
```

- `<mode>`: `working-tree` or empty → `--working-tree`; `A..B` → `--commit-range A..B`; a branch name →
  `--commit-range <merge-base with main>..<branch>`; names with `::` or identifiers → `--symbols a,b` (never a
  file path).
- Do **not** pass `--graph`, `--language`, `--build-dir`, `--output-dir`, `--targets`, `--include-tests`,
  `--max-hop-depth`, `--build-system` or `--variants` unless the user asks: they come from the config (one variant
  for one run: `--variants a,b`; everything: `--no-variant-filter`). Unit-test code is left out unless
  `include_tests` is true (the report is about the product, not its unit tests).
- Exit `1` = prerequisite missing: show the message with its fix and stop. `2` = wrong arguments: fix once.
  `3` = internal error: show stderr and stop.
- The last lines: `REPORT <dir>` (this run's own folder `.tcadvisor/reports/<time>-<change>/`; earlier runs are
  never overwritten, `.tcadvisor/reports/latest` points at the newest), `AI-VERIFY required` when `ai_verify` is
  `chat`, and `report: <dir>`.
- `PROFILE <state> <variants>` and `NOT-BUILT <id> <file:line> :: <variant: condition>` lines: cases on code no
  confirmed variant builds (they are in the report's "Not built in the confirmed variants" section, not deleted).

## 2. AI filter (when the brief says `AI-VERIFY required`, or the user asks to verify / reduce the list)

Goal: keep in the main report only the cases that really need a test on the real system. The AI closes the
others with a reason; they move to `report.ai-verified.md` / `.html` (never deleted, report.json keeps them).
Only packed code windows are read — never explore the repository.

1. `PY -m tcadvisor verify-pack --repo .` prints a manifest: `report`, `verdicts` (where to write the
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
4. `PY -m tcadvisor annotate <report> <verdicts>`; report its warnings. Then read `<REPORT dir>/report.brief.txt`
   again: it now lists only the cases left to test, and an `AI-CLOSED n` line.

## 3. Token discipline

- Read **only** the brief. Do not open `report.json`, `report.md` or `report.html` in full.
- Details of one case: `python -c "import json;r=json.load(open('<dir>/report.json'));print([c for c in
  r['test_case_candidates'] if c['id']=='TC-0003'])"`. Code: at most ~30 lines around an evidence `file:line`,
  only for P1 cases.
- Line tags (`CHANGED`, `UNCERTAIN`, `SOURCES`, `AI-ALSO`, `AI-CLOSED`, `NOTE`, `REPORT`, `PROFILE`, `NOT-BUILT`)
  are markers; the text
  after them is in the report language. In Claude Code, a brief with > 40 cases can be summarised by the
  `tc-coverage-analyst` subagent.

## 4. Answer (in the report language: `language` in the config, `vi` by default)

1. One-line summary and the brief's test-plan line (TARGET = test on the device, REVIEW = reading code may close
   it; cases closed by AI are counted, listed in `report.ai-verified.md`).
2. **P1 checklist**: id, symbol `file:line`, concrete test scenarios (inputs / states, expected result) from the
   corner cases (also the AI ones) and the evidence code.
3. P2/P3: one line each (or "N more" with the report path).
4. Every `UNCERTAIN` line: category and reason as given. Never drop one.
5. `AI-ALSO` checks, then the targets to rebuild / retest (CMake targets or autotools programs / libraries).
   With a build profile: "N cases on code not built in <variants>" (one line; they need no test for these
   variants).
6. `report.html` in the `REPORT` dir: visual impact flow and a form to record each case's result (verdict +
   evidence: paste a screenshot with Ctrl+V, it shows inline; Save report writes one self-contained file). The
   next analysis carries the results of the latest run over by case key; `tcadvisor results <filled.html>` checks
   completeness. `report.ai-verified.html`: the cases the AI closed, with its reasons.

## Rules

Output is a list of cases to check, never test code. Only cases the tool emitted: keep their ids, priority and
risk group; you may word them more concretely, never invent symbols, files or dependencies. A case leaves the main
list only through a verdict written to `verdicts.json` and `tcadvisor annotate`. Do not edit the user's source
code and do not run tests.
