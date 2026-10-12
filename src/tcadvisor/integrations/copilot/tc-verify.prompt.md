---
description: "AI-verify the tcadvisor test cases of the last analysis (verdicts, proof, extra corner cases) and annotate the report"
argument-hint: "all | review"
agent: agent
---

# TC Verify: AI review of the deterministic test cases

The user invoked this prompt, which approves sending the packed code windows of the impacted symbols (not the
repository) to the chat model. Verdicts only **annotate** cases: never add, remove, reorder or re-prioritise them.
Never trace dependencies yourself and never explore the repository beyond the packets.

Scope: `${input:scope:all}` (`review` = only the cases that reading code may close).

## 1. Make sure there is a report

If the user has not analysed the change yet (or it changed since), first run
`python -m tcadvisor analyze --repo . --working-tree --print brief -q` (or the range they name). Do not pass
`--graph`, `--language`, `--build-dir` or `--output-dir`: they come from `.tcadvisor/config.json`. Exit code `1`:
show the message with its fix and stop.

## 2. Pack the cases

```
python -m tcadvisor verify-pack --repo . --scope <all|review>
```

It prints a manifest: `report` (report.json path), `verdicts` (where to write the result), `report_language`
and the `batches` files. Use the Python that has tcadvisor installed (`python` on Windows, `python3` elsewhere).

## 3. Verify each batch

Read the batch files one at a time (only those files). Each packet has a symbol, a code window (`code`), its
graph links (`links`) and its cases. Each case has `verify_by`: `target` (must run on the real device;
`target_reasons` says why) or `review` (may be closed by reading code). For **every** case id decide:

- `pass_by_review` — only for `verify_by: review` cases, and only when the code you see **proves** the case
  cannot fail for this symbol for every input and state it can receive (the change does not reach its
  behaviour, value passed through unchanged, changed branch unreachable from here, identical semantics). Give
  `proof`: 1-3 `file:line` from the code window, and say why in `note`. Any doubt or assumption about hardware,
  timing, configuration or unseen data → do not use it: a wrong pass hides a regression, a missing pass only
  costs one test run. `tcadvisor annotate` rejects it without a resolvable proof or on a `target` case.
- `confirmed` — the code shows the risk is real for this symbol.
- `weak` — the link exists but the risk looks low (the case still needs a test run).
- `needs_info` — the window is not enough: say what is missing in `note` (you may read at most 20 more lines
  of that file once per packet).

Add up to 3 `extra_corner_cases` per case, concrete to the code you saw (inputs, states, ordering, boundary
values, thread interleavings, error paths). No generic advice, no test code.

## 4. Write the verdicts and annotate

Write the file at the manifest's `verdicts` path:

```json
{"cases": {"TC-0001": {"verdict": "confirmed", "note": "<=25 words", "extra_corner_cases": ["..."]},
           "TC-0002": {"verdict": "pass_by_review", "note": "...", "proof": ["src/a.cpp:42"], "extra_corner_cases": []}},
 "summary": "<=80 words: what really needs testing and why",
 "additional_checks": [{"title": "...", "why": "...", "evidence": "file:line"}],
 "models": ["GitHub Copilot"]}
```

- Write `note`, `extra_corner_cases`, `summary` and `additional_checks` in the manifest's `report_language`
  (`vi` = Vietnamese, `en` = English). Keep ids, verdict values, symbols and `file:line` unchanged.
- `additional_checks` (max 8): cross-cutting risks visible only when combining packets (two changed symbols
  interacting, an uncertainty flag that deserves a manual test, an existing test to extend). Each must cite a
  `file:line` that appears in the batches. Do not repeat cases.

Then run `python -m tcadvisor annotate <report> <verdicts>` and report its warnings, if any.

## 5. Answer

In the report language: verdict counts (confirmed / weak / needs_info / closed by review), the cases closed by
review with their proof, the additional checks, and that `report.html` (and the VS Code view) now show the
verdicts.
