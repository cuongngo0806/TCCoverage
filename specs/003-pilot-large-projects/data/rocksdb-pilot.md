SC-005 pilot (codegraph): 9 scored regressions — surfaced 7, file-level only 2, missed 0; missed-case rate 22% (symbol level), 0% (file level); fixed code in the first 20 cases for 5/9; reached only through the graph (not a changed symbol) for 2/9

| intro → fix | subject | verdict | via | best case | rank / cases (P1) | flags | s |
|---|---|---|---|---|---|---|---|
| 3b5cb114e → fc85a700c | Fix memory accounting leak in IODispatcher ReadIndex() (#145 | surfaced | impacted | P1 | 127 / 726 (152) | 26 | 161.4 |
| 4026c3cc0 → 43d60bfe9 | Revert reverse-comparator handling in range tree lock manage | surfaced | root | P1 | 6 / 33 (6) | 19 | 116.1 |
| 408e8d4c8 → 112bf15dc | Fix false-positive TestBackupRestore corruption (#12917) | file-level | - | - | - / 1117 (17) | 21 | 134.7 |
| 656b734a5 → 359d57be9 | Fix blob file path misidentification in SstFileManager durin | file-level | - | - | - / 2673 (794) | 29 | 324.2 |
| 7c9b58068 → 0c533e61b | Fix XPRESS compression and enable in CI (#13649) | surfaced | root | P1 | 125 / 2547 (769) | 91 | 427.5 |
| 7d83b4e3e → abd6751ab | Fix wrong padded bytes being used to generate file checksum  | surfaced | root | P2 | 1 / 17 (0) | 1 | 104.4 |
| 8234d67e5 → 1e1c19931 | Fix dbstress run - attempt 1 (#13408) | surfaced | impacted | P1 | 15 / 4220 (78) | 8 | 141.9 |
| 8f763bdea → 3093d98c7 | Fix higher read qps during db open caused by pr 11406 (#1151 | surfaced | root | P1 | 20 / 1552 (211) | 23 | 341.4 |
| 94d91dadd → 9577b92b5 | Fix ODR violation from open source folly build, update (#140 | no-source-truth | - | - | - / - (-) | - | - |
| a27fce408 → 40adb2bab | Fix wraparound in SstFileManager (#13010) | no-source-truth | - | - | - / - (-) | - | - |
| b0ecf86f6 → 43d60bfe9 | Revert reverse-comparator handling in range tree lock manage | surfaced | root | P2 | 1 / 7 (0) | 8 | 158.2 |
| d61a44936 → 8765a0f54 | Fix version edit dump in json (#12703) | no-source-truth | - | - | - / - (-) | - | - |
