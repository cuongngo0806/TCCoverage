#!/usr/bin/env python3
"""Seeded side-effect regressions on google/leveldb and jbeder/yaml-cpp (spec 007 SC-701..SC-704, spec 008).

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

# Holdout: written after the spec 007 implementation, never used to tune it (reported separately).
HOLDOUT = [
    ("arena_quarter_threshold", "util/arena.cc",
     "  if (bytes > kBlockSize / 4) {", "  if (bytes >= kBlockSize / 4) {",
     ["Arena::Allocate", "Arena::AllocateAligned"],
     r"bytes == kBlockSize"),
    ("cache_ref_conjunct_dropped", "util/cache.cc",
     "  if (e->refs == 1 && e->in_cache) {", "  if (e->refs == 1) {",
     ["LRUCache::Lookup", "LRUCache::Insert"],
     r"in_cache"),
    ("cache_usage_not_reduced", "util/cache.cc",
     "    usage_ -= e->charge;\n", "",
     ["LRUCache::Insert", "LRUCache::TotalCharge", "LRUCache::SetCapacity"],
     r"usage_"),
    ("footer_magic_check_removed", "table/format.cc",
     "  if (magic != kTableMagicNumber) {\n    return Status::Corruption(\"not an sstable (bad magic number)\");\n  }\n",
     "",
     ["Table::Open", "TableCache::FindTable"],
     r"magic|kTableMagicNumber|not an sstable"),
    ("arena_usage_term_dropped", "util/arena.cc",
     "memory_usage_.fetch_add(block_bytes + sizeof(char*),", "memory_usage_.fetch_add(block_bytes,",
     ["Arena::MemoryUsage", "MemTable::ApproximateMemoryUsage", "DBImpl::MakeRoomForWrite"],
     r"sizeof\(char\*\)|memory_usage_|MemoryUsage"),
    ("level_bytes_constant", "db/version_set.cc",
     "  double result = 10. * 1048576.0;", "  double result = 5. * 1048576.0;",
     ["VersionSet::Finalize"],
     r"\b10\b|\b5\b|1048576"),
    ("versionedit_tag_dropped", "db/version_edit.cc",
     "    PutVarint32(dst, kComparator);\n    PutLengthPrefixedSlice(dst, comparator_);",
     "    PutLengthPrefixedSlice(dst, comparator_);",
     ["VersionEdit::DecodeFrom", "VersionSet::Recover", "VersionSet::LogAndApply"],
     r"round trip|decod|kComparator|PutVarint32"),
    ("write_queue_conjunct_dropped", "db/db_impl.cc",
     "  while (!w.done && &w != writers_.front()) {", "  while (!w.done) {",
     ["DBImpl::Put", "DB::Put", "DBImpl::Delete", "DB::Delete"],
     r"writers_\.front\(\)|&w != writers_"),
    ("block_restart_offset", "table/block.cc",
     "restart_offset_ = size_ - (1 + NumRestarts()) * sizeof(uint32_t);",
     "restart_offset_ = size_ - NumRestarts() * sizeof(uint32_t);",
     ["Block::NewIterator", "Block::Iter"],
     r"restart_offset_|NumRestarts"),
    ("log_header_size", "db/log_format.h",
     "static const int kHeaderSize = 4 + 2 + 1;", "static const int kHeaderSize = 4 + 2 + 2;",
     ["Writer::EmitPhysicalRecord", "Writer::AddRecord", "Reader::ReadPhysicalRecord"],
     r"kHeaderSize"),
]

# Second project (spec 008): google-unrelated code base with `m_` members, accessors in headers and string
# literals full of braces. Written before the spec 008 implementation; scored as its own set.
YAML_URL = "https://github.com/jbeder/yaml-cpp.git"
YAML_COMMIT = "1e0876c"
YAMLCPP = [
    ("yaml_col_not_reset", "src/ostream_wrapper.cpp",
     "    m_row++;\n    m_col = 0;\n", "    m_row++;\n",
     ["Emitter::EmitBeginDoc", "Emitter::EmitEndDoc", "WriteComment"],
     r"m_col|newline|\\n"),
    ("yaml_anchor_flag_kept", "src/emitterstate.cpp",
     "  m_hasAnchor = false;\n  m_hasAlias = false;", "  m_hasAlias = false;",
     ["Emitter::EmitBeginDoc", "Emitter::EmitEndDoc", "EmitterState::EndedGroup"],
     r"m_hasAnchor"),
    ("yaml_indent_bound", "src/emitterstate.cpp",
     "  if (value <= 1)\n    return false;\n\n  _Set(m_indent", "  if (value < 1)\n    return false;\n\n  _Set(m_indent",
     ["Emitter::SetIndent", "EmitterState::StartedGroup"],
     r"value == 1"),
    ("yaml_null_empty_dropped", "src/null.cpp",
     "  return size == 0 || same(str, size, \"~\")", "  return same(str, size, \"~\")",
     ["IsValidPlainScalar", "SingleDocParser::HandleNode"],
     r"size == 0|empty"),
    ("yaml_size_guard_removed", "src/node_data.cpp",
     "  if (!m_isDefined)\n    return 0;\n\n  switch (m_type) {\n    case NodeType::Sequence:",
     "  switch (m_type) {\n    case NodeType::Sequence:",
     ["node_ref::size", "node::size", "Node::size"],
     r"m_isDefined"),
    ("yaml_mark_defined_flag", "src/node_data.cpp",
     "    m_type = NodeType::Null;\n  m_isDefined = true;\n}", "    m_type = NodeType::Null;\n}",
     ["node_data::compute_seq_size", "node_data::compute_map_size", "node_data::insert_map_pair", "node::is_defined"],
     r"m_isDefined"),
    ("yaml_last_indent_default", "src/emitterstate.cpp",
     "std::size_t lastIndent = (m_groups.empty() ? 0 : m_groups.back()->indent);",
     "std::size_t lastIndent = (m_groups.empty() ? 1 : m_groups.back()->indent);",
     ["Emitter::EmitEndSeq", "Emitter::EmitEndMap"],
     r"m_curIndent|empty|\b0, 1\b"),
    ("yaml_longkey_parity", "src/emitterstate.cpp",
     "    if (m_groups.back()->childCount % 2 == 0) {", "    if (m_groups.back()->childCount % 2 == 1) {",
     ["Emitter::FlowMapPrepareNode", "Emitter::BlockMapPrepareNode", "EmitterState::CurGroupLongKey"],
     r"childCount|% 2"),
    ("yaml_buffer_terminator", "src/ostream_wrapper.cpp",
     "    m_buffer.resize(std::max(m_buffer.size(), m_pos + str.size() + 1));",
     "    m_buffer.resize(std::max(m_buffer.size(), m_pos + str.size()));",
     ["ostream_wrapper::str", "Emitter::c_str"],
     r"m_buffer|\+ 1"),
]


def setup_yaml(work: Path) -> tuple[Path, Path]:
    repo, build = work / "yaml-cpp", work / "yaml-build"
    if not (repo / ".git").exists():
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", YAML_URL, str(repo)], check=True)
    subprocess.run(["git", "checkout", "-q", YAML_COMMIT], cwd=repo, check=True)
    if not (build / "compile_commands.json").exists():
        q = build / ".cmake" / "api" / "v1" / "query"
        q.mkdir(parents=True, exist_ok=True)
        (q / "codemodel-v2").touch()
        subprocess.run(["cmake", "-S", str(repo), "-B", str(build), "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                        "-DYAML_CPP_BUILD_TESTS=OFF", "-DYAML_CPP_BUILD_TOOLS=OFF", "-DCMAKE_CXX_COMPILER=clang++"],
                       check=True, capture_output=True)
    return repo, build


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
    names = {c["evidence"][0]["qualified_name"] for c in cases}
    named = [v for v in victims if any(n.endswith(v) or n.endswith("::" + v) or v in n.split("::") for n in names)]
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
    ap.add_argument("--set", choices=["dev", "holdout", "yamlcpp", "all"], default="all")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    a.workdir.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    rows, ok = [], True
    chosen = ([("dev", x) for x in SCENARIOS] if a.set in ("dev", "all") else []) + \
        ([("holdout", x) for x in HOLDOUT] if a.set in ("holdout", "all") else []) + \
        ([("yamlcpp", x) for x in YAMLCPP] if a.set in ("yamlcpp", "all") else [])
    chosen = [c for c in chosen if not only or c[1][0] in only]
    projects = {}
    if any(p != "yamlcpp" for p, _x in chosen):
        projects["leveldb"] = setup(a.workdir)
    if any(p == "yamlcpp" for p, _x in chosen):
        projects["yamlcpp"] = setup_yaml(a.workdir)
    for part, (name, rel, old, new, victims, corner) in chosen:
        repo, build = projects["yamlcpp" if part == "yamlcpp" else "leveldb"]
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
        s = score(r, victims, corner) | {"name": name, "set": part, "seconds": round(secs, 1)}
        rows.append(s)
        ok &= bool(s["victim_rank"]) and s["corner_hit"]
        if not a.quiet:
            print(f"{name:28} cases={s['cases']:4} victim_rank={s['victim_rank']!s:>4} "
                  f"victims={s['victims_named']}/{s['victims_total']} corner={'yes' if s['corner_hit'] else 'NO '} "
                  f"P1={s['p1']:3} {s['seconds']}s")
    summary = {}
    for part in ("dev", "holdout", "yamlcpp"):
        sub = [s for s in rows if s["set"] == part]
        if not sub:
            continue
        found = sum(bool(s["victim_rank"]) for s in sub)
        mrr = sum(1 / s["victim_rank"] for s in sub if s["victim_rank"]) / len(sub)
        corners = sum(s["corner_hit"] for s in sub)
        med_cases = sorted(s["cases"] for s in sub)[len(sub) // 2]
        summary[part] = {"victims_found": found, "corner_hits": corners, "n": len(sub), "mrr": round(mrr, 3),
                         "median_cases": med_cases}
        print(f"SEEDED {'yaml-cpp' if part == 'yamlcpp' else 'leveldb ' + part}: victims named {found}/{len(sub)}; corner hinted {corners}/{len(sub)}; "
              f"victim MRR {mrr:.3f}; median cases {med_cases}")
    if a.json and rows:
        a.json.write_text(json.dumps({"rows": rows, "summary": summary}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
