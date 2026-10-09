"""Optional, bounded LLM enrichment (FR-011, FR-012, FR-012a; research.md §4).

Only already-emitted cases are sent — id, risk group, symbol name, file:line and the deterministic
activation condition. No source code. The LLM may rewrite ``description`` text only; ids, evidence,
priority and risk group are never touched. Any failure degrades to the deterministic text.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from tcadvisor.models import SymbolRef, TestCaseCandidate, UsageError

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_CASES = 200


def check_endpoint(endpoint: str, external_approved: bool) -> None:
    host = urlparse(endpoint).hostname or ""
    if host not in LOCAL_HOSTS and not external_approved:
        raise UsageError(f"LLM endpoint '{endpoint}' is not local; pass --llm-external-approved to confirm documented "
                         "team approval for sending case metadata off this machine (Principle VI)")


def build_prompt(cases: list[TestCaseCandidate]) -> str:
    lines = []
    for c in cases[:MAX_CASES]:
        ev = c.evidence[0]
        loc = f"{ev.file_path}:{ev.line}" if isinstance(ev, SymbolRef) else ""
        lines.append(json.dumps({"id": c.id, "risk": c.risk_group, "sub": c.sub_reason,
                                 "symbol": ev.qualified_name if isinstance(ev, SymbolRef) else "", "at": loc,
                                 "why": c.activation_condition[:300]}))
    return ("You write concise test-case descriptions for C++ reviewers. For every JSON line below, return one "
            "sentence (max 30 words, English) saying what a tester should check. Do not invent symbols. Reply with a "
            "JSON object mapping id -> description and nothing else.\n" + "\n".join(lines))


def enrich(cases: list[TestCaseCandidate], endpoint: str, model: str, out_dir: Path, timeout: float = 120.0
           ) -> tuple[bool, dict[str, int] | None, str | None]:
    """Returns (degraded, token_usage, error)."""
    if not cases:
        return False, {"prompt_tokens": 0, "completion_tokens": 0}, None
    prompt = build_prompt(cases)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "llm-prompt.log").write_text(prompt, encoding="utf-8")  # auditable (constitution §LLM boundary)
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode()
    req = urllib.request.Request(endpoint.rstrip("/") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        mapping = json.loads(data.get("response", "{}"))
    except Exception as exc:  # noqa: BLE001 - any failure degrades gracefully
        return True, None, f"{type(exc).__name__}: {exc}"
    by_id = {c.id: c for c in cases}
    for cid, text in mapping.items() if isinstance(mapping, dict) else []:
        if cid in by_id and isinstance(text, str) and text.strip():
            by_id[cid].description = text.strip()[:400]
    usage = {"prompt_tokens": int(data.get("prompt_eval_count", 0) or 0),
             "completion_tokens": int(data.get("eval_count", 0) or 0)}
    return False, usage, None
