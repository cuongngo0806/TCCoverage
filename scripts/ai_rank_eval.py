#!/usr/bin/env python3
"""Does AI verification help a reviewer reach the later-fixed function sooner?

For every pilot report in RUN_DIR(s): copy it, run `tcadvisor verify` on the first N cases (relevance order),
then compare the deterministic rank with an *AI-triaged view* (confirmed > needs_info > unverified > weak,
stable inside each class) and check whether the AI "additional checks" name the fixed function.
The deterministic list is never changed (constitution III); the view is an optional presentation.

  python3 scripts/ai_rank_eval.py OUT_DIR RUN_DIR [RUN_DIR ...] [--max-cases 40] [--jobs 3]
"""
import argparse
import json
import shutil
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ORDER = {"confirmed": 0, "needs_info": 1, None: 2, "weak": 3}


def short(q):
    return q.split("::")[-1]


def first_hit(cases, truth):
    for i, c in enumerate(cases):
        ev = c["evidence"][0]
        if (ev["file_path"], short(ev["qualified_name"])) in truth:
            return i + 1
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--max-cases", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for run in a.runs:
        for row in json.loads((run / "pilot.json").read_text()):
            rp = run / f"out-{row['intro']}" / "report.json"
            if row.get("verdict") in ("surfaced", "file-level", "missed") and rp.exists():
                truth = {(t.split(":", 1)[0], fn) for t in row["truth"] for fn in t.split(":", 1)[1].split(",") if fn}
                jobs.append((run.parent.parent.name, row, rp, truth))

    def one(job):
        proj, row, rp, truth = job
        d = a.out / f"{proj}-{row['intro']}"
        d.mkdir(parents=True, exist_ok=True)
        dst = d / "report.json"
        if not (d / "done").exists():
            shutil.copy(rp, dst)
            res = subprocess.run([sys.executable, "-m", "tcadvisor", "verify", str(dst), "--ai-external-approved",
                                  "--priorities", "P1,P2,P3", "--max-cases", str(a.max_cases)],
                                 capture_output=True, text=True)
            (d / "verify.log").write_text(res.stdout + res.stderr)
            if res.returncode == 0:
                (d / "done").touch()
        rep = json.loads(dst.read_text())
        cases = rep["test_case_candidates"]
        det = first_hit(cases, truth)
        view = sorted(cases, key=lambda c: ORDER.get((c.get("verification") or {}).get("verdict"), 2))
        ai = first_hit(view, truth)
        verdict = None
        if det:
            verdict = (cases[det - 1].get("verification") or {}).get("verdict")
        checks = (rep.get("ai_verification") or {}).get("additional_checks", [])
        named = any(fn in (ch.get("title", "") + " " + ch.get("why", "")) or
                    (ch.get("evidence", "").split(":")[0] == f and fn in ch.get("why", ""))
                    for f, fn in truth for ch in checks)
        usage = (rep.get("ai_verification") or {}).get("usage", {})
        return {"proj": proj, "intro": row["intro"], "det_rank": det, "ai_rank": ai, "hit_verdict": verdict,
                "named_in_checks": named, "cost": usage.get("cost_usd", 0), "calls": usage.get("calls", 0)}

    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        rows = list(pool.map(one, jobs))
    (a.out / "ai_rank.json").write_text(json.dumps(rows, indent=1))

    def summary(rs, k):
        vals = [r[k] or 10**4 for r in rs]
        return {"top10": sum(v <= 10 for v in vals), "top20": sum(v <= 20 for v in vals),
                "mrr": round(sum(1 / v for v in vals) / len(vals), 3), "median": statistics.median(vals)}
    in_window = [r for r in rows if r["det_rank"] and r["det_rank"] <= a.max_cases]
    print(json.dumps({
        "n": len(rows), "deterministic": summary(rows, "det_rank"), "ai_view": summary(rows, "ai_rank"),
        "hit_in_verified_window": len(in_window),
        "hit_verdicts": {v: sum(r["hit_verdict"] == v for r in in_window) for v in ("confirmed", "needs_info", "weak")},
        "fixed_function_named_in_ai_checks": sum(r["named_in_checks"] for r in rows),
        "total_cost_usd": round(sum(r["cost"] for r in rows), 2), "calls": sum(r["calls"] for r in rows)}, indent=1))


if __name__ == "__main__":
    main()
