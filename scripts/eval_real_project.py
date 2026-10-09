#!/usr/bin/env python3
"""Real-project acceptance eval (spec 002 SC-201; constitution "recall tracking").

Clones google/leveldb at a pinned commit whose change is known (bb74ef7 "Add SetCapacity method to
leveldb::Cache"), configures it with the compile database + CMake File API, runs tcadvisor with every
available graph provider and checks ground-truth expectations derived from that commit.

  python3 scripts/eval_real_project.py [--workdir DIR] [--providers clang,codegraph,gitnexus] [--quiet]
Exit 0 when every expectation holds for every provider that ran; writes <workdir>/eval.json.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_URL = "https://github.com/google/leveldb.git"
COMMIT = "bb74ef739973a70ca9f0d90788a1da89b788c0ad"
MAX_CASES = 60  # noise guard: cycle-1 analyzer produced 271 cases for this commit


def sh(cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def setup(work: Path) -> tuple[Path, Path]:
    repo, build = work / "leveldb", work / "leveldb-build"
    if not (repo / ".git").exists():
        sh(["git", "clone", "-q", "--filter=blob:none", REPO_URL, str(repo)])
    sh(["git", "checkout", "-q", COMMIT], cwd=repo)
    if not (build / "compile_commands.json").exists():
        q = build / ".cmake" / "api" / "v1" / "query"
        q.mkdir(parents=True, exist_ok=True)
        (q / "codemodel-v2").touch()
        cxx = ["-DCMAKE_CXX_COMPILER=clang++"] if shutil.which("clang++") else []
        sh(["cmake", "-S", str(repo), "-B", str(build), "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
            "-DLEVELDB_BUILD_TESTS=OFF", "-DLEVELDB_BUILD_BENCHMARKS=OFF", *cxx])
    return repo, build


def expectations(r: dict, provider: str) -> dict[str, bool]:
    risks = {(s["symbol"]["qualified_name"], x["risk_group"], x["sub_reason"])
             for s in r["changed_symbols"] for x in s["risks"]}
    p1 = [c for c in r["test_case_candidates"] if c["priority"] == "P1"]
    e = {
        "cache_vtable_change_is_P1": any(c["evidence"][0]["qualified_name"] == "leveldb::Cache"
                                         and c["risk_group"] == "abi_layout" for c in p1),
        "setcapacity_lock_is_thread_safety": any(n.endswith("LRUCache::SetCapacity") and g == "thread_safety"
                                                 for n, g, _ in risks),
        "no_include_guard_build_config": not any(n == "leveldb::Cache" and g == "build_config" for n, g, _ in risks),
        f"case_count_below_{MAX_CASES}": len(r["test_case_candidates"]) < MAX_CASES,
    }
    if provider == "codegraph":
        e["finds_existing_test_CacheTest.SetCapacity"] = any(t["test"] == "CacheTest.SetCapacity"
                                                             for t in r.get("existing_tests", []))
        e["sharded_cache_reached_via_inheritance"] = any(
            n["symbol"]["qualified_name"].endswith("ShardedLRUCache") and n["hop_distance"] >= 1
            and any(ed["relation"] == "inherit_override" for ed in n["edges"]) for n in r["impact_nodes"])
    return e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, default=Path(os.environ.get("TCADVISOR_EVAL_DIR", "/tmp/tcadvisor-eval")))
    ap.add_argument("--providers", default="clang,codegraph,gitnexus")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    a.workdir.mkdir(parents=True, exist_ok=True)
    try:
        repo, build = setup(a.workdir)
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"SKIP: cannot prepare leveldb ({exc})")
        return 0
    results = {}
    for prov in a.providers.split(","):
        env_bin = os.environ.get(f"TCADVISOR_{prov.upper()}")
        if prov != "clang" and not (env_bin or shutil.which(prov)):
            results[prov] = {"skipped": f"{prov} not installed"}
            continue
        out = a.workdir / f"out-{prov}"
        t0 = time.monotonic()
        cmd = [sys.executable, "-m", "tcadvisor", "analyze", "--repo", str(repo), "--build-dir", str(build),
               "--commit-range", "HEAD~1..HEAD", "--output-dir", str(out), "--cache-dir", str(a.workdir / "cache"),
               "--graph", prov, "--no-run-cache", "-q"] + (["--graph-bin", env_bin] if env_bin else [])
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            results[prov] = {"error": res.stderr[-800:]}
            continue
        r = json.loads((out / "report.json").read_text())
        exp = expectations(r, prov)
        results[prov] = {"seconds": round(time.monotonic() - t0, 1), "cases": len(r["test_case_candidates"]),
                         "P1": sum(c["priority"] == "P1" for c in r["test_case_candidates"]),
                         "flags": len(r["uncertainty_flags"]), "impact_nodes": len(r["impact_nodes"]),
                         "existing_tests": [t["test"] for t in r.get("existing_tests", [])], "expectations": exp}
    (a.workdir / "eval.json").write_text(json.dumps(results, indent=1))
    failed = [f"{p}:{k}" for p, v in results.items() for k, ok in v.get("expectations", {}).items() if not ok]
    failed += [f"{p}:error" for p, v in results.items() if "error" in v]
    if not a.quiet:
        print(json.dumps(results, indent=1))
    ran = [p for p, v in results.items() if "expectations" in v]
    print(f"EVAL leveldb@{COMMIT[:7]}: providers run={','.join(ran) or '-'}; "
          + ("all expectations hold" if not failed else "FAILED " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
