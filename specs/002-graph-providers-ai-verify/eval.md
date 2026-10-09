# Cycle 2 evaluation — google/leveldb `bb74ef7` ("Add SetCapacity method to leveldb::Cache")

Reproduce: `TCADVISOR_CODEGRAPH=… TCADVISOR_GITNEXUS=… python3 scripts/eval_real_project.py`
(raw numbers: `eval-leveldb.json`).

| | cycle 1 (clang) | cycle 2 clang | cycle 2 codegraph | cycle 2 GitNexus |
|---|---|---|---|---|
| test cases | **271** | 23 | 25 | 15 |
| P1 | 29 | 7 | 9 | 6 |
| uncertainty flags | 4 | 2 | 0 | 6 |
| existing tests found | – | – | `CacheTest.SetCapacity` | – |
| cold run | 22.5 s | 23 s | 7 s | 36 s |

Ground-truth expectations (all hold for every provider): `Cache` vtable change is P1; the `MutexLock` in
`LRUCache::SetCapacity` is a thread-safety risk; the include guard is not a build-config condition; < 60
cases. codegraph additionally: re-run `CacheTest.SetCapacity` (the test the commit itself added) and
`ShardedLRUCache` reached through inheritance.

## Defects found by the real run and fixed in this cycle

1. Include guards (`#ifndef X_H_`) were treated as build conditions → every header change got `build_config`.
2. `&&` in expressions was read as move semantics.
3. Any class token change propagated to every user of the type (Cache: 200+ nodes) → now only when
   data layout / bases change; vtable-only changes reach subclasses + includers.
4. Project lock wrappers (`MutexLock`) were not recognised as thread-safety signals.
5. codegraph reports a data member `Cache* cache_;` as `extends` → base specifiers are validated against
   the class head.
6. `contains` edges were followed from every class on the path → only from the changed class.
7. Run cache was keyed by version only → now also by analyzer code digest.

## AI verification (Haiku ×3 + Sonnet ×1)

15 confirmed / 5 weak / 5 needs_info; 40.6k input / 19.4k output tokens; $0.065; 63 s. Notable additions
the graph cannot produce: "a deleter that calls Insert/Lookup/Erase on the same shard while SetCapacity holds
`mutex_` self-deadlocks", "subclass built against the old header silently ignores resize calls through
`Cache*`", shard capacity rounding at 0 / huge values. All 5 needs_info were file-level packets without
code → fixed (packets for file nodes now carry the lines that reference changed symbols).

## Review pass (Sonnet reviewer, 10 findings) — fixed in this cycle

- `tcCoverage.ai.approved` (and executable paths) were workspace-settable → a cloned repo could
  pre-approve sending code. Now machine-scoped; the extension stores approval globally only after a modal.
- Provider failure / unresolved root only produced a note → impact could vanish silently. Now the root falls
  back to the compile-database graph, or becomes an uncertainty flag when none exists (test added).
- Provider nodes without a source file aborted the evidence gate → dropped with a note.
- Malformed provider JSON / failing `init`/`sync` aborted the run → caught, falls back.
- Commit range with a different checkout: provider results now bypass the run cache and carry a note.
- AI "also check" evidence was unvalidated free text and the extension could open paths outside the repo →
  only `file:line` inside the repo is kept, others are labelled "unverified AI suggestion"; `openEvidence`
  is confined to the repo.
- `weak`/`recheck:false` read like an AI exclusion → `recheck` no longer comes from the model; neutral icon.
- `claude -p` ran with the analysed repo as cwd (its hooks/CLAUDE.md could load) → temp cwd +
  `--setting-sources user`; all-batches-failed now exits 3.
- Workflow args were interpolated unquoted into a shell command and had no approval → POSIX quoting, mode
  whitelist, `args.approved` required.
- Not changed (by design): a vtable-only class change propagates to subclasses and includers (recompile
  cases), not to every user of the type — on leveldb that is the difference between 23 and 271 cases. Revisit
  if a missed regression proves otherwise (constitution "recall tracking").

## Workflow run (`tc-verify`, Claude Code Workflow tool)

First attempt failed: agent types created mid-session are not registered until the next session → the
workflow now references `.claude/agents/*.md` by path. Second run: 5 agents, 25/25 cases verified,
4 additional checks, ~231k subagent tokens (vs ~60k for the headless `tcadvisor verify` path).
