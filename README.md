# TCCoverage — Change Impact & Test Case Advisor

For a C++/CMake change, `tcadvisor` tells you **which test cases to check**: the changed symbols,
their risk category (logic, ABI/layout, ownership/lifetime, thread safety, exception safety, build
config), every caller / subclass / user / includer up to N hops, corner cases to exercise, the CMake
targets to rebuild/retest, and the blind spots that need manual review. Results come as Markdown,
JSON, a token-lean brief, and an **interactive HTML impact-flow report**.

![report](docs/report-leveldb-verified.png)

**Impact comes from a code graph** (codegraph by default, GitNexus opt-in, or the built-in libclang graph);
**AI only verifies** the deterministic cases and adds corner cases — see [docs/workflow.md](docs/workflow.md)
for the agent/model workflow and the product-development cycle. Real-project evaluation on
google/leveldb: [specs/002…/eval.md](specs/002-graph-providers-ai-verify/eval.md). **Pilot on large projects**
(COVESA vsomeip 133k LOC, RocksDB 898k LOC; 23 real regressions, 0 missed, 87 % at the fixed function):
[specs/003…/pilot.md](specs/003-pilot-large-projects/pilot.md). **Cycle 4** (55 regressions, dev/holdout):
0 missed, 51/55 at the fixed function, MRR ~0.12 → ~0.35, the later-fixed function in the first 10 cases for 26/55
(29/55 with the optional AI-triaged view) —
[specs/004…/results.md](specs/004-ranking-and-recall/results.md).

Three front-ends share the same engine:

| Front-end | Where | Use |
|---|---|---|
| CLI | `tcadvisor analyze …` | CI / pre-submit, scripting |
| Claude Code | `/tc-coverage HEAD~1..HEAD` (skill) + `tc-coverage-analyst` subagent | conversational review with concrete test scenarios |
| VS Code | `vscode-extension/` (`.vsix`) | tree of cases, inline hints, report webview |

## How it works (deterministic first)

1. **Index** every translation unit of `compile_commands.json` with libclang: functions, classes, macros and
   their `call`, `inherit_override`, `uses_type`, `instantiate`, `macro_expand`, `include` edges. Cached per TU in
   SQLite keyed by content hashes → only changed TUs are re-parsed.
2. **Diff → changed symbols**: each changed file is parsed old/new; symbols are compared on comment-free
   token streams, so comment/format-only edits yield *no detected impact*.
3. **Risk rules** (additive) classify each change; **traversal** walks dependents up to `--max-hop-depth` (2).
4. **Cases** per (impacted node × risk group) with deterministic priority: direct + high-severity = P1,
   direct or high-severity = P2, else P3. Every case carries file:line evidence (evidence gate).
5. **Uncertainty flags**: uninstantiated templates, DI/virtual-only methods, callbacks/function pointers,
   macro branches not compiled in any configuration.
6. Optional local LLM (Ollama) may only reword descriptions; off by default and degrades gracefully.

## Graph providers

```bash
npm i -g @colbymchenry/codegraph     # MIT — default for --graph auto
npm i -g gitnexus                    # optional; PolyForm-Noncommercial license, check before commercial use
tcadvisor analyze ... --graph auto|codegraph|gitnexus|clang
```

With a graph provider the libclang index is replaced by a fast `#include` scan (`--index auto|full|lite`),
so ~1M-line code bases analyse in minutes. With codegraph/GitNexus a compile database is optional (results are marked *reduced accuracy* without it);
with it, change classification and CMake target mapping are exact.

## AI verification (optional, explicit opt-in)

```bash
tcadvisor verify ../tcadvisor-report/report.json --ai-external-approved   # Haiku per batch + 1 Sonnet call
```

Sends only packed code windows (≤40 lines per impacted symbol) through the Claude Code CLI. Verdicts are
annotations; no case is ever removed by a model.

## Install

```bash
pip install -e .            # Python ≥ 3.11, pulls the libclang wheel
```

Prepare the analysed project once (the advisor only reads these artifacts, it never configures your build):

```bash
mkdir -p build/.cmake/api/v1/query && touch build/.cmake/api/v1/query/codemodel-v2
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
```

## CLI

```bash
tcadvisor analyze --repo /path/repo --build-dir /path/repo/build --commit-range HEAD~1..HEAD \
                  --output-dir ../tcadvisor-report [--targets RemoteDoorLock,RemoteDoorUnlock]
tcadvisor analyze ... --working-tree                 # uncommitted changes
tcadvisor analyze ... --symbols rca::RemoteDoorLock::processOrderResp
tcadvisor analyze ... --print brief                  # compact output for AI assistants / PR comments
tcadvisor render ../tcadvisor-report/report.json     # re-render md/html
tcadvisor cache clear --repo /path/repo
```

Exit codes: 0 ok · 1 prerequisite (compile db / File API missing or stale) · 2 usage · 3 internal.
Outputs: `report.md` (with Mermaid flow), `report.json` (schema: `specs/001-change-impact-test-advisor/contracts/output-schema.json`),
`report.html`, `report.brief.txt`.

## Claude Code

Open this repo (or copy `.claude/skills/tc-coverage` and `.claude/agents/tc-coverage-analyst.md` into your
project's `.claude/`) and run `/tc-coverage HEAD~1..HEAD`. Claude runs the CLI with `--print brief`, reads
only evidence windows for P1 cases, and answers with concrete test scenarios — the expensive dependency
tracing is never done by the model, which keeps token usage small. Speckit commands for Claude:
`/speckit-specify`, `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`, …

## VS Code

```bash
cd vscode-extension && npm install && npm run compile && npx @vscode/vsce package
code --install-extension tc-coverage-0.1.0.vsix
```

See `vscode-extension/README.md`.

## Development

```bash
pip install -e '.[dev]' && python3 -m pytest -q
```

Spec-driven docs: `specs/001-change-impact-test-advisor/` (spec, plan, tasks). Project rules:
`.specify/memory/constitution.md`. Remaining acceptance step: pilot run on `remotecontrolapp`
(tasks.md T032).
