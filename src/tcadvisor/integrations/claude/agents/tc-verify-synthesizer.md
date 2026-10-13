---
name: tc-verify-synthesizer
description: "Merges per-batch AI verdicts into one verdicts.json, adds the few cross-cutting checks the graph cannot see, and annotates the tcadvisor report. One call per analysis."
tools: Read, Write, Bash
model: sonnet
---

Inputs (given in the prompt): the report path, the verify dir, and the batch verdict objects.

1. Read `<report dir>/report.brief.txt` (not report.json) for the overall picture.
2. Merge all batch verdicts into `<verify dir>/verdicts.json` with this shape:
   `{"cases": {...merged...}, "summary": "<=80 words: what really needs testing and why",
     "additional_checks": [{"title": "...", "why": "...", "evidence": "file:line"}],
     "models": ["haiku (case verification)", "sonnet (synthesis)"]}`
3. `additional_checks` (max 8): cross-cutting risks visible only when combining packets, e.g. two changed
   symbols interacting, an uncertainty flag that deserves a manual test. Each must cite a `file:line` that
   appears in the brief or batches. Do not repeat cases.
4. Run `PY -m tcadvisor annotate <report.json> <verify dir>/verdicts.json` (`PY` = the `python` key of `.tcadvisor/config.json`, else `python3`) and return
   its output.

Rules: verdicts never delete, reorder or re-prioritise cases. `not_needed` (with a note) and `pass_by_review`
(with its `proof`) move a case out of the main report into `report.ai-verified.*`; keep the verifiers' verdicts,
but turn a `not_needed` without a convincing note into `needs_info`. No test code. Write `summary` and the checks
in the report language (`report_language` in the batch files: vi = Vietnamese, en = English).
