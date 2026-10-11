"""`tcadvisor verify`: run the verification step with the Claude Code CLI in headless mode.

Token plan (spec 002 SC-202): one tool-less Haiku call per batch of <=8 packets (code windows only), one
tool-less Sonnet call for the synthesis. Sends code snippets to the model provider, therefore requires an
explicit approval flag (constitution VI).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from pathlib import Path
from typing import Any

from tcadvisor.models import UsageError
from tcadvisor.report.render import to_brief
from tcadvisor.verify.annotate import merge
from tcadvisor.verify.pack import write_packets


def _prompt(name: str) -> str:
    return resources.files("tcadvisor.verify").joinpath(f"prompts/{name}.md").read_text(encoding="utf-8")


def _json_from(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


def call_claude(claude: str, model: str, prompt: str, budget_usd: float | None, timeout: int = 600
                ) -> tuple[dict[str, Any], dict[str, Any]]:
    # temp cwd + user-only settings: the analysed repo's .claude/ hooks and CLAUDE.md are never loaded
    cmd = [claude, "-p", "--model", model, "--tools", "", "--output-format", "json", "--setting-sources", "user"]
    if budget_usd:
        cmd += ["--max-budget-usd", str(budget_usd)]
    with tempfile.TemporaryDirectory(prefix="tcadvisor-claude-") as cwd:
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                             cwd=cwd)
    if res.returncode != 0:
        raise RuntimeError(f"claude exited {res.returncode}: {res.stderr.strip()[-400:]}")
    outer = json.loads(res.stdout)
    u = outer.get("usage") or {}
    usage = {"cost_usd": float(outer.get("total_cost_usd") or 0),
             "input_tokens": sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                              "cache_read_input_tokens")),
             "output_tokens": int(u.get("output_tokens") or 0)}
    return _json_from(outer.get("result", "")), usage


def verify(report_path: Path, *, approved: bool, claude: str | None = None, verify_model: str = "haiku",
           synth_model: str = "sonnet", parallel: int = 4, priorities: set[str] | None = None, max_cases: int = 60,
           batch: int = 8, budget_usd: float | None = None, progress=None) -> dict[str, Any]:
    if not approved:
        raise UsageError("AI verification sends the packed code windows (not the repository) to the model provider. "
                         "Pass --ai-external-approved to confirm this is allowed for this code base.")
    claude = claude or shutil.which("claude")
    if not claude:
        raise UsageError("Claude Code CLI ('claude') not found; install it or pass --claude-bin")
    say = progress or (lambda _m: None)
    out_dir = report_path.parent / "verify"
    manifest = write_packets(report_path, out_dir, priorities or {"P1", "P2"}, max_cases, batch)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    verifier = _prompt("verifier")
    usage_total = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0}
    errors: list[str] = []

    def run_batch(b: dict) -> dict[str, Any]:
        text = Path(b["file"]).read_text(encoding="utf-8")
        say(f"verifying {Path(b['file']).name} ({b['cases']} cases) with {verify_model}")
        out, usage = call_claude(claude, verify_model, verifier + "\n\nBATCH:\n" + text, budget_usd)
        for k in ("cost_usd", "input_tokens", "output_tokens"):
            usage_total[k] += usage[k]
        usage_total["calls"] += 1
        cases = out.get("cases", out)
        if isinstance(cases, list):  # tolerate the array shape used by the workflow schema
            cases = {c["id"]: c for c in cases if isinstance(c, dict) and "id" in c}
        return cases

    merged: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        for b, fut in [(b, pool.submit(run_batch, b)) for b in manifest["batches"]]:
            try:
                merged.update(fut.result())
            except Exception as exc:  # noqa: BLE001 - a failed batch leaves its cases unverified
                errors.append(f"{Path(b['file']).name}: {exc}")
    synth: dict[str, Any] = {"summary": "", "additional_checks": []}
    if merged:
        say(f"synthesising with {synth_model}")
        compact = {cid: {"v": v.get("verdict"), "n": v.get("note", "")} for cid, v in merged.items()}
        try:
            synth, usage = call_claude(claude, synth_model, _prompt("synthesizer") + "\n\nBRIEF:\n" + to_brief(report)
                                       + "\nVERDICTS:\n" + json.dumps(compact), budget_usd)
            for k in ("cost_usd", "input_tokens", "output_tokens"):
                usage_total[k] += usage[k]
            usage_total["calls"] += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"synthesis: {exc}")
    verdicts = {"cases": merged, "summary": synth.get("summary", ""),
                "additional_checks": synth.get("additional_checks", []),
                "models": [f"{verify_model} (case verification)", f"{synth_model} (synthesis)"]}
    (out_dir / "verdicts.json").write_text(json.dumps(verdicts, indent=1), encoding="utf-8")
    warnings = merge(report, verdicts)
    report["ai_verification"]["usage"] = usage_total
    report["ai_verification"]["errors"] = errors + manifest["notes"]
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"verified": report["ai_verification"]["verified_cases"], "usage": usage_total, "errors": errors,
            "warnings": warnings, "packed_tokens": manifest["approx_tokens_total"]}
