# Spec 011 — Pilot feedback: less noise, one language, skills instead of the VS Code extension

Source: first run on a real workspace (`human-test/remotecontrolapp`, one commit, 3 changed files): 79 cases
(P1 1 / P2 51 / P3 27), of which 39 were unit-test re-runs / test includers and most of the rest recompile-only
includers; the Vietnamese report still showed English fragments; the VS Code extension was little used.

## Requirements

- **FR-1 (language)**: no English sentence fragment in a `vi` report: sub-reason tags (`— header change`,
  `(removed, signature change)`), AI verdicts, the summary line (`cache_hit`, empty targets), the "needs the
  target" reasons (`… at file:line`), the uncertainty reason without a compile database, and a template that
  swallows a nested English sentence into a plain placeholder (`Reachable from changed …: … was removed; …`).
- **FR-2 (unit tests)**: unit-test / mock code is out of scope unless `include_tests` (config) / `--include-tests`:
  changed test code goes to `out_of_scope`, impacted test functions / files are dropped from the impact graph,
  trigger sources and lesson-pattern cases, no `existing_tests`, no `test_gaps`; a run note counts what was left
  out. `test_paths` (config) adds globs. Benchmark scripts pass `--include-tests` (their numbers stay comparable).
- **FR-3 (AI filter)**: verdict `not_needed` (with a note) besides `pass_by_review` closes a case; closed cases leave
  `report.md` / `report.html` / brief for `report.ai-verified.md` / `.html`; report.json keeps every case. Config
  `ai_verify`: `off` | `chat` (the skill / prompt verifies every analysis; the brief ends with `AI-VERIFY required`)
  | `claude` (`analyze` runs the headless Claude Code verification). `weak` in older verdict files reads as
  `not_needed`. Constitution 1.3.0.
- **FR-4 (front-ends)**: the VS Code extension is removed. `tcadvisor init` installs one `tc-coverage` skill for
  Claude Code (`.claude/skills`, plus the subagents in `.claude/agents`) and GitHub Copilot (`.github/skills`, plus
  the `/tc-coverage`, `/tc-verify` prompts), and writes the config with `include_tests: false`, `ai_verify: chat`.

## Tests

`tests/integration/test_unit_tests_excluded.py`, `tests/integration/test_config_init.py` (init, AI-VERIFY marker,
`ai_verify: claude` with a fake `claude`, packaged skill == this repo's copy), `tests/unit/test_environment.py`
(`not_needed`, report split), `tests/integration/test_l10n.py` + the session l10n gate.

## Result on the pilot data (re-rendered from its report.json + verdicts.json)

Main report 79 → 32 cases (47 closed by AI into `report.ai-verified.*`). The 32 left: 5 cases the AI confirmed,
9 unit-test cases that FR-2 removes on a new analysis (the report predates it) and 18 P3 cases the pilot did not
pack for verification (verify-pack now defaults to P1,P2,P3). Expected on a new run: 5 confirmed + what the AI
keeps of those 18.
