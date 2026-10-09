#!/usr/bin/env python3
"""SC-005 regression pilot: would the advisor have pointed at the code a later bug fix had to change?

For every pair "introducing commit -> fixing commit" (one per line: `<intro> -> <fix> | subject`):
1. check out the introducing commit in a private git worktree, configure CMake (compile db + File API),
   sync the code graph, and run `tcadvisor analyze --commit-range <intro>^..<intro>`;
2. ground truth = the C++ functions changed by the fixing commit (test files excluded) that already
   existed at the introducing commit;
3. a regression is *surfaced* when one of those functions appears as a changed symbol, an impacted node, an
   existing test or an uncertainty flag; *file-level* when only its file appears; otherwise *missed*.

  python3 scripts/pilot_regressions.py --repo R --pairs pairs.txt --work DIR [--graph codegraph]
       [--cmake-args "-DWITH_TESTS=ON ..."] [--max-hop-depth 2]
Writes DIR/pilot.json and DIR/pilot.md. Never modifies the source clone (uses `git worktree`).
"""
import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

CPP = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl")
HUNK_FN = re.compile(r"^@@ [^@]+ @@\s*(.*)$")
NAME = re.compile(r"([A-Za-z_~][\w:~]*)\s*\(")


def sh(cmd, cwd=None, check=True, env=None):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True, env=env)


def is_test(path: str) -> bool:
    p = path.lower()
    return "test" in p.split("/")[-1] or "/test" in p or p.startswith("test")


def changed_functions(repo: Path, fix: str, attrs: Path) -> dict[str, set[str]]:
    """file -> short function names touched by the fix (from hunk headers and +/- lines with a signature)."""
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
                res.setdefault(cur, set()).add(n.group(1).split("::")[-1])
        elif line.startswith("@@"):
            res.setdefault(cur, set())
    return res


def short(name: str) -> str:
    return name.split("::")[-1]


def evaluate(report: dict, truth: dict[str, set[str]]) -> dict:
    """Where does the fixed code show up — and how prominently?

    via: root (the introducing commit changed that function itself — expected for SZZ pairs) or
    impacted (reached through the graph: the interesting case); best_priority / rank: position of the first
    case on that symbol in the priority-ordered list (what a reviewer working top-down would reach).
    """
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
    hits, file_hits, misses = [], [], []
    for file, fns in truth.items():
        for fn in sorted(fns) or ["<file>"]:
            if (file, fn) in hop:
                idx = next((i for i, c in enumerate(cases) if c["evidence"][0].get("file_path") == file
                            and short(c["evidence"][0].get("qualified_name", "")) == fn), None)
                hits.append({"symbol": f"{file}:{fn}", "hop": hop[(file, fn)],
                             "via": "root" if hop[(file, fn)] == 0 else "flag" if hop[(file, fn)] == 99 else "impacted",
                             "best_priority": cases[idx]["priority"] if idx is not None else None,
                             "rank": idx + 1 if idx is not None else None})
            elif file in seen_file:
                file_hits.append(f"{file}:{fn}")
            else:
                misses.append(f"{file}:{fn}")
    verdict = "surfaced" if hits else "file-level" if file_hits else "missed"
    best = min(hits, key=lambda h: (h["rank"] or 10**9)) if hits else None
    return {"verdict": verdict, "hits": hits, "file_hits": file_hits, "misses": misses,
            "via": best["via"] if best else None, "best_priority": best["best_priority"] if best else None,
            "rank": best["rank"] if best else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--graph", default="codegraph")
    ap.add_argument("--cmake-args", default="")
    ap.add_argument("--max-hop-depth", type=int, default=2)
    ap.add_argument("--rescore", action="store_true", help="recompute metrics from an earlier run's reports")
    a = ap.parse_args()
    if a.rescore:
        results = json.loads((a.work / "pilot.json").read_text())
        for row in results:
            rp = a.work / f"out-{row['intro']}" / "report.json"
            if row.get("truth") and rp.exists():
                truth = {t.split(":", 1)[0]: set(filter(None, t.split(":", 1)[1].split(","))) for t in row["truth"]}
                row.update(evaluate(json.loads(rp.read_text()), truth))
        return finish(a, results)
    a.work.mkdir(parents=True, exist_ok=True)
    attrs = a.work / "gitattributes"
    attrs.write_text("".join(f"*{e} diff=cpp\n" for e in CPP))
    wt, build = a.work / "wt", a.work / "wt-build"
    if not (wt / ".git").exists():
        sh(["git", "worktree", "add", "--detach", str(wt), "HEAD"], cwd=a.repo)
    (build / ".cmake/api/v1/query").mkdir(parents=True, exist_ok=True)
    (build / ".cmake/api/v1/query/codemodel-v2").touch()
    results = []
    for raw in a.pairs.read_text().splitlines():
        m = re.match(r"^\s*([0-9a-f]+)\s*->\s*([0-9a-f]+)\s*\|?\s*(.*)$", raw)
        if not m:
            continue
        intro, fix, subject = m.groups()
        row = {"intro": intro, "fix": fix, "subject": subject}
        truth = changed_functions(a.repo, fix, attrs)
        if not truth:
            row["verdict"] = "no-source-truth"
            results.append(row)
            print(f"{intro}->{fix}: skipped (fix touches no non-test C++ source)", file=sys.stderr)
            continue
        try:
            sh(["git", "checkout", "-q", "--detach", "-f", intro], cwd=wt)
            # ground truth must exist at the introducing commit (a fix may add brand-new helpers)
            truth = {f: {fn for fn in fns if (wt / f).exists() and re.search(rf"\b{re.escape(fn)}\b", (wt / f).read_text(
                errors="replace"))} for f, fns in truth.items() if (wt / f).exists()}
            truth = {f: fns for f, fns in truth.items()}
            if not truth:
                row["verdict"] = "no-source-truth"
                results.append(row)
                continue
            t0 = time.monotonic()
            sh(["cmake", "-S", str(wt), "-B", str(build), "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
                *shlex.split(a.cmake_args)])
            out = a.work / f"out-{intro}"
            cmd = [sys.executable, "-m", "tcadvisor", "analyze", "--repo", str(wt), "--build-dir", str(build),
                   "--commit-range", f"{intro}^..{intro}", "--output-dir", str(out), "--cache-dir",
                   str(a.work / "cache"), "--graph", a.graph, "--no-run-cache", "--allow-stale-compile-db",
                   "--max-hop-depth", str(a.max_hop_depth), "-q"]
            res = sh(cmd, check=False)
            row["seconds"] = round(time.monotonic() - t0, 1)
            if res.returncode != 0:
                row["verdict"] = "error"
                row["error"] = res.stderr[-600:]
            else:
                rep = json.loads((out / "report.json").read_text())
                row.update(evaluate(rep, truth))
                row.update(cases=len(rep["test_case_candidates"]),
                           p1=sum(c["priority"] == "P1" for c in rep["test_case_candidates"]),
                           flags=len(rep["uncertainty_flags"]), nodes=len(rep["impact_nodes"]),
                           changed=len(rep.get("changed_symbols", [])), truth=sorted(f"{f}:{','.join(sorted(v))}"
                                                                                    for f, v in truth.items()))
        except subprocess.CalledProcessError as exc:
            row["verdict"] = "error"
            row["error"] = (exc.stderr or str(exc))[-600:]
        results.append(row)
        print(f"{intro}->{fix}: {row['verdict']} via {row.get('via')} rank {row.get('rank')} "
          f"({row.get('seconds', '-')}s, {row.get('cases', '-')} cases)",
              file=sys.stderr)
    return finish(a, results)


def finish(a, results) -> int:
    (a.work / "pilot.json").write_text(json.dumps(results, indent=1))
    scored = [r for r in results if r["verdict"] in ("surfaced", "file-level", "missed")]
    md = ["| intro → fix | subject | verdict | via | best case | rank / cases (P1) | flags | s |",
          "|---|---|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['intro']} → {r['fix']} | {r['subject'][:60]} | {r['verdict']} | {r.get('via') or '-'} | "
                  f"{r.get('best_priority') or '-'} | {r.get('rank') or '-'} / {r.get('cases', '-')} ({r.get('p1', '-')}) | "
                  f"{r.get('flags', '-')} | {r.get('seconds', '-')} |")
    n = len(scored)
    surf = sum(r["verdict"] == "surfaced" for r in scored)
    filel = sum(r["verdict"] == "file-level" for r in scored)
    summary = (f"SC-005 pilot ({a.graph}): {n} scored regressions — surfaced {surf}, file-level only {filel}, "
               f"missed {n - surf - filel}; missed-case rate {((n - surf) / n * 100 if n else 0):.0f}% "
               f"(symbol level), {((n - surf - filel) / n * 100 if n else 0):.0f}% (file level)")
    in_top = sum(1 for r in scored if r.get("rank") and r["rank"] <= 20)
    impacted = sum(1 for r in scored if r.get("via") == "impacted")
    summary += (f"; fixed code in the first 20 cases for {in_top}/{n}; reached only through the graph (not a "
                f"changed symbol) for {impacted}/{n}")
    (a.work / "pilot.md").write_text(summary + "\n\n" + "\n".join(md) + "\n")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
