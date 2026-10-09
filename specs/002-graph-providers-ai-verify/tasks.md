# Tasks: Graph providers + AI verification (cycle 2)

## Phase 1: Lessons from the real project (US5)
- [ ] T201 [US5] Ignore include guards in `conditional_stack` in `src/tcadvisor/ingest/changes.py`
- [ ] T202 [US5] `&&` counts as move semantics only in declarations in `src/tcadvisor/classify/rules.py`
- [ ] T203 [US5] Class roots propagate via uses_type only when layout/vtable/bases changed (`src/tcadvisor/pipeline.py`)
- [ ] T204 [US5] Pure-virtual-added hint; unit tests in `tests/unit/test_rules.py`

## Phase 2: Graph providers (US1)
- [ ] T205 [US1] Provider interface + registry in `src/tcadvisor/graph/providers/base.py`
- [ ] T206 [P] [US1] codegraph adapter in `src/tcadvisor/graph/providers/codegraph.py`
- [ ] T207 [P] [US1] GitNexus adapter (+boundaries → flags) in `src/tcadvisor/graph/providers/gitnexus.py`
- [ ] T208 [US1] `--graph`, optional compile db / File API in `src/tcadvisor/pipeline.py`, `cli/main.py`
- [ ] T209 [US1] Provider tests with recorded JSON fixtures in `tests/unit/test_providers.py`

## Phase 3: AI verification (US2)
- [ ] T210 [US2] `verify-pack` in `src/tcadvisor/verify/pack.py`
- [ ] T211 [US2] `annotate` in `src/tcadvisor/verify/annotate.py` + renderers show verdicts
- [ ] T212 [US2] Agents `tc-case-verifier` (haiku), `tc-verify-synthesizer` (sonnet); skill update

## Phase 4: Workflows (US3)
- [ ] T213 [US3] `.claude/workflows/tc-verify.js`
- [ ] T214 [US3] `.claude/workflows/product-cycle.js` + `docs/workflow.md`

## Phase 5: VS Code (US4)
- [ ] T215 [US4] graphProvider setting, Verify with Claude command, verdict badges; package `.vsix`

## Phase 6: Evaluate & release
- [ ] T216 Run on leveldb with each provider; record `eval.md`
- [ ] T217 Run tc-verify workflow on the leveldb report
- [ ] T218 Code review pass, fix findings, full test suite, package, retro → next-cycle backlog
