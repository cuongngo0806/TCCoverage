| split | scored | surfaced | file-level | missed | via graph | top10 | top20 | top50 | MRR | median rank | median cases | median s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 39 | 36 | 3 | 0 | 2 | 16 | 18 | 23 | 0.199 | 22 | 629 | 139.2 |
| dev | 19 | 16 | 3 | 0 | 1 | 6 | 7 | 10 | 0.133 | 48 | 655 | 158.0 |
| holdout | 20 | 20 | 0 | 0 | 1 | 10 | 11 | 13 | 0.262 | 12.0 | 570.0 | 114.35 |

| intro → fix | subject | verdict | via | best | rank (symbol rank) / cases (P1) | flags | s |
|---|---|---|---|---|---|---|---|
| d1e228130 → eec6f1ae | Fix duplicate registration warn to match major/minor | surfaced | root | P2 | 22 (9) / 108 (32) | 5 | 61.3 |
| 30f8553c9 → a4c3a42d | Fix queue_size not counting pending_trains | surfaced | root | P3 | 67 (51) / 1317 (15) | 62 | 275.6 |
| 30f8553c9 → bf9647cb | fix lock order inversion | surfaced | root | P3 | 69 (53) / 1317 (15) | 62 | 264.0 |
| 4062d4c97 → c631be64 | Fix network-tests using same ranges for client-ids | surfaced | root | P2 | 5 (3) / 69 (13) | 3 | 59.8 |
| 710a8613e → a9f20026 | fix SIGSEGV in add_remote_service_info | surfaced | root | P1 | 173 (85) / 2955 (595) | 875 | 535.4 |
| 7a30a430d → ff17ad40 | Fix integer overflow in `ASSIGN_CLIENT` payload deseria | surfaced | root | P2 | 4 (3) / 297 (52) | 7 | 139.2 |
| 38e9f99a1 → 723b4820 | fix daemon build | no-source-truth | - | - | - (-) / - (-) | - | - |
| 1a749b7e8 → 8b7e2502 | Fix Android build issues | surfaced | root | P2 | 3 (3) / 169 (22) | 15 | 64.5 |
| da754567d → af781c9e | Fix double connect | surfaced | root | P2 | 3 (3) / 55 (6) | 5 | 86.2 |
| 2a4f05aa2 → 23a8282d | Fix subscribe triggered by stale ON_AVAILABLE | surfaced | root | P1 | 60 (12) / 89 (47) | 4 | 40.4 |
| 8c97ab91b → bcc74a90 | Fix and test atomic stop offers | surfaced | root | P2 | 24 (22) / 655 (179) | 41 | 211.3 |
| 30f8553c9 → 70598bba | fix availability loop on `send_cbk` | surfaced | root | P2 | 267 (194) / 1317 (15) | 62 | 252.2 |
| 6ef7b4e12 → 4d9f4661 | fix 'Target replaced' warnings after STR | file-level | - | - | - (-) / 359 (81) | 24 | 223.9 |
| 91d3a2198 → 2a4f05aa | fix deliver_notification/register_event race | surfaced | root | P1 | 3 (3) / 888 (429) | 11 | 80.3 |
| 46bd8bf17 → 51faf636 | fix wrap around to VSOMEIP_SEC_PORT_UNSET on UDS | surfaced | root | P1 | 6 (3) / 629 (260) | 33 | 160.6 |
| 1695955b0 → 823a7640 | fix payload not being printed on android | surfaced | root | P2 | 1 (1) / 200 (59) | 39 | 70.5 |
| 9933ad2c1 → 1fd7314d | fix log to file | surfaced | root | P1 | 14 (6) / 339 (67) | 20 | 28.2 |
| 11447b294 → da754567 | Fix UDP connection availability loop | surfaced | root | P1 | 22 (12) / 1265 (412) | 65 | 325.6 |
| 269e98393 → d87c412c | Fix missing lock in udp_client_endpoint | surfaced | root | P1 | 79 (57) / 1508 (539) | 81 | 293.7 |
| cc8c5a943 → 67a94651 | Fix missing clean-up of pinged clients | surfaced | root | P2 | 49 (22) / 289 (110) | 10 | 88.6 |
| 7c3f82cde → 2f2f2dbc | fix drop of udp errors | surfaced | root | P2 | 2 (2) / 41 (0) | 1 | 22.2 |
| 46bd8bf17 → 30f3498e | Fix availability, host state, tcp address race in rmc | surfaced | root | P1 | 2 (2) / 629 (260) | 33 | 168.4 |
| 05f8f469b → 1bdf66fb | Fix logger include | file-level | - | - | - (-) / 454 (123) | 56 | 158.0 |
| 07b13fa64 → 1898c18b | Fix detached dispatcher thread | surfaced | root | P2 | 3 (2) / 18 (6) | 5 | 16.7 |
| 11447b294 → bd7eadf9 | fix routingmanagerd deadlock | surfaced | root | P2 | 48 (27) / 1265 (412) | 65 | 325.5 |
| 11447b294 → 04911817 | Fix selective event subscription race | surfaced | root | P2 | 14 (6) / 1265 (412) | 65 | 324.4 |
| 03f8ed529 → 7104c72e | fix logger_ext.hpp include path | file-level | - | - | - (-) / 1451 (8) | 2 | 366.0 |
| 30f8553c9 → dc21ddbe | fix test flakiness | surfaced | root | P3 | 154 (132) / 1317 (15) | 62 | 262.1 |
| 1e7a7b044 → da2bc0e4 | Fix get_connected_clients after rearch | surfaced | root | P1 | 143 (63) / 907 (334) | 35 | 237.1 |
| 1e7a7b044 → 3d262d8c | fix for a "never cleaned up" local_endpoint (routing) | surfaced | impacted | P1 | 437 (211) / 907 (334) | 35 | 233.9 |
| a5fb6b28f → 4cb092ca | fix missing find on resume | surfaced | root | P2 | 8 (8) / 50 (0) | 5 | 20.0 |
| 710a8613e → 3e3d9c64 | fix delayed availability | surfaced | root | P1 | 173 (85) / 2955 (595) | 875 | 532.6 |
| 200815b21 → 35732ef1 | Fix plugin_manager_impl singleton free-after-use on dto | surfaced | root | P1 | 6 (2) / 782 (196) | 13 | 77.8 |
| 7f40d9c53 → 17ee63e7 | fix logging prefix in flush function | surfaced | root | P1 | 1 (1) / 62 (19) | 7 | 84.8 |
| 60c83e0b4 → c69e067f | Fix double stop race condition | surfaced | root | P1 | 1 (1) / 23 (9) | 0 | 24.1 |
| b1e7bab5d → 88d868f8 | Fix availability inconsistency | surfaced | root | P1 | 126 (80) / 637 (237) | 73 | 192.7 |
| 200815b21 → da1fdec2 | Fix broken android build when ANDROID_CI_BUILD is not s | surfaced | impacted | P1 | 218 (76) / 782 (196) | 13 | 80.3 |
| d42407e7d → 7797081f | Fix network_tests/someip_tp_tests | surfaced | root | P2 | 10 (5) / 17 (2) | 2 | 20.5 |
| e772e621e → 31b94d3e | fix send_queued error handling | surfaced | root | P1 | 86 (22) / 711 (249) | 21 | 42.9 |
| b40e1e894 → 7b0f0103 | Fix remote subscription expiration | surfaced | root | P1 | 1 (1) / 511 (144) | 13 | 89.5 |
