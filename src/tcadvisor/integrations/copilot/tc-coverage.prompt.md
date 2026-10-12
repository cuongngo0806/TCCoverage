---
description: "Find the test cases a C++ change must be checked against (impacted callers, side effects, corner cases) with tcadvisor"
argument-hint: "working-tree | HEAD~1..HEAD | main..my-branch | ns::Class::method"
agent: agent
---

# TC Coverage

Change to analyse: `${input:change:working-tree}`

Follow the `tc-coverage` skill in `.github/skills/tc-coverage/SKILL.md` (written by `tcadvisor init`) with this
change as its input: analyse with `python -m tcadvisor analyze --repo . <mode> --print brief -q`, run its AI filter
(section 2) when the brief ends with `AI-VERIFY required`, and answer per its section 4 in the report language.
Never trace dependencies yourself, never read the whole code base, never write test code.
