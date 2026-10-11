# Retro — cycle 2 (graph providers + AI verification)

## Shipped
- Impact from codegraph (default) / GitNexus (opt-in) / libclang, normalised into one graph; tests reached by
  the impact are listed for re-run (`--gtest_filter`).
- AI verification as annotations: `verify-pack` → Haiku per batch → Sonnet synthesis → `annotate`; available as
  CLI, VS Code button, Claude skill and `tc-verify` workflow. Product cycle as `product-cycle` workflow.
- VS Code 0.2.0: provider setting, Verify with Claude, verdict badges, tests to re-run, AI checks.
- Real-project eval (leveldb) as an automated gate; 52 pytest tests; extension smoke test.

## Numbers
- leveldb `bb74ef7`: 271 → 25 cases (codegraph), 9 P1, the commit's own test found; all ground-truth checks pass.
- AI verification: 4 calls, ~60k tokens, $0.065 (CLI) vs ~231k tokens (workflow).

## What went wrong
- Cycle 1 rules were only tested on a synthetic fixture → 271 noisy cases on the first real project.
  Lesson: real-project eval is now part of Test.
- Workflow relied on agent types registered at session start.
- The first review pass found 3 blocking issues (pre-approval via workspace settings, silent provider
  misses, vtable propagation question) — review stays mandatory in every cycle.

## Next-cycle backlog
1. Pilot run on `remotecontrolapp` (`RemoteDoorLock`, `RemoteDoorUnlock`) + curated regression list (SC-005).
2. Hybrid graph: union codegraph + libclang edges with a "confirmed by both" marker (recall + confidence).
3. Second real project in the eval (a codebase with heavy templates/DI, e.g. a Qt or ROS module).
4. `tcadvisor checklist` export: verified P1/P2 + gtest filter as a PR comment.
5. VS Code: run tests from the "Existing tests to re-run" group through the user's own test task (no execution
   inside tcadvisor — constitution VIII).
6. Run VS Code integration tests in CI where the VS Code download is allowed.
