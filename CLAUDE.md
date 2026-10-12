# TCCoverage — Change Impact & Test Case Advisor

Given a C++/CMake change (commit range, working tree, or explicit symbols) `tcadvisor` produces an
**evidence-backed list of test cases to check** (risk group, priority, corner cases, impacted
callers/targets) plus a visual impact-flow report. It never writes tests, runs tests or edits the
analysed repo.

## Layout

- `src/tcadvisor/` — the tool. Pipeline order is fixed (constitution):
  `index/` (libclang + compile_commands + CMake File API) → `ingest/` (git diff → changed symbols) →
  `graph/impact.py` (bounded traversal) → `classify/` (rules.py risk groups, cases.py priority) →
  `evidence/` (uncertainty flags, evidence gate) → `llm/` (optional, off by default) → `report/`.
- `tests/` — pytest; `tests/conftest.py` builds a synthetic CMake project (needs cmake + clang).
- `src/tcadvisor/integrations/` — AI front-ends `tcadvisor init` installs into the analysed repo: `skills/tc-coverage/SKILL.md`
  (one skill for Claude Code `.claude/skills` and Copilot `.github/skills`), `claude/agents/`, `copilot/*.prompt.md`.
  This repo's `.claude/skills/tc-coverage` + `.claude/agents/tc-*` are copies (test-enforced: edit the package, then
  `tcadvisor init --repo . --ai claude --force` and delete the generated `.tcadvisor/`).
- `src/tcadvisor/config.py` — `<repo>/.tcadvisor/config.json` (graph, language, build_dir, output_dir, targets, max_hop_depth,
  include_tests, test_paths, ai_verify), shared by CLI / AI chat; `tcadvisor init [--ai claude,copilot|none]` (`integrations/init.py`).
- Unit-test code is left out unless `include_tests` (`pipeline.is_test_file`); benchmark scripts pass `--include-tests`.
- AI verdicts `not_needed` / `pass_by_review` close a case: `report.*` lists the cases still to test, `report.ai-verified.*`
  the closed ones (`report/render.split`); report.json keeps all.
- `src/tcadvisor/graph/providers/` — codegraph / GitNexus / clang impact source (`.tcadvisor/config.json` `graph`, never switched); `src/tcadvisor/verify/` — packets, annotate, headless Claude runner.
- Spec 006 (lessons + test report): `index/flow.py` + `graph/dataflow.py` (data paths A→B→C), `graph/sources.py`
  (sibling trigger sources), `classify/patterns.py` + `classify/lessons.py` (patterns, `.tcadvisor/lessons.json`),
  `report/results.py` (fillable report results, `--previous-report`, `tcadvisor results`).
- Spec 009 (`specs/009-side-effect-corner-cases`, side effects + corner cases): `classify/edits.py` (edit shapes → concrete corner cases, `removed_guard` P1),
  `classify/patterns.py` `coupling()` (readers of state a change no longer / differently produces), `test_gaps` in the report.
- `.claude/skills/tc-coverage`, `.claude/agents/{tc-coverage-analyst,tc-case-verifier,tc-verify-synthesizer}.md`,
  `.claude/workflows/{tc-verify,product-cycle}.js` — Claude front-end; see `docs/workflow.md` (models per step).
- `scripts/eval_real_project.py` — leveldb ground-truth eval (run before release).
- `scripts/pilot_regressions.py` + `scripts/szz_pairs.py` — SC-005 regression pilot (see `specs/003-pilot-large-projects/pilot.md`);
  `scripts/rank_lab.py` (offline ranking experiments), `scripts/ai_rank_eval.py` (AI view) — `specs/004-ranking-and-recall/results.md`.
  Change ranking/rules only with a benchmark run that shows dev *and* holdout do not get worse.
  Rule / hint changes: also run `scripts/seeded_regressions.py` (victims, corners, MRR on dev and holdout).
- `src/tcadvisor/classify/environment.py` — spec 009 (`specs/007-target-vs-review`): `verify_by` target|review per case; AI `pass_by_review`
  (gated in `verify/annotate.py`) closes review cases with proof — see `docs/workflow.md`.
- `specs/001-change-impact-test-advisor/` — speckit spec/plan/tasks; `.specify/memory/constitution.md` — rules.

## Commands

```bash
pip install -e '.[dev]'                       # libclang wheel + pytest/jsonschema
python3 -m pytest -q                          # full suite (~20 s)
python3 -m pytest -q tests/unit               # fast
python3 -m tcadvisor analyze --repo R --build-dir B --working-tree --output-dir OUT --print brief
python3 scripts/eval_real_project.py --quiet   # real-project acceptance (needs network + cmake)
python3 scripts/seeded_regressions.py          # 31 seeded side-effect regressions: leveldb dev + holdout, yaml-cpp
python3 scripts/seeded_regressions.py --min-victims yamlcpp=8 --min-corners yamlcpp=9   # CI recall gate (per-set thresholds)
```

## Spec-driven workflow with Claude (speckit)

Speckit skills are available for Claude in `.claude/skills/speckit-*` (`/speckit-specify`,
`/speckit-plan`, `/speckit-tasks`, `/speckit-implement`, `/speckit-analyze`, ...). Their helper scripts
are cross-platform: `python3 .specify/scripts/python/speckit.py <check-prerequisites|setup-plan|setup-tasks|resolve-template>`
(the PowerShell versions remain for Copilot on Windows). New features go in `specs/NNN-name/`.

## Token-efficient working rules

- Start from `specs/.../tasks.md` (unchecked items) — do not re-read spec/plan/research in full; grep them.
- Read files by range around what you need; run the narrowest pytest selection first, full suite before commit.
- When analysing a change for a user, use the `tc-coverage` skill: run the CLI with `--print brief` and never load
  `report.json`/`report.html` whole; delegate big reports to the `tc-coverage-analyst` subagent.
- Keep diffs small and match existing style (dataclasses, plain functions, no new dependencies).

## Non-negotiables (constitution)

Output is a case list (no test code). Every case has resolvable evidence. Dependency tracing is
deterministic; an LLM may only reword descriptions of already-emitted cases. Blind spots go to
`uncertainty_flags`, never silently dropped. Local-first: no source leaves the machine unless
`--llm-external-approved`. Code, docs, CLI messages and report.json text in English; the rendered report follows
`report_language` (vi default, en — `--language` / `.tcadvisor/config.json`) via `report/l10n/` catalogs: a new or
changed report sentence needs its `vi_*.py` entry (`scripts/l10n_check.py`, `tests/integration/test_l10n.py`).
