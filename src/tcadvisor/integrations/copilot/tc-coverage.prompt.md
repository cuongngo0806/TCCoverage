---
description: "Find the test cases a C/C++ change (CMake or autotools / Yocto) must be checked against (impacted callers, side effects, corner cases) with tcadvisor"
argument-hint: "working-tree | HEAD~1..HEAD | main..my-branch | ns::Class::method"
agent: agent
---

# TC Coverage

Change to analyse: `${input:change:working-tree}`

Follow the `tc-coverage` skill in `.github/skills/tc-coverage/SKILL.md` (written by `tcadvisor init`) with this
change as its input: confirm the build profile on the first run (section 0b), analyse with `PY -m tcadvisor
analyze --repo . <mode> --print brief -q` (`PY` = the `python` key of `.tcadvisor/config.json`), run its AI filter
(section 2) when the brief ends with `AI-VERIFY required`, and answer per its section 4 in the report language.
Never trace dependencies yourself, never read the whole code base, never write test code.
