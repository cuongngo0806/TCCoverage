"""Token-lean verification packets (spec 002, US2).

The deterministic report already decided *what* is impacted. A verifier model only needs, per impacted
symbol, the cases attached to it and a short window of code — never the repository. Cases sharing a
symbol share one packet, so code is sent once.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

WINDOW_BEFORE = 3
WINDOW_MAX = 40
CALLSITE_LINES = 1


def _lines(repo: Path, rel: str, cache: dict[str, list[str]]) -> list[str]:
    if rel not in cache:
        try:
            cache[rel] = (repo / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            cache[rel] = []
    return cache[rel]


def _window(lines: list[str], line: int) -> str:
    start = max(1, line - WINDOW_BEFORE)
    out, depth, opened = [], 0, False
    for n in range(start, min(len(lines), start + WINDOW_MAX - 1) + 1):
        text = lines[n - 1]
        out.append(f"{n:5d}| {text}")
        if n < line:
            continue  # context lines before the symbol do not count towards its braces
        depth += text.count("{") - text.count("}")
        opened = opened or "{" in text
        if n >= line and opened and depth <= 0:
            break  # end of the symbol body
    return "\n".join(out)


def _references(lines: list[str], names: set[str], limit: int = 12) -> str:
    """For file-level cases (rebuild a TU / header users): only the lines mentioning a changed symbol."""
    pat = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(names)) + r")\b") if names else None
    hits = [f"{i:5d}| {ln}" for i, ln in enumerate(lines, 1) if pat and pat.search(ln)]
    return "\n".join(hits[:limit]) + (f"\n  ... {len(hits) - limit} more" if len(hits) > limit else "")


def build_packets(report: dict[str, Any], priorities: set[str], max_cases: int) -> tuple[list[dict], list[str]]:
    repo = Path(report["change_input"]["target_repo_path"])
    changed_names = {s["symbol"]["qualified_name"].split("::")[-1] for s in report.get("changed_symbols", [])
                     if s["symbol"]["kind"] != "file"}
    cache: dict[str, list[str]] = {}
    chosen = [c for c in report["test_case_candidates"] if c["priority"] in priorities]
    dropped = chosen[max_cases:]
    chosen = chosen[:max_cases]
    packets: dict[str, dict] = {}
    for c in chosen:
        ev = c["evidence"][0]
        key = f"{ev['file_path']}:{ev['line']}:{ev['qualified_name']}"
        p = packets.get(key)
        if p is None:
            lines = _lines(repo, ev["file_path"], cache)
            calls = []
            for e in c["evidence"][1:4]:
                loc = e["source_location"]
                src = _lines(repo, loc["file_path"], cache)
                code = src[loc["line"] - 1].strip() if 0 < loc["line"] <= len(src) else ""
                calls.append(f"{e['relation']} -> {e['to_symbol']['qualified_name']} at {loc['file_path']}:{loc['line']}: {code}")
            p = packets[key] = {"packet": f"K{len(packets) + 1:03d}", "symbol": ev["qualified_name"],
                                "at": f"{ev['file_path']}:{ev['line']}", "links": calls,
                                "code": _window(lines, ev["line"]) if ev.get("kind") != "file"
                                else _references(lines, changed_names), "cases": []}
        p["cases"].append({k: c.get(k) for k in ("id", "priority", "risk_group", "sub_reason", "description",
                                                    "activation_condition", "corner_cases", "hop_distance")})
    notes = [f"{len(dropped)} {'/'.join(sorted(priorities))} case(s) beyond --max-cases were not packed: "
             + ", ".join(c["id"] for c in dropped[:20])] if dropped else []
    return list(packets.values()), notes


def write_packets(report_path: Path, out_dir: Path, priorities: set[str], max_cases: int, batch: int) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    packets, notes = build_packets(report, priorities, max_cases)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("batch-*.json"):
        old.unlink()
    changed = [f"{s['symbol']['qualified_name']} @{s['symbol']['file_path']}:{s['symbol']['line']} "
               f"[{','.join(sorted({r['risk_group'] for r in s['risks']}))}]" for s in report.get("changed_symbols", [])]
    header = {"changed": changed, "flags": [f"{f['category']}: {f['reason']}" for f in report["uncertainty_flags"]],
              "existing_tests": [t["test"] for t in report.get("existing_tests", [])]}
    batches = []
    for i in range(0, len(packets), batch):
        b = {"batch": f"batch-{i // batch + 1:02d}", **header, "packets": packets[i:i + batch]}
        path = out_dir / f"{b['batch']}.json"
        path.write_text(json.dumps(b, indent=1), encoding="utf-8")
        batches.append({"file": str(path), "packets": len(b["packets"]),
                        "cases": sum(len(p["cases"]) for p in b["packets"]),
                        "approx_tokens": len(path.read_text(encoding="utf-8")) // 4})
    manifest = {"report": str(report_path), "batches": batches, "notes": notes,
                "approx_tokens_total": sum(b["approx_tokens"] for b in batches)}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest
