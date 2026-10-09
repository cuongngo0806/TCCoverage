#!/usr/bin/env python3
"""Offline ranking lab: re-order the cases of existing pilot reports with candidate ranking functions and
measure where the later-fixed function lands — seconds instead of re-running the pilot.

  python3 scripts/rank_lab.py RUN_DIR [RUN_DIR ...]      (RUN_DIR = <work>/runs/<tag> with pilot.json)
Only deterministic features already present in report.json are used (priority, hop, risk group,
sub-reason, changed lines, number of roots reaching a node, test/log flags).
"""
import json
import statistics
import sys
from pathlib import Path

RISK = ["logic", "abi_layout", "ownership_lifetime", "thread_safety", "exception_safety", "build_config"]
HIGH = {"abi_layout", "thread_safety", "exception_safety", "ownership_lifetime"}
LOW_SUBS = {"header_change", "inline_change", "logging", "test_code"}
PR = {"P1": 0, "P2": 1, "P3": 2}


def short(q):
    return q.split("::")[-1]


def load(run_dir: Path):
    out = []
    for row in json.loads((run_dir / "pilot.json").read_text()):
        rp = run_dir / f"out-{row['intro']}" / "report.json"
        if row.get("verdict") not in ("surfaced", "file-level", "missed") or not rp.exists():
            continue
        truth = {(t.split(":", 1)[0], fn) for t in row["truth"] for fn in t.split(":", 1)[1].split(",") if fn}
        out.append((row, json.loads(rp.read_text()), truth))
    return out


def features(rep):
    roots = {s["id"]: s for s in rep.get("changed_symbols", [])}
    nodes = {n["id"]: n for n in rep.get("impact_nodes", [])}
    feats = []
    for c in rep["test_case_candidates"]:
        nid = c.get("node_id", "")
        f = {"prio": PR[c["priority"]], "hop": c["hop_distance"], "group": c["risk_group"], "sub": c.get("sub_reason"),
             "node": nid, "ev": (c["evidence"][0]["file_path"], short(c["evidence"][0]["qualified_name"]))}
        if c["hop_distance"] == 0 and nid in roots:
            r = roots[nid]
            f["lines"] = r.get("changed_lines", 0)
            f["strong"] = len({x["risk_group"] for x in r["risks"] if x["sub_reason"] not in LOW_SUBS})
            f["ngroups"] = len({x["risk_group"] for x in r["risks"]})
            f["nroots"] = 1
            f["rootlines"] = f["lines"]
            f["ckind"] = r.get("change_kind")
        else:
            rs = nodes.get(nid, {}).get("roots", [])
            f["lines"] = 0
            f["strong"] = 0
            f["ngroups"] = len(nodes.get(nid, {}).get("risk_groups", []))
            f["nroots"] = len(rs)
            f["rootlines"] = sum(roots.get(r, {}).get("changed_lines", 0) for r in rs)
            f["ckind"] = "impacted"
        feats.append(f)
    return feats


def metrics(data, keyfn, group_by_symbol=False):
    ranks, sranks = [], []
    for _row, rep, truth in data:
        fs = features(rep)
        order = sorted(range(len(fs)), key=lambda i: keyfn(fs[i]))
        if group_by_symbol:
            best = {}
            for pos, i in enumerate(order):
                best.setdefault(fs[i]["node"], pos)
            order = sorted(order, key=lambda i: (best[fs[i]["node"]], order.index(i)))
        rank = srank = None
        seen = []
        for pos, i in enumerate(order):
            ev = fs[i]["ev"]
            if ev not in seen:
                seen.append(ev)
            if ev in truth:
                rank, srank = pos + 1, len(seen)
                break
        ranks.append(rank or 10**4)
        sranks.append(srank or 10**4)
    n = len(ranks)
    return {"n": n, "top10": sum(r <= 10 for r in ranks), "top20": sum(r <= 20 for r in ranks),
            "top50": sum(r <= 50 for r in ranks), "mrr": round(sum(1 / r for r in ranks) / n, 3),
            "median": statistics.median(ranks), "sym_top10": sum(r <= 10 for r in sranks),
            "sym_mrr": round(sum(1 / r for r in sranks) / n, 3)}


import math
SEV = {"thread_safety": 3, "ownership_lifetime": 3, "exception_safety": 3, "abi_layout": 2, "logic": 2, "build_config": 1}


def lowsub(f):
    return f["sub"] in LOW_SUBS or (f["hop"] > 0 and f["sub"] == "signature_change")


CANDIDATES = {
    "BEST": lambda f: (f["hop"], lowsub(f), -int(math.log2(1 + f["rootlines"])), -SEV[f["group"]], -f["nroots"]),
    "BEST+removed-last": lambda f: (f["hop"], lowsub(f), f["ckind"] == "removed",
                                    -int(math.log2(1 + f["rootlines"])), -SEV[f["group"]], -f["nroots"]),
    "BEST+modified-first": lambda f: (f["hop"], lowsub(f), f["ckind"] not in ("modified", "impacted"),
                                      -int(math.log2(1 + f["rootlines"])), -SEV[f["group"]], -f["nroots"]),
    "BEST+added-first": lambda f: (f["hop"], lowsub(f), f["ckind"] != "added",
                                   -int(math.log2(1 + f["rootlines"])), -SEV[f["group"]], -f["nroots"]),
    "BEST-lines-bucket3": lambda f: (f["hop"], lowsub(f), -min(3, int(math.log2(1 + f["rootlines"])) // 2),
                                     -SEV[f["group"]], -f["rootlines"]),
    "hop,lowsub,prio,-loglines": lambda f: (f["hop"], lowsub(f), f["prio"], -int(math.log2(1 + f["rootlines"]))),
    "hop,lowsub,-loglines,prio": lambda f: (f["hop"], lowsub(f), -int(math.log2(1 + f["rootlines"])), f["prio"]),
    "hop,lowsub,-loglines,-sev,-nroots": lambda f: (f["hop"], lowsub(f), -int(math.log2(1 + f["rootlines"])),
                                                    -SEV[f["group"]], -f["nroots"]),
    "hop,-lines": lambda f: (f["hop"], -f["rootlines"]),
    "hop,-lines,prio": lambda f: (f["hop"], -f["rootlines"], f["prio"]),
    "hop,lowsub,-lines,prio": lambda f: (f["hop"], lowsub(f), -f["rootlines"], f["prio"]),
    "hop,prio,-loglines": lambda f: (f["hop"], f["prio"], -int(math.log2(1 + f["rootlines"]))),
    "hop,-loglines,prio": lambda f: (f["hop"], -int(math.log2(1 + f["rootlines"])), f["prio"]),
    "hop,-loglines,-sev": lambda f: (f["hop"], -int(math.log2(1 + f["rootlines"])), -SEV[f["group"]], f["prio"]),
    "hop,lowsub,-loglines,-sev": lambda f: (f["hop"], lowsub(f), -int(math.log2(1 + f["rootlines"])), -SEV[f["group"]]),
    "hop,prio,-lines,-sev": lambda f: (f["hop"], f["prio"], -f["rootlines"], -SEV[f["group"]]),
    "current-order(prio,hop,group)": lambda f: (f["prio"], f["hop"], RISK.index(f["group"])),
    "prio,hop,-strong": lambda f: (f["prio"], f["hop"], -f["strong"], RISK.index(f["group"])),
    "prio,hop,-lines": lambda f: (f["prio"], f["hop"], -f["rootlines"]),
    "prio,hop,-strong,-lines": lambda f: (f["prio"], f["hop"], -f["strong"], -f["rootlines"]),
    "prio,-lines,hop": lambda f: (f["prio"], -f["rootlines"], f["hop"]),
    "prio,hop,-ngroups,-lines": lambda f: (f["prio"], f["hop"], -f["ngroups"], -f["rootlines"]),
    "hop,prio,-lines": lambda f: (f["hop"], f["prio"], -f["rootlines"]),
    "prio,hop,-nroots,-lines": lambda f: (f["prio"], f["hop"], -f["nroots"], -f["rootlines"]),
}


def main():
    data = []
    for d in sys.argv[1:]:
        data += load(Path(d))
    dev = data[0::2]
    hold = data[1::2]
    print(f"{len(data)} regressions ({len(dev)} dev / {len(hold)} holdout)")
    for name, fn in CANDIDATES.items():
        for grouped in (False, True):
            m_dev, m_hold, m_all = metrics(dev, fn, grouped), metrics(hold, fn, grouped), metrics(data, fn, grouped)
            print(f"{name:32s} {'grouped' if grouped else 'flat   '} all={m_all} dev_mrr={m_dev['mrr']} "
                  f"hold_mrr={m_hold['mrr']}")


if __name__ == "__main__":
    main()
