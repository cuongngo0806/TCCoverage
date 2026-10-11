| split | scored | surfaced | file-level | missed | via graph | top10 | top20 | top50 | MRR | median rank | median cases | median s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 39 | 36 | 3 | 0 | 2 | 7 | 12 | 20 | 0.064 | 50 | 588 | 149.9 |
| dev | 19 | 16 | 3 | 0 | 1 | 3 | 6 | 8 | 0.07 | 61 | 591 | 161.4 |
| holdout | 20 | 20 | 0 | 0 | 1 | 4 | 6 | 12 | 0.059 | 44.0 | 527.0 | 121.65 |

| intro → fix | subject | verdict | via | best | rank (symbol rank) / cases (P1) | flags | s |
|---|---|---|---|---|---|---|---|
| d1e228130 → eec6f1ae | Fix duplicate registration warn to match major/minor | surfaced | root | P1 | 20 (10) / 112 (42) | 5 | 55.6 |
| 30f8553c9 → a4c3a42d | Fix queue_size not counting pending_trains | surfaced | root | P1 | 50 (44) / 1311 (224) | 60 | 289.9 |
| 30f8553c9 → bf9647cb | fix lock order inversion | surfaced | root | P1 | 75 (69) / 1311 (224) | 60 | 282.9 |
| 4062d4c97 → c631be64 | Fix network-tests using same ranges for client-ids | surfaced | root | P2 | 14 (10) / 53 (6) | 3 | 62.2 |
| 710a8613e → a9f20026 | fix SIGSEGV in add_remote_service_info | surfaced | root | P1 | 347 (175) / 3094 (883) | 813 | 556.5 |
| 7a30a430d → ff17ad40 | Fix integer overflow in `ASSIGN_CLIENT` payload deseria | surfaced | root | P1 | 22 (9) / 307 (63) | 7 | 149.9 |
| 38e9f99a1 → 723b4820 | fix daemon build | no-source-truth | - | - | - (-) / - (-) | - | - |
| 1a749b7e8 → 8b7e2502 | Fix Android build issues | surfaced | root | P1 | 31 (21) / 170 (38) | 15 | 65.0 |
| da754567d → af781c9e | Fix double connect | surfaced | root | P2 | 11 (9) / 53 (6) | 5 | 95.0 |
| 2a4f05aa2 → 23a8282d | Fix subscribe triggered by stale ON_AVAILABLE | surfaced | root | P1 | 50 (12) / 103 (61) | 4 | 42.5 |
| 8c97ab91b → bcc74a90 | Fix and test atomic stop offers | surfaced | root | P2 | 256 (97) / 591 (179) | 41 | 226.3 |
| 30f8553c9 → 70598bba | fix availability loop on `send_cbk` | surfaced | root | P1 | 77 (71) / 1311 (224) | 60 | 262.3 |
| 6ef7b4e12 → 4d9f4661 | fix 'Target replaced' warnings after STR | file-level | - | - | - (-) / 349 (99) | 24 | 235.8 |
| 91d3a2198 → 2a4f05aa | fix deliver_notification/register_event race | surfaced | root | P1 | 94 (39) / 779 (369) | 11 | 83.8 |
| 46bd8bf17 → 51faf636 | fix wrap around to VSOMEIP_SEC_PORT_UNSET on UDS | surfaced | root | P1 | 11 (9) / 588 (266) | 33 | 168.2 |
| 1695955b0 → 823a7640 | fix payload not being printed on android | surfaced | root | P2 | 71 (28) / 198 (59) | 39 | 72.8 |
| 9933ad2c1 → 1fd7314d | fix log to file | surfaced | root | P1 | 37 (21) / 314 (60) | 14 | 26.1 |
| 11447b294 → da754567 | Fix UDP connection availability loop | surfaced | root | P1 | 38 (21) / 1148 (365) | 65 | 328.8 |
| 269e98393 → d87c412c | Fix missing lock in udp_client_endpoint | surfaced | root | P1 | 57 (56) / 1497 (539) | 71 | 300.1 |
| cc8c5a943 → 67a94651 | Fix missing clean-up of pinged clients | surfaced | root | P2 | 148 (94) / 277 (110) | 10 | 93.4 |
| 7c3f82cde → 2f2f2dbc | fix drop of udp errors | surfaced | root | P2 | 3 (3) / 37 (0) | 1 | 22.4 |
| 46bd8bf17 → 30f3498e | Fix availability, host state, tcp address race in rmc | surfaced | root | P1 | 6 (4) / 588 (266) | 33 | 169.8 |
| 05f8f469b → 1bdf66fb | Fix logger include | file-level | - | - | - (-) / 433 (145) | 56 | 161.4 |
| 07b13fa64 → 1898c18b | Fix detached dispatcher thread | surfaced | root | P1 | 3 (2) / 14 (4) | 5 | 17.3 |
| 11447b294 → bd7eadf9 | fix routingmanagerd deadlock | surfaced | root | P2 | 399 (205) / 1148 (365) | 65 | 335.6 |
| 11447b294 → 04911817 | Fix selective event subscription race | surfaced | root | P1 | 119 (73) / 1148 (365) | 65 | 338.3 |
| 03f8ed529 → 7104c72e | fix logger_ext.hpp include path | file-level | - | - | - (-) / 1451 (8) | 2 | 373.9 |
| 30f8553c9 → dc21ddbe | fix test flakiness | surfaced | root | P1 | 18 (12) / 1311 (224) | 60 | 257.7 |
| 1e7a7b044 → da2bc0e4 | Fix get_connected_clients after rearch | surfaced | root | P1 | 156 (82) / 843 (308) | 35 | 243.5 |
| 1e7a7b044 → 3d262d8c | fix for a "never cleaned up" local_endpoint (routing) | surfaced | impacted | P2 | 716 (211) / 843 (308) | 35 | 238.4 |
| a5fb6b28f → 4cb092ca | fix missing find on resume | surfaced | root | P2 | 9 (9) / 29 (0) | 5 | 19.8 |
| 710a8613e → 3e3d9c64 | fix delayed availability | surfaced | root | P1 | 347 (175) / 3094 (883) | 813 | 519.5 |
| 200815b21 → 35732ef1 | Fix plugin_manager_impl singleton free-after-use on dto | surfaced | root | P1 | 22 (10) / 762 (189) | 13 | 79.8 |
| 7f40d9c53 → 17ee63e7 | fix logging prefix in flush function | surfaced | root | P1 | 7 (7) / 60 (19) | 7 | 81.6 |
| 60c83e0b4 → c69e067f | Fix double stop race condition | surfaced | root | P1 | 2 (2) / 14 (5) | 0 | 23.9 |
| b1e7bab5d → 88d868f8 | Fix availability inconsistency | surfaced | root | P1 | 78 (72) / 606 (234) | 73 | 190.5 |
| 200815b21 → da1fdec2 | Fix broken android build when ANDROID_CI_BUILD is not s | surfaced | impacted | P1 | 68 (41) / 762 (189) | 13 | 82.4 |
| d42407e7d → 7797081f | Fix network_tests/someip_tp_tests | surfaced | root | P1 | 7 (3) / 16 (7) | 2 | 22.5 |
| e772e621e → 31b94d3e | fix send_queued error handling | surfaced | root | P1 | 61 (19) / 675 (260) | 21 | 43.6 |
| b40e1e894 → 7b0f0103 | Fix remote subscription expiration | surfaced | root | P1 | 23 (10) / 466 (136) | 13 | 89.5 |
