# Quickstart: Change Impact & Test Case Advisor (MVP)

**Purpose**: Runnable validation scenarios proving the MVP works end-to-end against the pilot
module, mapped to the spec's User Stories and Success Criteria. See
[data-model.md](./data-model.md) for entity shapes and [contracts/](./contracts/) for the exact
CLI/JSON contracts referenced below.

## Prerequisites

1. Python 3.11+ with the advisor installed (`pip install -e .` from this workspace once
   implemented) and `libclang` available (system package or `pip install libclang`).
2. `git` available on `PATH`.
3. The pilot module's CMake build is configured with the CMake File API query directory present
   **before** configuring, and `CMAKE_EXPORT_COMPILE_COMMANDS=ON`:

   ```text
   mkdir -p D:\Honda\sourceCode\honda_con_release\remotecontrolapp\unittests\build\.cmake\api\v1\query
   touch D:\Honda\sourceCode\honda_con_release\remotecontrolapp\unittests\build\.cmake\api\v1\query\codemodel-v2
   cmake -S D:\Honda\sourceCode\honda_con_release\remotecontrolapp\unittests ^
         -B D:\Honda\sourceCode\honda_con_release\remotecontrolapp\unittests\build ^
         -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DWITH_LGE_UNIT_TESTS=ON
   ```

   Confirm artifacts exist: `unittests\build\compile_commands.json` and
   `unittests\build\.cmake\api\v1\reply\*codemodel-v2*.json`. If either is missing, this is the
   FR-013 prerequisite failure condition — do not proceed.

4. A curated list of known regression bugs for the pilot module (for SC-005), prepared by the
   `remotecontrolapp` team per the spec's Clarifications session, saved as e.g.
   `pilot-regressions.json` (format TBD in a future contract iteration — out of scope to finalize
   in this quickstart).

## Scenario 1 — Impact map + test case list from a git diff (User Story 1, P1)

```text
tcadvisor analyze ^
  --repo D:\Honda\sourceCode\honda_con_release\remotecontrolapp ^
  --build-dir D:\Honda\sourceCode\honda_con_release\remotecontrolapp\unittests\build ^
  --commit-range HEAD~1..HEAD ^
  --output-dir .\tcadvisor-report
```

**Expected outcome**: `tcadvisor-report\report.md` lists one or more test cases, each citing at
least one concrete file/symbol from `RemoteDoorLock`/`RemoteDoorUnlock` (or "no detected impact"
if the diff touched no tracked symbol). `report.json` validates against
`contracts/output-schema.json`. Run summary on stdout reports run time (target: < 10 min per
SC-001 for a ~50-file diff).

## Scenario 2 — No-op / comment-only diff (Edge Case)

Apply a comment-only change to `RemoteDoorLock.cpp`, commit it, then run Scenario 1's command
against that commit. **Expected outcome**: `test_case_candidates` is empty and the run summary
explicitly states "no detected impact" — not a bare empty list indistinguishable from failure.

## Scenario 3 — Explicit symbol input (User Story 1, Acceptance Scenario 3)

```text
tcadvisor analyze ^
  --repo D:\Honda\sourceCode\honda_con_release\remotecontrolapp ^
  --build-dir D:\Honda\sourceCode\honda_con_release\remotecontrolapp\unittests\build ^
  --symbols "rca::RemoteDoorLock::processOrderResp" ^
  --output-dir .\tcadvisor-report-explicit
```

**Expected outcome**: Same report shape as Scenario 1, with impact traced from exactly the named
method (FR-001a) — not from the entire `RemoteDoorLock.cpp` file.

## Scenario 4 — Cache hit on re-run (User Story 1, Acceptance Scenario 4 / SC-003)

Run Scenario 1's exact command twice in a row without any repo changes in between. **Expected
outcome**: second run's stdout summary reports `cache_hit: true` and completes markedly faster
than the first (cold-start) run.

## Scenario 5 — Risk classification coverage (User Story 2)

Using the synthetic fixtures under `tests/integration/fixtures/` (one small CMake project per risk
group — created during implementation, not in this quickstart), run `tcadvisor analyze` against
each fixture's prepared diff and confirm the expected `risk_group` appears in `report.json` for:
ABI/layout (header member reorder), thread safety (new `std::mutex`), exception safety (`noexcept`
removed). Each fixture is a standalone pytest integration test, not a manual step in production
use.

## Scenario 6 — Uncertainty flagging (User Story 4)

Using a synthetic fixture with a template with zero instantiations and a DI-routed call, confirm
`report.json`'s `uncertainty_flags` array contains entries with `category` =
`uninstantiated_template` and `di_config_routing` respectively, and that these symbols do **not**
also appear in `test_case_candidates` (they must be flagged, not fabricated into a case).

## Scenario 7 — LLM-disabled (default) determinism check

Run Scenario 1 twice with `--no-llm` (the default). **Expected outcome**: `llm_enabled: false`,
`llm_degraded: false`, `llm_token_usage: null`, and `test_case_candidates` ids/content are
byte-for-byte identical across both runs (proves the deterministic template fallback path, FR-012a,
is reproducible).

## Scenario 8 — MVP acceptance gate (SC-005)

Compare the `test_case_candidates` + `uncertainty_flags` produced for each historical regression
commit in `pilot-regressions.json` against the actual regression's known impacted area. Record:
(a) the fraction of regressions whose impacted symbol/file was surfaced by at least one emitted
case, and (b) whether any regression's area was silently absent from both the case list and the
uncertainty-flag list (a constitution violation if so, per Principle IV). This produces the MVP's
baseline missed-case rate (SC-005) — the quickstart does not require hitting a specific target
number, only that the baseline is captured and nothing was silently dropped.
