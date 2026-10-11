"""Tester results stored inside ``report.html`` (spec 006 US3, contracts/report-results.schema.json).

The form in the HTML report writes a JSON block ``<script type="application/json" id="results">`` holding
one record per case key plus the embedded attachments. This module reads that block back (``tcadvisor
results``, ``--previous-report``), validates records with the same rules as the form, summarises them and
carries them over to a new analysis by case key. Results never influence which cases exist or their order
(FR-613).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tcadvisor.models import UsageError

SCHEMA = 1
VERDICTS = ("pass", "fail", "not_testable", "cannot_occur")
VERDICT_LABEL = {"pass": "PASS", "fail": "FAIL", "not_testable": "N/T", "cannot_occur": "N/O", None: "—"}
_BLOCK = re.compile(r'<script type="application/json" id="results">(.*?)</script>', re.S)
_DATA = re.compile(r'<script id="data" type="application/json">(.*?)</script>', re.S)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def report_key(report: dict[str, Any]) -> str:
    ci = report.get("change_input", {})
    raw = json.dumps([report.get("tool", {}).get("version"), ci.get("mode"), ci.get("commit_range"),
                      report.get("commit_hash"), ci.get("symbols_requested")], sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def empty_block(report: dict[str, Any], warn_mb: int = 50) -> dict[str, Any]:
    return {"schema": SCHEMA, "report_key": report_key(report),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "attachment_warn_mb": warn_mb, "results": {}, "orphaned_results": {}, "attachments": {}}


def read_results(path: Path) -> dict[str, Any]:
    """Results block of a (filled) tcadvisor report.html; UsageError when absent or unsupported."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read report {path}: {exc}") from exc
    m = _BLOCK.search(text)
    if not m:
        raise UsageError(f"{path} is not a tcadvisor report with a test-results block")
    try:
        block = json.loads(m.group(1))
    except ValueError as exc:
        raise UsageError(f"{path}: test-results block is not valid JSON: {exc}") from exc
    if not isinstance(block, dict) or block.get("schema") != SCHEMA or not isinstance(block.get("results"), dict):
        raise UsageError(f"{path}: unsupported test-results schema {block.get('schema') if isinstance(block, dict) else '?'}")
    block.setdefault("orphaned_results", {})
    block.setdefault("attachments", {})
    return block


def read_cases(path: Path) -> list[dict[str, Any]]:
    """Cases of the analysis embedded in a report.html (id, key, description, ...)."""
    m = _DATA.search(path.read_text(encoding="utf-8"))
    if not m:
        raise UsageError(f"{path} has no analysis data block")
    return json.loads(m.group(1)).get("test_case_candidates", [])


def validate_record(rec: dict[str, Any], attachments: dict[str, Any] | None = None) -> list[str]:
    """Problems that keep a record from being complete (same rules as the form, FR-609)."""
    v = rec.get("verdict")
    if v is None:
        return []
    if v not in VERDICTS:
        return [f"unknown verdict {v!r}"]
    out = []
    if not str(rec.get("tester", "")).strip():
        out.append("tester is required")
    if not _DATE.match(str(rec.get("date", ""))):
        out.append("date (YYYY-MM-DD) is required")
    if v in ("not_testable", "cannot_occur") and not str(rec.get("comment", "")).strip():
        out.append("a justification comment is required")
    atts = [a for a in rec.get("attachments", []) if attachments is None or a in attachments]
    if v == "fail" and not atts and not str(rec.get("defect_ref", "")).strip():
        out.append("a failed case needs an attachment or a defect reference")
    return out


def summary(block: dict[str, Any], case_keys: list[str]) -> dict[str, Any]:
    res = block.get("results", {})
    atts = block.get("attachments", {})
    counts = {v: 0 for v in VERDICTS}
    untested = invalid = recheck = 0
    for k in case_keys:
        rec = res.get(k) or {}
        v = rec.get("verdict")
        if v in counts:
            counts[v] += 1
        else:
            untested += 1
        if validate_record(rec, atts):
            invalid += 1
        if rec.get("needs_recheck"):
            recheck += 1
    size = sum(int(a.get("size", 0)) for a in atts.values())
    return {**counts, "untested": untested, "invalid": invalid, "needs_recheck": recheck, "total": len(case_keys),
            "complete": untested == 0 and invalid == 0 and recheck == 0, "attachment_bytes": size,
            "orphaned": len(block.get("orphaned_results", {}))}


def carry_over(previous: dict[str, Any], report: dict[str, Any], warn_mb: int = 50) -> dict[str, Any]:
    """New results block for ``report``: records copied by case key; a changed code fingerprint marks the
    record ``needs_recheck``; records of cases that no longer exist go to ``orphaned_results``."""
    block = empty_block(report, warn_mb)
    cases = {c["key"]: c for c in report.get("test_case_candidates", [])}
    used: set[str] = set()
    for key, rec in previous.get("results", {}).items():
        rec = dict(rec)
        if key in cases:
            if rec.get("fingerprint") and rec["fingerprint"] != cases[key].get("code_fingerprint"):
                rec["needs_recheck"] = True
            rec["carried_from"] = previous.get("report_key")
            block["results"][key] = rec
        else:
            rec.setdefault("last_description", rec.get("description", ""))
            block["orphaned_results"][key] = rec
        used.update(rec.get("attachments", []))
    for key, rec in previous.get("orphaned_results", {}).items():
        if key not in block["results"] and key not in cases:
            block["orphaned_results"][key] = rec
            used.update(rec.get("attachments", []))
    block["attachments"] = {k: v for k, v in previous.get("attachments", {}).items() if k in used}
    attach_case_results(report, block)
    return block


def attach_case_results(report: dict[str, Any], block: dict[str, Any]) -> None:
    """Copy each case's record (attachments by id + name only) onto the case as ``test_result``."""
    for c in report.get("test_case_candidates", []):
        rec = block["results"].get(c.get("key", ""))
        c["test_result"] = dict(rec) if rec else None
        if rec is not None:
            c["test_result"]["attachments"] = [{"id": a, "name": block["attachments"].get(a, {}).get("name", a)}
                                               for a in rec.get("attachments", [])]
