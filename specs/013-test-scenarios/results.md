# Results — spec 013 on the field run

Input: `human-test/remotecontrolapp/20261013-124545-61ffe19_cb62fef/report.json` (one commit, 6 files, 244 cases,
237 closed by AI), re-rendered with this branch (no re-analysis; scenarios are computed at render time).

| | before | after |
|---|---|---|
| Cases to test (main report) | 7 separate cases, 5–8 lines each | **4 scenarios** covering the 7 cases |
| All 244 cases (no AI filter) | 244 | **59 scenarios** (24 %; 43 call flows, 16 relation groups) |
| AI-closed report (237 cases) | 237 | 57 scenarios |
| Test plan text in report.md (diagram source excluded) | — | 39 lines, ≤ 10 per scenario, no duplicate check |
| Corner cases of TC-0001 / TC-0018 / TC-0153 | printed 3× | printed once under S1 |

The plan:

- **S1** P1 target — `processRxResSig → checkEndF → determineResSuspend*` covers TC-0153, TC-0018, TC-0001
- **S2** P2 target — `handleMessage → processOrderResp*` covers TC-0017, TC-0005
- **S3** P2 target — `completeFeature*` covers TC-0006
- **S4** P2 target — `RemoteEngineStart*` (class members) covers TC-0012

Include guards: the 20 `build_config_incomplete_macro` flags of the run were all `#ifndef X_H` guards of headers that
start with a multi-line `/* … */` license block (the old detector stripped comments line by line, so ` * Copyright`
counted as code). `_include_guard` now strips comments over the whole text; unit test
`test_include_guard_after_multiline_license_comment`. A new analysis of that commit should report none of them and
no longer route TC-0012 to the target for that reason (needs the user's workspace to confirm).

SC-004: case emission, priorities and ranking are untouched by the scenario layer (render-time only). The include-
guard fix only removes conditions that were include guards.
