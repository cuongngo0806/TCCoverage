---
description: "AI-verify the tcadvisor test cases of the last analysis: close the ones that need no real test, keep the rest"
argument-hint: "all | review"
agent: agent
---

# TC Verify

The user invoked this prompt, which approves sending the packed code windows of the impacted symbols (not the
repository) to the chat model. Scope: `${input:scope:all}` (`review` = only the cases reading code may close; pass
`--scope review` to `verify-pack`).

Follow section 2 ("AI filter") of the `tc-coverage` skill in `.github/skills/tc-coverage/SKILL.md`: `verify-pack`,
a verdict for every case of every batch, `verdicts.json`, `tcadvisor annotate`. If there is no report yet, run its
section 1 first. Then answer in the report language: verdict counts, the cases left to test (from the new
`report.brief.txt`), the cases closed by AI with their reasons (`report.ai-verified.md`) and the additional checks.
