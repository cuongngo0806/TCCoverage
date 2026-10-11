#!/usr/bin/env python3
"""Seeded side-effect regressions on google/leveldb (spec 007, SC-701..SC-704).

Each scenario applies one small, realistic edit to a pinned leveldb checkout (the kind of change that "fixes one
place and breaks another"), runs ``tcadvisor analyze --working-tree`` and scores the report against a ground truth
written down *before* the tool was improved:

  victim    functions that really break (or must be re-tested) because of the edit — never the edited function
            itself unless the edit only hurts its own callers through its result
  corner    a regex for the concrete corner case that exposes the bug (e.g. ``left == right``, a null snapshot)
  noise     cases ranked before the first victim (lower is better)

  python3 scripts/seeded_regressions.py [--workdir DIR] [--only NAME,...] [--json OUT] [--quiet]
Exit 0 when every victim is named and every corner is hinted on the edited symbol or a victim case.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_real_project import setup  # noqa: E402  (clone + configure leveldb, pinned commit)

# name, file, old text, new text, victims (qualified-name suffixes), corner regex (case-insensitive)
SCENARIOS = [
    ("findfile_loop_bound", "db/version_set.cc",
     "  while (left < right) {\n    uint32_t mid = (left + right) / 2;",
     "  while (left <= right) {\n    uint32_t mid = (left + right) / 2;",
     ["SomeFileOverlapsRange", "LevelFileNumIterator::Seek", "Version::ForEachOverlapping"],
     r"left == right|empty|size\(\)|past the (last|end)"),
    ("varint_limit_guard", "util/coding.h",
     "  if (p < limit) {\n    uint32_t result",
     "  if (p <= limit) {\n    uint32_t result",
     ["GetVarint32", "GetLengthPrefixedSlice", "DecodeEntry"],
     r"p == limit|empty|end of the (buffer|input)|zero-length"),
    ("cache_unref_order", "util/cache.cc",
     "    (*e->deleter)(e->key(), e->value);\n    free(e);",
     "    free(e);\n    (*e->deleter)(e->key(), e->value);",
     ["LRUCache::Release", "LRUCache::FinishErase", "LRUCache::~LRUCache"],
     r"after (it was |being )?(free|delet|releas)|use[- ]after|order"),
    ("blockhandle_error_swallowed", "table/format.cc",
     '    return Status::Corruption("bad block handle");',
     "    return Status::OK();",
     ["Footer::DecodeFrom", "Table::Open", "Table::BlockReader", "Table::ReadMeta"],
     r"corrupt|malformed|invalid|truncat|error (result|value|status)"),
    ("compaction_flag_not_set", "db/db_impl.cc",
     "    background_compaction_scheduled_ = true;\n",
     "",
     ["DBImpl::BackgroundCall", "DBImpl::~DBImpl", "DBImpl::BackgroundCompaction"],
     r"background_compaction_scheduled_"),
    ("memtable_encoded_len", "db/memtable.cc",
     "internal_key_size + VarintLength(val_size) +",
     "internal_key_size +",
     ["MemTable::Get", "MemTableIterator::value", "GetLengthPrefixedSlice"],
     r"round trip|decod|read back|empty value|val_size"),
    ("writebatch_count_dropped", "db/write_batch.cc",
     "void WriteBatch::Put(const Slice& key, const Slice& value) {\n"
     "  WriteBatchInternal::SetCount(this, WriteBatchInternal::Count(this) + 1);\n",
     "void WriteBatch::Put(const Slice& key, const Slice& value) {\n",
     ["WriteBatch::Iterate", "WriteBatchInternal::InsertInto", "DBImpl::Write", "WriteBatchInternal::Count"],
     r"SetCount|Count\b|no longer"),
    ("slice_prefix_equal_len", "include/leveldb/slice.h",
     "return ((size_ >= x.size_) &&",
     "return ((size_ > x.size_) &&",
     ["DBImpl::GetProperty", "PosixEnv", "ParseFileName", "starts_with"],
     r"size_ == x\.size_|equal (length|size)|same (length|size)"),
    ("get_null_snapshot", "db/db_impl.cc",
     "  if (options.snapshot != nullptr) {\n    snapshot =\n"
     "        static_cast<const SnapshotImpl*>(options.snapshot)->sequence_number();\n  } else {",
     "  {\n    snapshot =\n"
     "        static_cast<const SnapshotImpl*>(options.snapshot)->sequence_number();\n  }\n  {",
     ["DBImpl::Get", "DB::Get", "leveldb_get"],
     r"null|snapshot == nullptr|without a snapshot"),
    ("valuetype_new_enumerator", "db/dbformat.h",
     "enum ValueType { kTypeDeletion = 0x0, kTypeValue = 0x1 };",
     "enum ValueType { kTypeDeletion = 0x0, kTypeValue = 0x1, kTypeMerge = 0x2 };",
     ["MemTable::Get", "DBIter::FindNextUserEntry", "DBIter::FindPrevUserEntry", "WriteBatch::Iterate"],
     r"kTypeMerge"),
    ("write_buffer_default", "include/leveldb/options.h",
     "  size_t write_buffer_size = 4 * 1024 * 1024;",
     "  size_t write_buffer_size = 64 * 1024;",
     ["SanitizeOptions", "DBImpl::MakeRoomForWrite", "BuildBatchGroup"],
     r"write_buffer_size"),
    ("snapshot_lock_removed", "db/db_impl.cc",
     "const Snapshot* DBImpl::GetSnapshot() {\n  MutexLock l(&mutex_);\n",
     "const Snapshot* DBImpl::GetSnapshot() {\n",
     ["DBImpl::ReleaseSnapshot", "DBImpl::DoCompactionWork", "SnapshotList"],
     r"concurren|thread|race"),
]


def run(repo: Path, build: Path, out: Path) -> tuple[dict, float]:
    t = time.time()
    subprocess.run([sys.executable, "-m", "tcadvisor", "analyze", "--repo", str(repo), "--build-dir", str(build),
                    "--working-tree", "--output-dir", str(out), "--format", "json", "--no-run-cache", "-q"],
                   check=True, capture_output=True, text=True)
    return json.loads((out / "report.json").read_text()), time.time() - t


def score(r: dict, victims: list[str], corner: str) -> dict:
    cases = r["test_case_candidates"]
    roots = {s["symbol"]["qualified_name"] for s in r["changed_symbols"]}

    def is_victim(name: str) -> bool:
        return any(name.endswith(v) or name.endswith("::" + v) or v in name.split("::") for v in victims)

    rank = next((i for i, c in enumerate(cases, 1) if is_victim(c["evidence"][0]["qualified_name"])), None)
    named = sorted({c["evidence"][0]["qualified_name"] for c in cases if is_victim(c["evidence"][0]["qualified_name"])})
    rx = re.compile(corner, re.I)
    corner_hit = any(rx.search(h) for c in cases
                     if c["evidence"][0]["qualified_name"] in roots or is_victim(c["evidence"][0]["qualified_name"])
                     for h in c.get("corner_cases", []) + [c["description"]])
    return {"cases": len(cases), "victim_rank": rank, "victims_named": len(named), "victims_total": len(victims),
            "corner_hit": corner_hit, "noise_before_victim": (rank - 1) if rank else len(cases),
            "p1": sum(c["priority"] == "P1" for c in cases)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, default=Path("/tmp/tcadvisor-eval"))
    ap.add_argument("--only", help="comma-separated scenario names")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    a.workdir.mkdir(parents=True, exist_ok=True)
    repo, build = setup(a.workdir)
    only = set(a.only.split(",")) if a.only else None
    rows, ok = [], True
    for name, rel, old, new, victims, corner in SCENARIOS:
        if only and name not in only:
            continue
        subprocess.run(["git", "checkout", "-q", "."], cwd=repo, check=True)
        path = repo / rel
        text = path.read_text()
        if old not in text:
            print(f"SKIP {name}: edit site not found in {rel}", file=sys.stderr)
            ok = False
            continue
        path.write_text(text.replace(old, new, 1))
        try:
            r, secs = run(repo, build, a.workdir / "seeded" / name)
        finally:
            subprocess.run(["git", "checkout", "-q", "."], cwd=repo, check=True)
        s = score(r, victims, corner) | {"name": name, "seconds": round(secs, 1)}
        rows.append(s)
        ok &= bool(s["victim_rank"]) and s["corner_hit"]
        if not a.quiet:
            print(f"{name:28} cases={s['cases']:4} victim_rank={s['victim_rank']!s:>4} "
                  f"victims={s['victims_named']}/{s['victims_total']} corner={'yes' if s['corner_hit'] else 'NO '} "
                  f"P1={s['p1']:3} {s['seconds']}s")
    if rows:
        found = sum(bool(s["victim_rank"]) for s in rows)
        mrr = sum(1 / s["victim_rank"] for s in rows if s["victim_rank"]) / len(rows)
        corners = sum(s["corner_hit"] for s in rows)
        med_cases = sorted(s["cases"] for s in rows)[len(rows) // 2]
        print(f"SEEDED leveldb: victims named {found}/{len(rows)}; corner hinted {corners}/{len(rows)}; "
              f"victim MRR {mrr:.3f}; median cases {med_cases}")
        if a.json:
            a.json.write_text(json.dumps({"rows": rows, "victims_found": found, "corner_hits": corners,
                                          "mrr": round(mrr, 3), "median_cases": med_cases}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
