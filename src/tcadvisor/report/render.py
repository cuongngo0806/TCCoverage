"""Markdown / JSON / brief renderers (FR-008). All output is English (Principle IX)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PRIO_ORDER = ("P1", "P2", "P3")
GROUP_LABEL = {
    "logic": "Logic",
    "abi_layout": "ABI / layout",
    "ownership_lifetime": "Ownership / lifetime",
    "thread_safety": "Thread safety",
    "exception_safety": "Exception safety",
    "build_config": "Build config",
}
MERMAID_MAX_NODES = 60


def _ev_label(ev: dict[str, Any]) -> str:
    if "qualified_name" in ev:
        return f"`{ev['qualified_name']}` ({ev['file_path']}:{ev['line']})"
    loc = ev["source_location"]
    return f"{ev['from_symbol']['qualified_name']} —{ev['relation']}→ {ev['to_symbol']['qualified_name']} " \
           f"({loc['file_path']}:{loc['line']})"


def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def _targets(ts: list[str], limit: int = 6) -> str:
    return (", ".join(ts[:limit]) + (f" (+{len(ts) - limit} more)" if len(ts) > limit else "")) if ts else "-"


def summary_line(r: dict[str, Any]) -> str:
    cases = r["test_case_candidates"]
    by = {p: sum(1 for c in cases if c["priority"] == p) for p in PRIO_ORDER}
    llm = "degraded (LLM unavailable)" if r["llm_degraded"] else "enabled" if r["llm_enabled"] else "disabled"
    if r.get("no_detected_impact"):
        head = "No detected impact"
    else:
        head = f"{len(cases)} test case(s) [P1 {by['P1']} / P2 {by['P2']} / P3 {by['P3']}]"
    tr = _test_summary(r)
    return (f"{head}; {len(r['uncertainty_flags'])} uncertainty flag(s); {tr}"
            f"{len(r.get('changed_files', []))} changed file(s); targets: {_targets(r['target_scope'])}; "
            f"cache_hit: {str(r['cache_hit']).lower()}; LLM: {llm}; "
            f"{r.get('metrics', {}).get('duration_seconds', 0)}s")


def _mermaid_id(i: int) -> str:
    return f"n{i}"


def mermaid(r: dict[str, Any]) -> str:
    nodes = r.get("impact_nodes", [])[:MERMAID_MAX_NODES]
    ids = {n["id"]: _mermaid_id(i) for i, n in enumerate(nodes)}
    out = ["flowchart RL"]
    for n in nodes:
        label = re.sub(r'["<>\[\]{}|]', "", n["symbol"]["qualified_name"])[:60]
        hop = n["hop_distance"]
        shape = f'(["{label}"])' if hop == 0 else f'["{label}"]' if n["symbol"]["kind"] != "file" else f'[/"{label}"/]'
        out.append(f"  {ids[n['id']]}{shape}:::h{min(hop, 2)}")
    seen = set()
    for n in nodes:
        for e in n["edges"]:
            # edge: dependent (this node) -> changed dependency
            to_name = e["to_symbol"]["qualified_name"]
            tgt = next((m for m in nodes if m["symbol"]["qualified_name"] == to_name
                        and m["hop_distance"] < n["hop_distance"]), None)
            if tgt is None:
                continue
            key = (ids[n["id"]], ids[tgt["id"]], e["relation"])
            if key in seen:
                continue
            seen.add(key)
            out.append(f"  {key[0]} -- {e['relation']} --> {key[1]}")
    out += ["  classDef h0 fill:#fde2e1,stroke:#c0392b,color:#000",
            "  classDef h1 fill:#fff1d6,stroke:#d68910,color:#000",
            "  classDef h2 fill:#e8f1fb,stroke:#2e86c1,color:#000"]
    if len(r.get("impact_nodes", [])) > MERMAID_MAX_NODES:
        out.append(f"  more[\"+{len(r['impact_nodes']) - MERMAID_MAX_NODES} more nodes (see report.html)\"]")
    return "\n".join(out)


def _test_summary(r: dict[str, Any]) -> str:
    """'test results: …; ' when the report carries tester results (spec 006), else ''."""
    if not r.get("test_results"):
        return ""
    from tcadvisor.report.results import summary
    s = summary(r["test_results"], [c["key"] for c in r["test_case_candidates"]])
    recheck = f" / {s['needs_recheck']} re-check" if s["needs_recheck"] else ""
    return (f"test results: {s['pass']} pass / {s['fail']} fail / {s['not_testable']} n/t / "
            f"{s['cannot_occur']} n/o / {s['untested']} untested{recheck}; ")


def _verdict_tag(c: dict[str, Any]) -> str:
    tr = c.get("test_result")
    if tr is None:
        return ""
    from tcadvisor.report.results import VERDICT_LABEL
    return f" [{VERDICT_LABEL.get(tr.get('verdict'), '—')}]" + (" (re-check)" if tr.get("needs_recheck") else "")


def to_markdown(r: dict[str, Any]) -> str:
    L: list[str] = ["# Change Impact & Test Case Report", ""]
    ci = r["change_input"]
    src = ci.get("commit_range") or ("working tree" if ci.get("working_tree") else
                                     ", ".join(ci.get("symbols_requested") or []))
    L += [f"- **Change**: {ci['mode']} — {src}", f"- **Repository**: `{ci['target_repo_path']}`",
          f"- **Summary**: {summary_line(r)}", ""]
    if r.get("no_detected_impact"):
        L += ["> **No detected impact.** The change touches no indexed symbol semantically (e.g. comments, "
              "whitespace or non-C++ files only). This is a positive result, not a tool failure.", ""]
    if r.get("changed_symbols"):
        L += ["## Changed symbols", "", "| Symbol | Change | Risk groups |", "|---|---|---|"]
        for s in r["changed_symbols"]:
            groups = ", ".join(sorted({GROUP_LABEL[x['risk_group']] + (f" ({x['sub_reason']})" if x['sub_reason'] else "")
                                       for x in s["risks"]}))
            L.append(f"| `{_md_cell(s['symbol']['qualified_name'])}` {s['symbol']['file_path']}:{s['symbol']['line']} "
                     f"| {s['change_kind']} | {groups} |")
        L.append("")
    if r.get("impact_nodes"):
        L += ["## Impact flow", "", "Arrows point from the affected code to what it depends on "
              "(red = changed, orange = direct, blue = indirect).", "", "```mermaid", mermaid(r), "```", ""]
    cases = r["test_case_candidates"]
    if cases:
        L += ["## Test cases to check", "",
              "Listed in relevance order (closest to the change, substantive before recompile-only, larger changes "
              "first); the P1/P2/P3 label is the deterministic priority.", ""]
        for title, sel in (("Changed code", lambda c: c["hop_distance"] == 0),
                           ("Direct impact (1 hop)", lambda c: c["hop_distance"] == 1),
                           ("Indirect impact", lambda c: c["hop_distance"] > 1)):
            group = [c for c in cases if sel(c)]
            if not group:
                continue
            L += [f"### {title} ({len(group)})", ""]
            for c in group:
                tr = c.get("test_result") or {}
                box = "x" if tr.get("verdict") and not tr.get("needs_recheck") else " "
                L.append(f"- [{box}] **{c['id']}** {c['priority']} [{GROUP_LABEL[c['risk_group']]}] "
                         f"{_md_cell(c['description'])}{_verdict_tag(c)}")
                L.append(f"  - *When*: {_md_cell(c['activation_condition'])}")
                L.append("  - *Evidence*: " + "; ".join(_ev_label(e) for e in c["evidence"]))
                if c.get("path"):
                    L.append("  - *Path*: " + " → ".join(
                        f"`{x['symbol']['qualified_name']}` ({x['role']}{', checked' if x['checked'] else ''})"
                        for x in c["path"]))
                if c.get("corner_cases"):
                    L.append("  - *Corner cases*: " + "; ".join(c["corner_cases"][:5]))
                L.append(f"  - *Targets*: {', '.join(c['related_cmake_targets'])}")
                if tr.get("verdict"):
                    names = ", ".join(a["name"] for a in tr.get("attachments", []))
                    L.append(f"  - *Test result*: {tr['verdict']} by {_md_cell(tr.get('tester', ''))} on "
                             f"{tr.get('date', '')}{' — ' + _md_cell(tr['comment']) if tr.get('comment') else ''}"
                             f"{'; defect ' + _md_cell(tr['defect_ref']) if tr.get('defect_ref') else ''}"
                             f"{'; evidence: ' + _md_cell(names) if names else ''}")
                v = c.get("verification")
                if v:
                    L.append(f"  - *AI verification*: **{v['verdict']}**{' — re-check' if v['recheck'] else ''}"
                             f"{': ' + _md_cell(v['note']) if v['note'] else ''}")
                    if v["extra_corner_cases"]:
                        L.append("  - *AI corner cases*: " + "; ".join(_md_cell(x) for x in v["extra_corner_cases"]))
            L.append("")
    av = r.get("ai_verification")
    if av:
        L += ["## AI verification (annotations only — cases are never removed)", "",
              f"{_md_cell(av['summary'])}", "", f"- verified cases: {av['verified_cases']}; models: "
              f"{', '.join(av.get('models') or []) or '-'}"]
        for a in av["additional_checks"]:
            L.append(f"- [ ] **Also check** (AI): {_md_cell(a['title'])} — {_md_cell(a['why'])}"
                     f"{' (' + a['evidence'] + ')' if a['evidence'] else ' (unverified AI suggestion: no resolvable file:line)'}")
        L.append("")
    if r.get("existing_tests"):
        L += ["## Existing tests to re-run", "",
              "`--gtest_filter=" + ":".join(t["test"] for t in r["existing_tests"]) + "`", ""]
        L += [f"- `{t['test']}` ({t['file_path']}:{t['line']}, hop {t['hop_distance']})" for t in r["existing_tests"]]
        L.append("")
    for t in r.get("trigger_sources") or []:
        L += [f"## Trigger sources of `{t['target']['qualified_name']}`", "",
              f"Guard added in {', '.join(f'`{c}`' for c in t['covered_by'])}: `{_md_cell('; '.join(t['guard']))}`", "",
              "| Source | Kind | Guard | |", "|---|---|---|---|"]
        for x in t["sources"]:
            sym = x["symbol"]
            kind = (f"callback registered at {x['registered_at'][0]}:{x['registered_at'][1]}" if x["registered_at"]
                    else "call")
            L.append(f"| `{sym['qualified_name']}` {sym['file_path']}:{x['call_line']} | {kind} | {x['guard']} | "
                     f"{'covered by this change' if x['covered_by_change'] else 'check (see cases)'} |")
        L.append("")
    if r["uncertainty_flags"]:
        L += ["## Uncertain — needs manual review", "", "| Category | Symbol | Reason |", "|---|---|---|"]
        for f in r["uncertainty_flags"]:
            sym = f["related_symbol"]
            where = f"`{sym['qualified_name']}` {sym['file_path']}:{sym['line']}" if sym else "-"
            L.append(f"| {f['category']} | {_md_cell(where)} | {_md_cell(f['reason'])} |")
        L.append("")
    if r.get("affected_targets"):
        L += ["## Build / test scope to rerun", ""]
        for t in r["affected_targets"]:
            via = f" (links {t['via']})" if t.get("via") else ""
            L.append(f"- `{t['name']}` — {t['relation']}{via}")
        L.append("")
    if r.get("out_of_scope"):
        L += ["## Skipped (out of scope)", ""]
        for o in r["out_of_scope"]:
            L.append(f"- `{o['path']}`{' `' + o['symbol'] + '`' if o.get('symbol') else ''}: {o['reason']}")
        L.append("")
    if r.get("run_notes"):
        L += ["## Run notes", ""] + [f"- {n}" for n in r["run_notes"]] + [""]
    m = r.get("metrics", {})
    L += ["## Metrics", "", f"- run_id: `{r['run_id']}`", f"- duration: {m.get('duration_seconds')}s",
          f"- cache_hit: {r['cache_hit']}", f"- index: {m.get('index')}",
          f"- LLM: enabled={r['llm_enabled']} degraded={r['llm_degraded']} tokens={r['llm_token_usage']}", ""]
    return "\n".join(L)


def to_brief(r: dict[str, Any], limit: int = 80) -> str:
    """Token-lean summary meant for an AI assistant (Claude) or a PR comment."""
    L = [summary_line(r)]
    for s in r.get("changed_symbols", []):
        L.append(f"CHANGED {s['symbol']['qualified_name']} @{s['symbol']['file_path']}:{s['symbol']['line']} "
                 f"[{','.join(sorted({x['risk_group'] for x in s['risks']}))}]")
    for c in r["test_case_candidates"][:limit]:
        ev = c["evidence"][0]
        v = c.get("verification")
        tag = f" [AI:{v['verdict']}]" if v else ""
        L.append(f"{c['id']} {c['priority']} {c['risk_group']} {ev['file_path']}:{ev['line']}{tag} :: {c['description']}"
                 f"{_verdict_tag(c)}")
        if c.get("corner_cases"):
            L.append("   corner: " + " | ".join(c["corner_cases"][:3]))
    if len(r["test_case_candidates"]) > limit:
        L.append(f"... {len(r['test_case_candidates']) - limit} more in report.json")
    for t in r.get("trigger_sources") or []:
        L.append(f"SOURCES {t['target']['qualified_name']} :: " + ", ".join(
            f"{x['symbol']['qualified_name']} ({'covered' if x['covered_by_change'] else 'guard ' + x['guard']})"
            for x in t["sources"]))
    for f in r["uncertainty_flags"]:
        sym = f["related_symbol"]
        L.append(f"UNCERTAIN {f['category']} {sym['qualified_name'] if sym else '-'} :: {f['reason']}")
    if r.get("existing_tests"):
        L.append("RERUN --gtest_filter=" + ":".join(t["test"] for t in r["existing_tests"]))
    for a in (r.get("ai_verification") or {}).get("additional_checks", []):
        L.append(f"AI-ALSO {a['title']} :: {a['why']}")
    if r.get("affected_targets"):
        L.append("TARGETS " + ", ".join(t["name"] for t in r["affected_targets"]))
    for n in r.get("run_notes", []):
        L.append(f"NOTE {n}")
    return "\n".join(L) + "\n"


def _without_attachment_data(r: dict[str, Any]) -> dict[str, Any]:
    """report.json lists attachments (name, type, size, sha256) but their bytes stay in report.html only."""
    tr = r.get("test_results")
    if not tr or not tr.get("attachments"):
        return r
    atts = {k: {f: v for f, v in a.items() if f != "data"} for k, a in tr["attachments"].items()}
    return {**r, "test_results": {**tr, "attachments": atts}}


def write_outputs(r: dict[str, Any], out_dir: Path, fmt: str = "both", same_analysis: bool = False) -> list[Path]:
    """``same_analysis``: re-rendering an existing analysis (verify / annotate / render) keeps the test results
    already recorded in ``out_dir/report.html``. A new analysis never merges them silently: a filled report about
    to be overwritten is first copied to ``report.results-backup-<time>.html`` (use --previous-report to carry
    results over)."""
    from tcadvisor.report.html import to_html
    from tcadvisor.report.results import attach_case_results, read_results

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    old_html = out_dir / "report.html"
    existing = None
    if old_html.is_file():
        try:
            existing = read_results(old_html)
        except Exception:  # noqa: BLE001 - an older report without a results block
            existing = None
    if existing and (existing["results"] or existing["orphaned_results"]):
        if same_analysis:
            r = {**r, "test_case_candidates": [dict(c) for c in r["test_case_candidates"]], "test_results": existing}
            attach_case_results(r, existing)
        elif not (r.get("test_results") or {}).get("results") or r["test_results"] != existing:
            from datetime import datetime
            backup = out_dir / f"report.results-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
            backup.write_bytes(old_html.read_bytes())
            written.append(backup)
    if fmt in ("json", "both", "all"):
        p = out_dir / "report.json"
        p.write_text(json.dumps(_without_attachment_data(r), indent=2), encoding="utf-8")
        written.append(p)
    if fmt in ("md", "both", "all"):
        p = out_dir / "report.md"
        p.write_text(to_markdown(r), encoding="utf-8")
        written.append(p)
    if fmt in ("html", "both", "all"):
        p = out_dir / "report.html"
        p.write_text(to_html(r), encoding="utf-8")
        written.append(p)
    p = out_dir / "report.brief.txt"
    p.write_text(to_brief(r), encoding="utf-8")
    written.append(p)
    return written
