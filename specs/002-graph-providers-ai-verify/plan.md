# Plan: Graph providers + AI verification (cycle 2)

## Architecture

```text
git diff ──► ingest/changes.py (libclang token diff; fallback flags when no compile db)
                 │ changed roots (+ deterministic risk rules)
                 ▼
         graph/providers/{codegraph,gitnexus,clang}.py  ── impact nodes/edges (+ boundaries)
                 ▼
         classify/cases.py (deterministic priority) → evidence gate → report.json/md/html/brief
                 ▼                                   (deterministic, $0 tokens)
         tcadvisor verify-pack  → packets/*.json (case + ≤40 lines evidence)
                 ▼
   Claude: tc-case-verifier ×N (Haiku, batches of 8) → tc-verify-synthesizer (Sonnet)
                 ▼
         tcadvisor annotate verdicts.json → report (+verification) → VS Code tree/webview
```

## Model allocation (token budget)

| Step | Who | Model | Why |
|---|---|---|---|
| Impact graph, rules, priority | codegraph/GitNexus/libclang + tcadvisor | none | deterministic, free |
| Case verification (per packet batch) | `tc-case-verifier` | Haiku | short, bounded context, many calls |
| Merge + "what else to test" | `tc-verify-synthesizer` | Sonnet | one call, needs judgement |
| Dev cycle: specify/plan/review | main session | Opus/Sonnet | few, high-leverage decisions |
| Dev cycle: implement tasks | worker agents | Sonnet | bulk code |
| Dev cycle: test/package/retro bookkeeping | worker agents | Haiku | mechanical |

## Structure

- `src/tcadvisor/graph/providers/` (`base.py`, `codegraph.py`, `gitnexus.py`)
- `src/tcadvisor/verify/` (`pack.py`, `annotate.py`)
- `.claude/agents/tc-case-verifier.md`, `.claude/agents/tc-verify-synthesizer.md`
- `.claude/workflows/tc-verify.js`, `.claude/workflows/product-cycle.js`, `docs/workflow.md`
- `vscode-extension/src/extension.ts` (provider setting, verify command, verdict badges)

## Constitution check

I (list only) ✔ · II (evidence: provider nodes carry file:line, gate unchanged) ✔ · III (LLM annotates
only; tracing by graph tools) ✔ · IV (provider boundaries → flags) ✔ · V (providers incremental:
`codegraph sync`, GitNexus parse cache) ✔ · VI (local by default; cloud verification is an explicit
user action) ✔ · VIII (index dirs excluded via `.git/info/exclude`, `--index-only`) ✔ · IX ✔
