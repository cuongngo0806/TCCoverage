#!/usr/bin/env python3
"""SC-005 regression pilot: would the advisor have pointed at the code a later bug fix had to change?

For every pair "introducing commit -> fixing commit" (one per line: `<intro> -> <fix> | subject`):
1. *prepare* (once, cached): a private git worktree at the introducing commit, a CMake build dir
   (compile db + File API) and a code-graph index;
2. *analyse*: `tcadvisor analyze --commit-range <intro>^..<intro>`;
3. ground truth = the C++ functions changed by the fixing commit (test files excluded) that already existed
   at the introducing commit. A regression is *surfaced* when one of them appears as a changed symbol,
   impacted node or uncertainty flag; *file-level* when only its file does; *missed* otherwise. The rank of
   the first case on that function measures how far down a reviewer has to read.

  python3 scripts/pilot_regressions.py --repo R --pairs pairs.txt --work DIR [--graph codegraph]
       [--cmake-args "..."] [--jobs 2] [--prepare-only] [--rescore]
Writes DIR/pilot.json, DIR/pilot.md and DIR/summary.json (all / dev = even rows / holdout = odd rows).
Never modifies the source clone (uses `git worktree`).
"""
import argparse
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CPP = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl")
HUNK_FN = re.compile(r"^@@ [^@]+ @@\s*(.*)$")
NAME = re.compile(r"([A-Za-z_~][\w:~]*)\s*\(")
ENV = dict(os.environ, CODEGRAPH_TELEMETRY="0")


def sh(cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True, env=ENV)


def is_test(path: str) -> bool:
    return "test" in path.lower()


def short(name: str) -> str:
    return name.split("::")[-1]


def changed_functions(repo: Path, fix: str, attrs: Path) -> dict[str, set[str]]:
    """file -> short function names touched by the fix (from git's C++ hunk headers)."""
    out = sh(["git", "-c", f"core.attributesFile={attrs}", "diff", "-U0", "--no-color", f"{fix}^", fix],
             cwd=repo).stdout
    res: dict[str, set[str]] = {}
    cur = None
    for line in out.splitlines():
        if line.startswith("+++ "):
            p = line[6:] if line.startswith("+++ b/") else None
            cur = p if p and p.endswith(CPP) and not is_test(p) else None
            continue
        if cur is None:
            continue
        m = HUNK_FN.match(line)
        if m and m.group(1):
            n = NAME.search(m.group(1))
            if n:
                res.setdefault(cur, set()).add(short(n.group(1)))
        elif line.startswith("@@"):
            res.setdefault(cur, set())
    return res


def evaluate(report: dict, truth: dict[str, set[str]]) -> dict:
    """via: root (changed by the introducing commit itself — expected for SZZ pairs) / impacted (reached
    through the graph) / flag; rank: position of the first case on that symbol; symbol_rank: number of
    distinct symbols a reviewer reads before reaching it."""
    hop: dict[tuple[str, str], int] = {}
    seen_file: set[str] = set()

    def add(sym, h):
        if sym:
            k = (sym["file_path"], short(sym["qualified_name"]))
            hop[k] = min(h, hop.get(k, h))
            seen_file.add(sym["file_path"])
    for s in report.get("changed_symbols", []):
        add(s["symbol"], 0)
    for n in report.get("impact_nodes", []):
        add(n["symbol"], n["hop_distance"])
    for f in report.get("uncertainty_flags", []):
        add(f.get("related_symbol"), 99)
    for t in report.get("existing_tests", []):
        seen_file.add(t["file_path"])
    cases = report.get("test_case_candidates", [])
    order: list[tuple[str, str]] = []
    first_case: dict[tuple[str, str], int] = {}
    for i, c in enumerate(cases):
        ev = c["evidence"][0]
        k = (ev.get("file_path"), short(ev.get("qualified_name", "")))
        if k not in first_case:
            first_case[k] = i
            order.append(k)
    sym_rank = {k: i for i, k in enumerate(order)}
    hits, file_hits, misses = [], [], []
    for file, fns in truth.items():
        for fn in sorted(fns) or ["<file>"]:
            k = (file, fn)
            if k in hop:
                hits.append({"symbol": f"{file}:{fn}", "hop": hop[k],
                             "via": "root" if hop[k] == 0 else "flag" if hop[k] == 99 else "impacted",
                             "best_priority": cases[first_case[k]]["priority"] if k in first_case else None,
                             "rank": first_case[k] + 1 if k in first_case else None,
                             "symbol_rank": sym_rank[k] + 1 if k in sym_rank else None})
            elif file in seen_file:
                file_hits.append(f"{file}:{fn}")
            else:
                misses.append(f"{file}:{fn}")
    verdict = "surfaced" if hits else "file-level" if file_hits else "missed"
    best = min(hits, key=lambda h: (h["rank"] or 10**9)) if hits else None
    return {"verdict": verdict, "hits": hits, "file_hits": file_hits, "misses": misses,
            "via": best["via"] if best else None, "best_priority": best["best_priority"] if best else None,
            "rank": best["rank"] if best else None, "symbol_rank": best["symbol_rank"] if best else None}


def parse_pairs(path: Path) -> list[dict]:
    out = []
    for raw in path.read_text().splitlines():
        m = re.match(r"^\s*([0-9a-f]+)\s*->\s*([0-9a-f]+)\s*\|?\s*(.*)$", raw)
        if m:
            out.append({"intro": m.group(1), "fix": m.group(2), "subject": m.group(3)})
    return out


def prepare(a, pair: dict, attrs: Path) -> dict:
    """Worktree + build dir + graph index for one introducing commit (cached by a marker file)."""
    intro = pair["intro"]
    wt, build = a.work / f"wt-{intro}", a.work / f"build-{intro}"
    marker = a.work / f"prepared-{intro}-{pair['fix']}.json"
    if marker.exists():
        return json.loads(marker.read_text())
    truth = changed_functions(a.repo, pair["fix"], attrs)
    info = {"truth": {}, "wt": str(wt), "build": str(build)}
    if truth:
        if not (wt / ".git").exists():
            sh(["git", "worktree", "add", "-f", "--detach", str(wt), intro], cwd=a.repo)
        truth = {f: {fn for fn in fns if re.search(rf"\b{re.escape(fn)}\b", (wt / f).read_text(errors="replace"))}
                 for f, fns in truth.items() if (wt / f).exists()}
        info["truth"] = {f: sorted(v) for f, v in truth.items()}
        if truth:
            (build / ".cmake/api/v1/query").mkdir(parents=True, exist_ok=True)
            (build / ".cmake/api/v1/query/codemodel-v2").touch()
            sh(["cmake", "-S", str(wt), "-B", str(build), "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                *shlex.split(a.cmake_args)])
            if a.graph == "codegraph" and not (wt / ".codegraph").exists():
                sh(["codegraph", "init", "-y", "."], cwd=wt)
    marker.write_text(json.dumps(info))
    return info


def analyse(a, pair: dict, info: dict) -> dict:
    row = dict(pair)
    truth = {f: set(v) for f, v in info["truth"].items()}
    row["truth"] = sorted(f"{f}:{','.join(sorted(v))}" for f, v in truth.items())
    if not truth:
        row["verdict"] = "no-source-truth"
        return row
    out = a.work / f"out-{pair['intro']}"
    t0 = time.monotonic()
    cmd = [sys.executable, "-m", "tcadvisor", "analyze", "--repo", info["wt"], "--build-dir", info["build"],
           "--commit-range", f"{pair['intro']}^..{pair['intro']}", "--output-dir", str(out), "--cache-dir",
           str(a.work / f"cache-{pair['intro']}"), "--graph", a.graph, "--no-run-cache",
           "--allow-stale-compile-db", "--max-hop-depth", str(a.max_hop_depth), "--jobs", "1", "-q"]
    res = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    row["seconds"] = round(time.monotonic() - t0, 1)
    if res.returncode != 0:
        row["verdict"] = "error"
        row["error"] = res.stderr[-600:]
        return row
    rep = json.loads((out / "report.json").read_text())
    row.update(evaluate(rep, truth))
    row.update(cases=len(rep["test_case_candidates"]),
               p1=sum(c["priority"] == "P1" for c in rep["test_case_candidates"]),
               flags=len(rep["uncertainty_flags"]), nodes=len(rep["impact_nodes"]),
               changed=len(rep.get("changed_symbols", [])))
    return row


def summarise(results: list[dict], label: str) -> dict:
    scored = [r for r in results if r.get("verdict") in ("surfaced", "file-level", "missed")]
    n = len(scored)
    ranks = [r["rank"] if r.get("rank") else 10**4 for r in scored]
    srank = [r["symbol_rank"] if r.get("symbol_rank") else 10**4 for r in scored]
    return {"label": label, "scored": n,
            "surfaced": sum(r["verdict"] == "surfaced" for r in scored),
            "file_level": sum(r["verdict"] == "file-level" for r in scored),
            "missed": sum(r["verdict"] == "missed" for r in scored),
            "via_graph": sum(r.get("via") == "impacted" for r in scored),
            "top10": sum(x <= 10 for x in ranks), "top20": sum(x <= 20 for x in ranks),
            "top50": sum(x <= 50 for x in ranks),
            "sym_top10": sum(x <= 10 for x in srank),
            "mrr": round(sum(1 / x for x in ranks) / n, 3) if n else 0,
            "median_rank": statistics.median(ranks) if n else None,
            "median_cases": statistics.median([r["cases"] for r in scored if "cases" in r]) if n else None,
            "median_seconds": statistics.median([r["seconds"] for r in scored if "seconds" in r]) if n else None,
            "errors": sum(r.get("verdict") == "error" for r in results)}


def finish(a, results: list[dict]) -> int:
    (a.work / "pilot.json").write_text(json.dumps(results, indent=1))
    dev = [r for i, r in enumerate(results) if i % 2 == 0]
    hold = [r for i, r in enumerate(results) if i % 2 == 1]
    sums = [summarise(results, "all"), summarise(dev, "dev"), summarise(hold, "holdout")]
    md = ["| split | scored | surfaced | file-level | missed | via graph | top10 | top20 | top50 | MRR | median rank "
          "| median cases | median s |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sums:
        md.append(f"| {s['label']} | {s['scored']} | {s['surfaced']} | {s['file_level']} | {s['missed']} | "
                  f"{s['via_graph']} | {s['top10']} | {s['top20']} | {s['top50']} | {s['mrr']} | {s['median_rank']} | "
                  f"{s['median_cases']} | {s['median_seconds']} |")
    md += ["", "| intro → fix | subject | verdict | via | best | rank (symbol rank) / cases (P1) | flags | s |",
           "|---|---|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['intro']} → {r['fix']} | {r['subject'][:55]} | {r.get('verdict')} | {r.get('via') or '-'} | "
                  f"{r.get('best_priority') or '-'} | {r.get('rank') or '-'} ({r.get('symbol_rank') or '-'}) / "
                  f"{r.get('cases', '-')} ({r.get('p1', '-')}) | {r.get('flags', '-')} | {r.get('seconds', '-')} |")
    (a.work / "pilot.md").write_text("\n".join(md) + "\n")
    (a.work / "summary.json").write_text(json.dumps(sums, indent=1))
    for s in sums:
        print(json.dumps(s))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--graph", default="codegraph")
    ap.add_argument("--cmake-args", default="")
    ap.add_argument("--max-hop-depth", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--rescore", action="store_true", help="recompute metrics from the last run's reports")
    a = ap.parse_args()
    a.work = a.work.resolve()
    a.work.mkdir(parents=True, exist_ok=True)
    attrs = a.work / "gitattributes"
    attrs.write_text("".join(f"*{e} diff=cpp\n" for e in CPP))
    pairs = parse_pairs(a.pairs)
    if a.rescore:
        results = json.loads((a.work / "pilot.json").read_text())
        for row in results:
            rp = a.work / f"out-{row['intro']}" / "report.json"
            if row.get("truth") and rp.exists() and row.get("verdict") != "error":
                truth = {t.split(":", 1)[0]: set(filter(None, t.split(":", 1)[1].split(","))) for t in row["truth"]}
                row.update(evaluate(json.loads(rp.read_text()), truth))
        return finish(a, results)

    def prep(p):
        try:
            return prepare(a, p, attrs)
        except subprocess.CalledProcessError as exc:
            print(f"prepare {p['intro']} failed: {(exc.stderr or '')[-300:]}", file=sys.stderr)
            return {"truth": {}, "error": True}
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        infos = list(pool.map(prep, pairs))
    if a.prepare_only:
        print(f"prepared {sum(bool(i['truth']) for i in infos)}/{len(pairs)} pairs with source ground truth")
        return 0

    def run(pi):
        p, info = pi
        row = analyse(a, p, info)
        print(f"{p['intro']}->{p['fix']}: {row.get('verdict')} rank {row.get('rank')} "
              f"({row.get('seconds', '-')}s, {row.get('cases', '-')} cases)", file=sys.stderr)
        return row
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        results = list(pool.map(run, zip(pairs, infos)))
    return finish(a, results)


if __name__ == "__main__":
    raise SystemExit(main())
