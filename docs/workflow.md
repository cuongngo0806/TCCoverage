# TC Coverage — workflows, agents and models

Two loops share one rule: **graphs decide impact, models only verify and enrich.**

## 1. Runtime loop (every change a developer makes)

```text
 git diff ─► tcadvisor analyze --graph auto ───────────────► report.json/.md/.html/brief   ($0, deterministic)
              │  changed symbols: libclang token diff + risk rules
              │  impact: codegraph (default) | GitNexus (opt-in) | libclang
              ▼
 tcadvisor verify-pack ─► batch-NN.json (≤8 symbols, ≤40 code lines each, code sent once per symbol)
              ▼
 tc-case-verifier ×N   (Haiku, no tools, parallel)  ── verdict + ≤3 concrete corner cases per case
              ▼
 tc-verify-synthesizer ×1 (Sonnet, no tools)        ── summary + ≤8 cross-cutting "also check"
              ▼
 tcadvisor annotate ─► report (+verification) ─► VS Code tree badges / webview / inline hints
```

Ways to run it — all produce the same annotated report:

| Entry point | Command |
|---|---|
| VS Code | *TC Coverage: Analyze …* then *Verify Cases with Claude (AI)* |
| CLI / CI | `tcadvisor analyze … --graph auto` then `tcadvisor verify <out>/report.json --ai-external-approved` |
| Claude Code chat | `/tc-coverage HEAD~1..HEAD` (skill; delegates to the agents below) |
| Claude Code workflow | Workflow `tc-verify` with args `{repo, buildDir, mode, graph}` |

### Model allocation and measured cost (google/leveldb `bb74ef7`, 25 cases)

| Step | Who | Model | Calls | Measured |
|---|---|---|---|---|
| Index + impact + rules + priority | codegraph + tcadvisor | none | – | 7 s cold, <1 s warm |
| Packets | `tcadvisor verify-pack` | none | – | 3 batches, ~8.8k tokens of input |
| Case verification | `tc-case-verifier` | Haiku | 3 | |
| Synthesis | `tc-verify-synthesizer` | Sonnet | 1 | |
| **Total AI** | | | **4** | **40.6k in / 19.4k out tokens, $0.065, 63 s** |

Why it is cheap: the model never explores the repository. Code reaches it once per impacted symbol in a
bounded window. Haiku does the many small checks; Sonnet makes the one judgement call. Opus is not used
at runtime.

### Verdict semantics (constitution III)

`confirmed` / `weak` / `needs_info` are **annotations**. No case is removed, reordered or re-prioritised by a
model. `weak` + `recheck:false` lets a reviewer skip a case consciously; the deterministic list stays auditable.

## 2. Product-development cycle (building the tool itself)

Saved workflow `.claude/workflows/product-cycle.js` (args `{feature}` or `{specDir}`):

```text
 Specify ─► Plan+Tasks ─► Analyze gate ─► Implement ─► Test (+fix ≤2) ─► Review (2 lenses, +fix) ─► Package .vsix ─► Retro
    ▲                                                                                                          │
    └──────────────────────────────── next-cycle backlog (retro.md) ◄──────────────────────────────────────────┘
```

| Phase | Skill / tool | Model | Gate |
|---|---|---|---|
| Specify | speckit-specify (assumptions recorded instead of interactive clarify) | session (Opus) | – |
| Plan, Tasks | speckit-plan, speckit-tasks | Sonnet | – |
| Analyze | speckit-analyze (read-only) | Sonnet, low effort | stop on CRITICAL constitution issue |
| Implement | speckit-implement, one sequential worker | Sonnet | narrow pytest per task |
| Test | `pytest` + `scripts/eval_real_project.py` (leveldb ground truth) | Haiku | fix loop with Sonnet, max 2 |
| Review | correctness lens ∥ constitution lens | Sonnet | blocking findings fixed |
| Package | `npm run compile`, `vsce package` | Haiku | `.vsix` exists |
| Retro | writes `specs/NNN/retro.md` + backlog | Haiku | backlog feeds next Specify |

Token rules for every agent: start from `tasks.md`; read files by range; never load `report.json`/`report.html`
whole (use `report.brief.txt`); narrowest test first, full suite before handing over.

## 3. Graph providers

| Provider | License | Index | Strengths seen on leveldb | Weaknesses seen |
|---|---|---|---|---|
| codegraph | MIT | `.codegraph/` (SQLite, tree-sitter) | finds tests (`CacheTest.SetCapacity`), override chains, 7 s | heuristic edges (a `Cache* cache_` member reported as `extends` — filtered by tcadvisor) |
| GitNexus | PolyForm-Noncommercial | `.gitnexus/` (graph DB) | execution flows, explicit "boundaries" (unresolved receivers → uncertainty flags) | commercial use needs a license decision; 25–35 s; fewer C++ edges |
| libclang (built-in) | Apache-2.0 (LLVM) | per-TU cache | exact semantics from compile_commands.json | only sees compiled TUs (tests off ⇒ no tests found) |

Both external tools keep their index inside the analysed repo; tcadvisor adds the directory to
`.git/info/exclude`, disables codegraph telemetry and runs GitNexus with `--index-only` so no
AGENTS.md/CLAUDE.md/skills are written into your repository.
