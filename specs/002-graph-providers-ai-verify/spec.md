# Feature Specification: Graph-Provider Impact + AI Verification Workflow (cycle 2)

**Feature Branch**: `002-graph-providers-ai-verify` · **Created**: 2026-10-09 · **Status**: Implemented (cycle 2)

**Input**: "Impact of a change must be known mainly through codegraph or GitNexus; the AI skill only
verifies, adds information, corner cases and says which TCs must be re-checked. Use agents/models
sensibly to save tokens. Run it as a complete product-development-cycle workflow whose destination is
a VS Code extension. Test it on a real C++ project."

## Clarifications (decided, cycle 2)

- Q: Which graph tool is the default? → A: **codegraph** (`@colbymchenry/codegraph`, MIT, tree-sitter,
  local SQLite). **GitNexus** is supported but opt-in only, because its license is
  PolyForm-Noncommercial-1.0.0 (commercial use at the team requires a separate license decision).
  The built-in libclang graph stays as the third provider and as a cross-check.
- Q: Is `compile_commands.json` still a hard prerequisite? → A: Only for the `clang` provider. With
  codegraph/GitNexus it is optional: when present it sharpens change classification and target mapping;
  when absent the run is marked `reduced_accuracy` in `run_notes` (FR-013 amended, not silently degraded).
- Q: May the AI drop cases it believes are false positives? → A: No (constitution III). AI output is an
  **annotation** (`verification`: confirmed | weak | needs_info, extra corner cases, re-check flag);
  every deterministic case stays in the report.
- Q: Do graph tools write into the analysed repo? → A: They keep an index dir (`.codegraph/`,
  `.gitnexus/`). The advisor runs GitNexus with `--index-only` (no AGENTS.md/CLAUDE.md/skills) and
  disables codegraph telemetry; both index dirs are added to `.git/info/exclude`, never to tracked files.

## User Stories

### US1 — Impact from a graph tool (P1)
A developer selects `--graph codegraph` (default when installed) or `--graph gitnexus`; changed symbols
are mapped to graph nodes and the blast radius (callers, overrides, contained members, includers,
execution flows for GitNexus) comes from that tool. **Test**: leveldb commit `bb74ef7`
(`Cache::SetCapacity`) yields callers of the changed methods with file:line evidence from the provider.

### US2 — Token-lean AI verification (P1)
After the deterministic report exists, `tcadvisor verify-pack` writes one compact packet per P1/P2 case
(case + ≤40 lines of evidence code). Cheap agents (Haiku) verify packets in parallel, one synthesis agent
(Sonnet) merges, `tcadvisor annotate` writes verdicts back. **Test**: annotate round-trip keeps all ids,
adds `verification` to the requested cases only.

### US3 — Product-cycle workflow (P2)
`.claude/workflows/product-cycle.js` runs specify → plan → tasks → implement → test → review →
package → retro with a fixed model per phase; `.claude/workflows/tc-verify.js` runs the runtime
verification. **Test**: both scripts parse and are documented in `docs/workflow.md`.

### US4 — VS Code is the destination (P1)
The extension gets `tcCoverage.graphProvider`, a **Verify with Claude** command (headless `claude -p`
with the verifier agents) and shows verdict badges in the tree and report. **Test**: `.vsix` builds.

### US5 — Lessons from the real-project run are fixed (P1)
Noise found on leveldb (271 cases) is reduced without losing the real risks: include guards are not
build-config conditions; `&&` in expressions is not move semantics; a class change only propagates to
users when layout/vtable/bases changed; new pure virtuals get an "every external implementation breaks"
hint. **Test**: unit tests + leveldb case count drops while `Cache` vtable change stays P1.

## Functional Requirements

- **FR-201** `--graph {auto,codegraph,gitnexus,clang}`; `auto` = codegraph if on PATH/configured, else clang.
- **FR-202** Provider output is normalised to the existing ImpactNode/ImpactEdge model; provider
  heuristics (e.g. codegraph `provenance: heuristic`, GitNexus `confidence`) are kept on the edge.
- **FR-203** GitNexus `boundaries` (unresolved receivers, dispatch boundaries) become `uncertainty_flags`.
- **FR-204** `verify-pack` / `annotate` subcommands; verdicts never remove or re-prioritise cases.
- **FR-205** Report (MD/HTML/brief) and VS Code show verdicts and AI-added corner cases, labelled as AI.
- **FR-206** Every provider call is local; no source leaves the machine unless the user runs a cloud
  model on the packets (that step is explicit: the Claude verify command/workflow).

## Success Criteria

- **SC-201** leveldb `HEAD~1..HEAD` analysed with codegraph and clang; results and timings recorded in
  `eval.md`.
- **SC-202** Verification of a ≤40-case report costs ≤ ~1 Sonnet call + N/8 Haiku calls (packets batched by 8).
- **SC-203** Full pytest suite green; `.vsix` packaged.
