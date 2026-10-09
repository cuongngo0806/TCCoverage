| split | scored | surfaced | file-level | missed | via graph | top10 | top20 | top50 | MRR | median rank | median cases | median s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 16 | 15 | 1 | 0 | 2 | 10 | 10 | 12 | 0.496 | 2.0 | 324.5 | 55.1 |
| dev | 9 | 8 | 1 | 0 | 1 | 5 | 5 | 6 | 0.506 | 2 | 125 | 36.6 |
| holdout | 7 | 7 | 0 | 0 | 1 | 5 | 5 | 6 | 0.482 | 2 | 599 | 67.0 |

| intro → fix | subject | verdict | via | best | rank (symbol rank) / cases (P1) | flags | s |
|---|---|---|---|---|---|---|---|
| 062396af1 → 55d58d91e | Fix use of crc32c 3way on portable builds using MSVC (# | file-level | - | - | - (-) / 125 (0) | 3 | 3.2 |
| 1e5b631e5 → bbc85a5f2 | Fix minor wrong variable name in db_bench (#8549) | no-source-truth | - | - | - (-) / - (-) | - | - |
| 2acbf386a → f6c4d7a57 | Fix hang in MultiRead with O_DIRECT and io_uring (#1036 | surfaced | root | P2 | 2 (2) / 328 (24) | 57 | 61.0 |
| 3b5cb114e → fc85a700c | Fix memory accounting leak in IODispatcher ReadIndex()  | surfaced | impacted | P1 | 295 (90) / 780 (168) | 26 | 120.2 |
| 4026c3cc0 → 43d60bfe9 | Revert reverse-comparator handling in range tree lock m | surfaced | root | P2 | 1 (1) / 40 (6) | 19 | 36.6 |
| 408e8d4c8 → 112bf15dc | Fix false-positive TestBackupRestore corruption (#12917 | surfaced | root | P2 | 2 (2) / 1201 (9) | 45 | 49.2 |
| 656b734a5 → 359d57be9 | Fix blob file path misidentification in SstFileManager  | surfaced | impacted | P1 | 951 (295) / 2737 (798) | 32 | 217.6 |
| 749b849a3 → 013305af1 | Fix potential memory leak in ArenaWrappedDBIter::Refres | surfaced | root | P1 | 1 (1) / 321 (63) | 2 | 73.7 |
| 7c9b58068 → 0c533e61b | Fix XPRESS compression and enable in CI (#13649) | surfaced | root | P2 | 116 (45) / 2656 (711) | 95 | 342.9 |
| 7d83b4e3e → abd6751ab | Fix wrong padded bytes being used to generate file chec | surfaced | root | P2 | 1 (1) / 21 (0) | 1 | 19.5 |
| 8234d67e5 → 1e1c19931 | Fix dbstress run - attempt 1 (#13408) | surfaced | root | P2 | 23 (11) / 4309 (75) | 27 | 64.1 |
| 8f763bdea → 3093d98c7 | Fix higher read qps during db open caused by pr 11406 ( | surfaced | root | P1 | 2 (2) / 1512 (162) | 23 | 249.2 |
| 94d91dadd → 9577b92b5 | Fix ODR violation from open source folly build, update  | no-source-truth | - | - | - (-) / - (-) | - | - |
| a27fce408 → 40adb2bab | Fix wraparound in SstFileManager (#13010) | no-source-truth | - | - | - (-) / - (-) | - | - |
| b0ecf86f6 → 43d60bfe9 | Revert reverse-comparator handling in range tree lock m | surfaced | root | P2 | 1 (1) / 7 (0) | 8 | 28.2 |
| b1ee19140 → 3f7e92986 | Fix a race in ColumnFamilyData::UnrefAndTryDelete (#860 | surfaced | root | P1 | 3 (2) / 253 (41) | 0 | 22.0 |
| b397dcd39 → 2297769b3 | Fix regression issue of too large score (#10518) | surfaced | root | P2 | 1 (1) / 106 (0) | 0 | 21.8 |
| c2029f971 → 3f7e92986 | Fix a race in ColumnFamilyData::UnrefAndTryDelete (#860 | surfaced | root | P1 | 26 (10) / 599 (95) | 7 | 67.0 |
| d61a44936 → 8765a0f54 | Fix version edit dump in json (#12703) | no-source-truth | - | - | - (-) / - (-) | - | - |
| e1b176d27 → b57155a0b | Revert "Add CompressedSecondaryCache into stress test"  | no-source-truth | - | - | - (-) / - (-) | - | - |
| f07c56928 → 7cd576327 | Fix a copy-paste bug related to background threads in d | surfaced | root | P1 | 1 (1) / 43 (2) | 2 | 2.5 |
