# Results: spec 010

Seeded benchmark (`python3 scripts/seeded_regressions.py`), leveldb + yaml-cpp:

| Measure | yaml-cpp baseline | yaml-cpp now | leveldb dev (007 / now) | leveldb holdout (007 / now) |
|---|---|---|---|---|
| victim named | 6 / 9 | **8 / 9** | 12 / 12, 12 / 12 | 10 / 10, 10 / 10 |
| concrete corner hinted | 9 / 9 | 9 / 9 | 12 / 12, 12 / 12 | 10 / 10, 10 / 10 |
| victim MRR | 0.287 | **0.343** | 0.402, 0.402 | 0.347, 0.348 |

Gate: SC-801 passed (8 / 9 victims, corners 9 / 9, MRR 0.343 >= 0.287); SC-802 passed (no measure worse);
SC-803: full suite (152 passed, 3 skipped) and leveldb eval (`all expectations hold`) pass. Per-scenario times
are in the same range as spec 009 (about 2-8 s each).

CI thresholds (`.github/workflows/ci.yml`): dev 12 / 12, holdout 10 / 10, yaml-cpp victims >= 8 and corners >= 9.
Remaining miss: `yaml_mark_defined_flag` (victim not named).


## Verification after the workflow (main session)

Interleaved runs on the same container (baseline = a0517c6 source, same benchmark script):

| | baseline | after workflow | final |
|---|---|---|---|
| yaml-cpp victims / corners / MRR | 6/9, 9/9, 0.287 | 8/9, 9/9, 0.343 | **9/9, 9/9, 0.365** |
| leveldb dev | 12/12, 12/12, 0.402 | 12/12, 12/12, 0.402 | 12/12, 12/12, 0.397 |
| leveldb holdout | 10/10, 10/10, 0.347 | 10/10, 10/10, 0.348 | 10/10, 10/10, 0.348 |
| total seconds (31 scenarios) | 96.4 / 96.0 | 95.6 / 96.1 | ~100 |

Changes after the workflow (found by inspecting the remaining yaml-cpp miss; the yaml-cpp set therefore served as a
development set from here on):

- one-line definitions with statements (`bool ok() const { return m_ok; }`) were never function heads in the text
  scan, and `A(const A&) = delete;` left a pending head — both fixed;
- forwarding accessor chains (pimpl: `node::is_defined` → `node_ref::is_defined` → `node_data::is_defined`) are
  expanded up to 3 levels; a forwarder is a body that only returns the call;
- capped reader slots are filled by proximity (product code, then the changed file, then its directory);
- mutating calls on a member (`items_.push_back(...)`) are writers, not consumers; trivial accessors go after methods
  with logic in `class_consumer`, and accessor callers (other code) are not class consumers.

Dev MRR −0.005 comes from one scenario (`memtable_encoded_len`): the newly visible one-line reader
`MemTable::NewIterator` (it creates `MemTableIterator`, whose `value()` is in the ground truth) now ranks before
`MemTable::Get`. The ground truth was not changed after the fact.

CI threshold for yaml-cpp raised to victims ≥ 9. Full suite: 154 passed, 3 skipped; leveldb eval passes.
