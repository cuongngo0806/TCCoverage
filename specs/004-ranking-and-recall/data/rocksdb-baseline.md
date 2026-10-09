| split | scored | surfaced | file-level | missed | via graph | top10 | top20 | top50 | MRR | median rank | median cases | median s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | 16 | 13 | 3 | 0 | 3 | 8 | 10 | 11 | 0.256 | 10.5 | 297.5 | 48.2 |
| dev | 9 | 6 | 3 | 0 | 1 | 4 | 4 | 5 | 0.258 | 40 | 119 | 39.7 |
| holdout | 7 | 7 | 0 | 0 | 2 | 4 | 6 | 6 | 0.254 | 7 | 587 | 71.8 |

| intro → fix | subject | verdict | via | best | rank (symbol rank) / cases (P1) | flags | s |
|---|---|---|---|---|---|---|---|
| 062396af1 → 55d58d91e | Fix use of crc32c 3way on portable builds using MSVC (# | file-level | - | - | - (-) / 119 (0) | 2 | 4.1 |
| 1e5b631e5 → bbc85a5f2 | Fix minor wrong variable name in db_bench (#8549) | no-source-truth | - | - | - (-) / - (-) | - | - |
| 2acbf386a → f6c4d7a57 | Fix hang in MultiRead with O_DIRECT and io_uring (#1036 | surfaced | root | P1 | 40 (16) / 317 (48) | 54 | 61.8 |
| 3b5cb114e → fc85a700c | Fix memory accounting leak in IODispatcher ReadIndex()  | surfaced | impacted | P1 | 127 (53) / 726 (152) | 26 | 129.2 |
| 4026c3cc0 → 43d60bfe9 | Revert reverse-comparator handling in range tree lock m | surfaced | root | P1 | 6 (4) / 33 (6) | 19 | 39.7 |
| 408e8d4c8 → 112bf15dc | Fix false-positive TestBackupRestore corruption (#12917 | surfaced | impacted | P1 | 6 (6) / 1117 (17) | 21 | 38.4 |
| 656b734a5 → 359d57be9 | Fix blob file path misidentification in SstFileManager  | file-level | - | - | - (-) / 2673 (794) | 29 | 227.7 |
| 749b849a3 → 013305af1 | Fix potential memory leak in ArenaWrappedDBIter::Refres | surfaced | root | P1 | 7 (5) / 278 (57) | 2 | 77.7 |
| 7c9b58068 → 0c533e61b | Fix XPRESS compression and enable in CI (#13649) | surfaced | root | P1 | 187 (53) / 2547 (769) | 91 | 357.3 |
| 7d83b4e3e → abd6751ab | Fix wrong padded bytes being used to generate file chec | surfaced | root | P2 | 1 (1) / 17 (0) | 1 | 18.0 |
| 8234d67e5 → 1e1c19931 | Fix dbstress run - attempt 1 (#13408) | surfaced | impacted | P1 | 8 (6) / 4220 (78) | 8 | 56.7 |
| 8f763bdea → 3093d98c7 | Fix higher read qps during db open caused by pr 11406 ( | surfaced | root | P1 | 20 (5) / 1552 (211) | 23 | 254.6 |
| 94d91dadd → 9577b92b5 | Fix ODR violation from open source folly build, update  | no-source-truth | - | - | - (-) / - (-) | - | - |
| a27fce408 → 40adb2bab | Fix wraparound in SstFileManager (#13010) | no-source-truth | - | - | - (-) / - (-) | - | - |
| b0ecf86f6 → 43d60bfe9 | Revert reverse-comparator handling in range tree lock m | surfaced | root | P2 | 1 (1) / 7 (0) | 8 | 28.5 |
| b1ee19140 → 3f7e92986 | Fix a race in ColumnFamilyData::UnrefAndTryDelete (#860 | surfaced | root | P1 | 3 (2) / 253 (41) | 0 | 23.0 |
| b397dcd39 → 2297769b3 | Fix regression issue of too large score (#10518) | surfaced | root | P2 | 1 (1) / 104 (0) | 0 | 28.0 |
| c2029f971 → 3f7e92986 | Fix a race in ColumnFamilyData::UnrefAndTryDelete (#860 | surfaced | root | P1 | 13 (7) / 587 (94) | 7 | 71.8 |
| d61a44936 → 8765a0f54 | Fix version edit dump in json (#12703) | no-source-truth | - | - | - (-) / - (-) | - | - |
| e1b176d27 → b57155a0b | Revert "Add CompressedSecondaryCache into stress test"  | no-source-truth | - | - | - (-) / - (-) | - | - |
| f07c56928 → 7cd576327 | Fix a copy-paste bug related to background threads in d | file-level | - | - | - (-) / 35 (1) | 2 | 3.0 |
