"""Merge AI verification verdicts into report.json (annotation only: constitution III).

Verdicts never add, remove, reorder or re-prioritise cases; they only attach `verification`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tcadvisor.models import UsageError

VERDICTS = {"confirmed", "weak", "needs_info"}


def merge(report: dict[str, Any], verdicts: dict[str, Any]) -> list[str]:
    by_id = {c["id"]: c for c in report["test_case_candidates"]}
    warnings = []
    for cid, v in (verdicts.get("cases") or {}).items():
        case = by_id.get(cid)
        if case is None:
            warnings.append(f"unknown case id {cid} ignored")
            continue
        verdict = v.get("verdict")
        if verdict not in VERDICTS:
            warnings.append(f"{cid}: invalid verdict {verdict!r} ignored")
            continue
        case["verification"] = {
            "verdict": verdict,
            "note": str(v.get("note", ""))[:600],
            "extra_corner_cases": [str(x)[:300] for x in (v.get("extra_corner_cases") or [])][:6],
            "recheck": True,  # a model never signals exclusion (constitution III); kept for schema compatibility
            "by": "ai",
        }
    repo = Path(report["change_input"]["target_repo_path"]).resolve()
    checks = []
    for a in (verdicts.get("additional_checks") or [])[:15]:
        ev = str(a.get("evidence", ""))[:200]
        checks.append({"title": str(a.get("title", ""))[:200], "why": str(a.get("why", ""))[:500],
                       "evidence": ev if _resolves(repo, ev) else "",
                       "evidence_status": "resolved" if _resolves(repo, ev) else "unverified AI suggestion"})
    report["ai_verification"] = {
        "summary": str(verdicts.get("summary", ""))[:2000],
        "additional_checks": checks,
        "models": verdicts.get("models") or [],
        "verified_cases": sum(1 for c in report["test_case_candidates"] if "verification" in c),
        "warnings": warnings,
    }
    return warnings


def _resolves(repo: Path, evidence: str) -> bool:
    """`file:line` that exists inside the repository (AI text is never trusted as evidence)."""
    m = re.match(r"^(.+?):(\d+)$", evidence.strip())
    if not m:
        return False
    p = (repo / m.group(1)).resolve()
    try:
        p.relative_to(repo)
    except ValueError:
        return False
    if not p.is_file():
        return False
    with p.open(encoding="utf-8", errors="replace") as fh:
        n = sum(1 for _ in fh)
    return 1 <= int(m.group(2)) <= n


def annotate_file(report_path: Path, verdicts_path: Path) -> list[str]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        verdicts = json.loads(verdicts_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read report/verdicts: {exc}") from exc
    warnings = merge(report, verdicts)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return warnings
