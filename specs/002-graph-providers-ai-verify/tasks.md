# Tasks: Graph providers + AI verification (cycle 2)

## Phase 1: Lessons from the real project (US5)
- [x] T201 [US5] Ignore include guards in `conditional_stack` in `src/tcadvisor/ingest/changes.py`
- [x] T202 [US5] `&&` counts as move semantics only in declarations in `src/tcadvisor/classify/rules.py`
- [x] T203 [US5] Class roots propagate via uses_type only when layout/vtable/bases changed (`src/tcadvisor/pipeline.py`)
- [x] T204 [US5] Pure-virtual-added hint; unit tests in `tests/unit/test_rules.py`

## Phase 2: Graph providers (US1)
- [x] T205 [US1] Provider interface + registry in `src/tcadvisor/graph/providers/base.py`
- [x] T206 [P] [US1] codegraph adapter in `src/tcadvisor/graph/providers/codegraph.py`
- [x] T207 [P] [US1] GitNexus adapter (+boundaries → flags) in `src/tcadvisor/graph/providers/gitnexus.py`
- [x] T208 [US1] `--graph`, optional compile db / File API in `src/tcadvisor/pipeline.py`, `cli/main.py`
- [x] T209 [US1] Provider tests with recorded JSON fixtures in `tests/unit/test_providers.py`

## Phase 3: AI verification (US2)
- [x] T210 [US2] `verify-pack` in `src/tcadvisor/verify/pack.py`
- [x] T211 [US2] `annotate` in `src/tcadvisor/verify/annotate.py` + renderers show verdicts
- [x] T212 [US2] Agents `tc-case-verifier` (haiku), `tc-verify-synthesizer` (sonnet); skill update

## Phase 4: Workflows (US3)
- [x] T213 [US3] `.claude/workflows/tc-verify.js`
- [x] T214 [US3] `.claude/workflows/product-cycle.js` + `docs/workflow.md`

## Phase 5: VS Code (US4)
- [x] T215 [US4] graphProvider setting, Verify with Claude command, verdict badges; package `.vsix`

## Phase 6: Evaluate & release
- [x] T216 Run on leveldb with each provider; record `eval.md`
- [x] T217 Run tc-verify workflow on the leveldb report
- [x] T218 Code review pass, fix findings, full test suite, package, retro → next-cycle backlog

## Phase 7: Convergence
- [x] T219 CRITICAL: replace the silent skip of out-of-repo callees on changed lines (`src/tcadvisor/pipeline.py` `_add_changed_calls`, "standard library / third-party code") with an explicit `uncertainty_flags` entry naming the external call site per Constitution IV (contradicts)
- [x] T220 Route provider nodes without a source file (`src/tcadvisor/graph/providers/base.py` `build_overlay`) to `uncertainty_flags` instead of only a `run_notes` count per FR-202 / Constitution IV (partial)
