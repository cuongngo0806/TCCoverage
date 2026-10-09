SC-005 pilot (codegraph): 14 scored regressions — surfaced 13, file-level only 1, missed 0; missed-case rate 7% (symbol level), 0% (file level); fixed code in the first 20 cases for 4/14; reached only through the graph (not a changed symbol) for 0/14

| intro → fix | subject | verdict | via | best case | rank / cases (P1) | flags | s |
|---|---|---|---|---|---|---|---|
| d1e228130 → eec6f1a | Fix duplicate registration warn to match major/minor | surfaced | root | P1 | 18 / 112 (42) | 5 | 62.5 |
| 30f8553c9 → a4c3a42 | Fix queue_size not counting pending_trains | surfaced | root | P1 | 50 / 1311 (224) | 60 | 269.4 |
| 30f8553c9 → bf9647c | fix lock order inversion | surfaced | root | P1 | 75 / 1311 (224) | 60 | 263.3 |
| 4062d4c97 → c631be6 | Fix network-tests using same ranges for client-ids | surfaced | root | P2 | 14 / 53 (6) | 3 | 73.6 |
| 710a8613e → a9f2002 | fix SIGSEGV in add_remote_service_info | surfaced | root | P1 | 347 / 3094 (883) | 813 | 552.7 |
| 7a30a430d → ff17ad4 | Fix integer overflow in `ASSIGN_CLIENT` payload deserializer | surfaced | root | P1 | 22 / 307 (63) | 7 | 163.5 |
| 38e9f99a1 → 723b482 | fix daemon build | no-source-truth | - | - | - / - (-) | - | - |
| 1a749b7e8 → 8b7e250 | Fix Android build issues | surfaced | root | P1 | 31 / 170 (38) | 15 | 70.1 |
| da754567d → af781c9 | Fix double connect | surfaced | root | P2 | 8 / 53 (6) | 5 | 102.4 |
| 2a4f05aa2 → 23a8282 | Fix subscribe triggered by stale ON_AVAILABLE | surfaced | root | P1 | 50 / 103 (61) | 4 | 53.5 |
| 8c97ab91b → bcc74a9 | Fix and test atomic stop offers | surfaced | root | P2 | 256 / 591 (179) | 41 | 237.1 |
| 30f8553c9 → 70598bb | fix availability loop on `send_cbk` | surfaced | root | P1 | 77 / 1311 (224) | 60 | 272.4 |
| 6ef7b4e12 → 4d9f466 | fix 'Target replaced' warnings after STR | file-level | - | - | - / 349 (99) | 24 | 243.8 |
| 91d3a2198 → 2a4f05a | fix deliver_notification/register_event race | surfaced | root | P1 | 94 / 779 (369) | 11 | 100.4 |
| 46bd8bf17 → 51faf63 | fix wrap around to VSOMEIP_SEC_PORT_UNSET on UDS | surfaced | root | P1 | 11 / 588 (266) | 33 | 179.1 |
