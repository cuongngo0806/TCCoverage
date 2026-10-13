"""Markdown / JSON / brief renderers (FR-008), in the report language (``report_language``: vi default, en)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tcadvisor.classify.environment import AI_CLOSED, action
from tcadvisor.report.l10n import Translator, localize
from tcadvisor.report.scenarios import build as build_scenarios, case_scenario, localize_scenarios, top_checks

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
AI_REPORT = "report.ai-verified"  # .md / .html: the cases an AI closed (main report: the cases to test for real)
AI_VERDICT_LABEL = {"confirmed": "confirmed: needs a real test", "needs_info": "needs more information",
                    "not_needed": "no real test needed", "weak": "no real test needed",
                    "pass_by_review": "closed by code review"}


def split(r: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(main, ai_closed) copies of report ``r``: the main one lists the cases that still need a real test (plus
    ``ai_closed``: how many went to the other); the other lists the cases an AI closed (`not_needed`,
    `pass_by_review`). report.json keeps every case."""
    cases = r["test_case_candidates"]
    closed = [c for c in cases if action(c) in AI_CLOSED]
    main = [c for c in cases if action(c) not in AI_CLOSED]
    return ({**r, "test_case_candidates": main, "ai_closed": len(closed) + r.get("ai_closed", 0)},
            {**r, "test_case_candidates": closed, "report_part": "ai_closed"})


def sub_label(sub: str | None, T: Translator) -> str:
    return T(sub.replace("_", " ")) if sub else ""


def case_labels(r: dict[str, Any], T: Translator) -> None:
    """Translated display labels (sub-reason tag, AI verdict) on the cases of a localized copy ``r`` (HTML)."""
    cases = []
    for c in r["test_case_candidates"]:
        c = {**c, "sub_label": sub_label(c.get("sub_reason"), T)}
        if c.get("verification"):
            c["verification"] = {**c["verification"],
                                 "label": T.ui(AI_VERDICT_LABEL.get(c["verification"]["verdict"], "needs more information"))}
        cases.append(c)
    r["test_case_candidates"] = cases


def _ev_label(ev: dict[str, Any]) -> str:
    if "qualified_name" in ev:
        return f"`{ev['qualified_name']}` ({ev['file_path']}:{ev['line']})"
    loc = ev["source_location"]
    return f"{ev['from_symbol']['qualified_name']} —{ev['relation']}→ {ev['to_symbol']['qualified_name']} " \
           f"({loc['file_path']}:{loc['line']})"


def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def translator(r: dict[str, Any]) -> Translator:
    """Reports written before the report language existed are English."""
    return Translator(r.get("report_language", "en"))


def _targets(ts: list[str], T: Translator, limit: int = 6) -> str:
    more = T.ui(" (+{n} more)", n=len(ts) - limit) if len(ts) > limit else ""
    return (", ".join(ts[:limit]) + more) if ts else T.ui("-")


def summary_line(r: dict[str, Any]) -> str:
    T = translator(r)
    cases = r["test_case_candidates"]
    by = {p: sum(1 for c in cases if c["priority"] == p) for p in PRIO_ORDER}
    llm = T.ui("degraded (LLM unavailable)") if r["llm_degraded"] else T.ui("enabled") if r["llm_enabled"] \
        else T.ui("disabled")
    if r.get("no_detected_impact"):
        head = T.ui("No detected impact")
    else:
        head = T.ui("{n} test case(s) [P1 {p1} / P2 {p2} / P3 {p3}]", n=len(cases), p1=by["P1"], p2=by["P2"], p3=by["P3"])
    return T.ui("{head}; {flags} uncertainty flag(s); {tests}{files} changed file(s); targets: {targets}; "
                "cache_hit: {cache}; LLM: {llm}; {secs}s", head=head, flags=len(r["uncertainty_flags"]),
                tests=_test_summary(r, T), files=len(r.get("changed_files", [])),
                targets=_targets(r["target_scope"], T), cache=T.ui(str(r["cache_hit"]).lower()), llm=llm,
                secs=r.get("metrics", {}).get("duration_seconds", 0))


ACTION_LABEL = {"test_on_target": "Test on target", "review": "Review code",
                "closed_by_review": "Closed by code review", "not_needed": "No real test needed (AI)"}
ACTION_TAG = {"test_on_target": "TARGET", "review": "REVIEW", "closed_by_review": "CLOSED", "not_needed": "CLOSED"}


def plan_line(r: dict[str, Any]) -> str:
    n = {a: 0 for a in ACTION_LABEL}
    for c in r["test_case_candidates"]:
        n[action(c)] += 1
    closed = n["closed_by_review"] + n["not_needed"] + r.get("ai_closed", 0)
    return translator(r).ui("Test plan: {target} to test on target, {review} to review (code reading may close "
                            "them), {closed} closed by AI (listed in {ai_report}.md)", target=n["test_on_target"],
                            review=n["review"], closed=closed, ai_report=AI_REPORT)


def _mermaid_id(i: int) -> str:
    return f"n{i}"


def mermaid(r: dict[str, Any], T: Translator | None = None) -> str:
    T = T or Translator()
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
        out.append(f"  more[\"{T.ui('+{n} more nodes (see report.html)', n=len(r['impact_nodes']) - MERMAID_MAX_NODES)}\"]")
    return "\n".join(out)


def _test_summary(r: dict[str, Any], T: Translator) -> str:
    """'test results: …; ' when the report carries tester results (spec 006), else ''."""
    if not r.get("test_results"):
        return ""
    from tcadvisor.report.results import summary
    s = summary(r["test_results"], [c["key"] for c in r["test_case_candidates"]])
    recheck = T.ui(" / {n} re-check", n=s["needs_recheck"]) if s["needs_recheck"] else ""
    return T.ui("test results: {ok} pass / {bad} fail / {nt} n/t / {no} n/o / {untested} untested{recheck}; ",
                ok=s["pass"], bad=s["fail"], nt=s["not_testable"], no=s["cannot_occur"], untested=s["untested"],
                recheck=recheck)


def _verdict_tag(c: dict[str, Any], T: Translator) -> str:
    tr = c.get("test_result")
    if tr is None:
        return ""
    from tcadvisor.report.results import VERDICT_LABEL
    return f" [{T.ui(VERDICT_LABEL.get(tr.get('verdict'), '—'))}]" + (T.ui(" (re-check)") if tr.get("needs_recheck") else "")


REL_LABEL = {"call": "calls", "contains": "member of", "include": "includes", "inherit_override": "derives / overrides",
             "uses_type": "uses the type", "instantiate": "instantiates", "macro_expand": "expands the macro"}
SCENARIO_CHECKS = 6
MERMAID_MAX_SCENARIOS = 12


def scenarios_of(r: dict[str, Any]) -> list[dict[str, Any]]:
    """Test scenarios (spec 013) of the cases of report part ``r`` (English text)."""
    return build_scenarios(r["test_case_candidates"], r.get("impact_nodes"))


def _short(name: str, n: int = 48) -> str:
    """Drop leading namespaces / classes until ``name`` fits (``rca::A::f`` -> ``A::f``)."""
    parts = name.split("::")
    while len("::".join(parts)) > n and len(parts) > 1:
        parts = parts[1:]
    out = "::".join(parts)
    return out if len(out) <= n else "…" + out[-(n - 1):]


def scenario_flow(s: dict[str, Any], T: Translator, md: bool = True) -> str:
    """``a`` (file:line) → ``b`` → ``c`` *(changed)* — the steps of a flow, or representative ⇢ dependency."""
    q = (lambda x: f"`{x}`") if md else (lambda x: x)
    st = s["steps"]
    first = st[0]["symbol"]
    where = f" ({first['file_path']}:{first['line']})" if md and first.get("file_path") else ""
    changed = T.ui(" *(changed)*") if md else "*"
    if s["kind"] == "group":
        dep = st[-1]["symbol"]["qualified_name"]
        return (q(first["qualified_name"]) + where + f" ⇢ {T.ui(REL_LABEL.get(s['relation'], s['relation']))} ⇢ "
                + q(dep) + (changed if st[-1]["changed"] else ""))
    parts = [q(x["symbol"]["qualified_name"]) + (where if i == 0 else "") + (changed if x["changed"] else "")
             for i, x in enumerate(st)]
    return " → ".join(parts)


def scenario_labels(sc: list[dict[str, Any]], T: Translator) -> list[dict[str, Any]]:
    """Scenarios for the HTML page: checks in the report language plus display labels (reason, relation)."""
    return [{**s, "why": _scenario_why(s, T), "relation_label": T.ui(REL_LABEL.get(s["relation"], s["relation"]))}
            for s in localize_scenarios(sc, T)]


def _scenario_why(s: dict[str, Any], T: Translator) -> str:
    groups = ", ".join(T.ui(GROUP_LABEL[g]) for g in s["risk_groups"] if g in GROUP_LABEL)
    subs = ", ".join(sub_label(x, T) for x in s["sub_reasons"])
    return groups + (f" ({subs})" if subs else "")


def scenarios_mermaid(sc: list[dict[str, Any]], T: Translator) -> str:
    out = ["flowchart LR"]
    for s in sc[:MERMAID_MAX_SCENARIOS]:
        sid = s["id"].lower()
        out.append(f'  subgraph {sid}["{s["id"]} · {s["priority"]} · {T.ui(ACTION_LABEL[s["action"]])}"]')
        out.append("    direction LR")
        ids = []
        for i, x in enumerate(s["steps"]):
            label = re.sub(r'["<>\[\]{}|]', "", _short(x["symbol"]["qualified_name"], 40))
            if s["kind"] == "group" and i == 0 and len(s["members"]) > 1:
                label += f" +{len(s['members']) - 1}"
            out.append(f'    {sid}_{i}["{label}"]' + (":::chg" if x["changed"] else ""))
            ids.append(f"{sid}_{i}")
        if len(ids) > 1:
            arrow = f" -. {T.ui(REL_LABEL.get(s['relation'], s['relation']))} .-> " if s["kind"] == "group" else " --> "
            out.append("    " + arrow.join(ids))
        out.append("  end")
    out.append("  classDef chg fill:#fde2e1,stroke:#c0392b,color:#000")
    return "\n".join(out)


def scenarios_markdown(sc: list[dict[str, Any]], r: dict[str, Any], T: Translator) -> list[str]:
    """The test plan: one runnable test per scenario, with the cases it covers and what to check."""
    n_cases = sum(len(s["cases"]) for s in sc)
    L = [T.ui("{n} scenario(s) cover {m} case(s): run one test per scenario, entering at the first function of its "
              "flow; the changed code is marked *(changed)*.", n=len(sc), m=n_cases), "",
         "```mermaid", scenarios_mermaid(sc, T), "```", ""]
    if len(sc) > MERMAID_MAX_SCENARIOS:
        L += [T.ui("(diagram: first {n} scenarios)", n=MERMAID_MAX_SCENARIOS), ""]
    for s in sc:
        L += [T.ui("### {id} · {prio} · {action} · {n} case(s)", id=s["id"], prio=s["priority"],
                   action=T.ui(ACTION_LABEL[s["action"]]), n=len(s["cases"])), "",
              T.ui("- [ ] **Run**: {flow}", flow=_md_cell(scenario_flow(s, T)))]
        if s["kind"] == "group" and len(s["members"]) > 1:
            names = [f"`{m['qualified_name']}`" for m in s["members"][:6]]
            more = T.ui(" (+{n} more)", n=len(s["members"]) - 6) if len(s["members"]) > 6 else ""
            L.append(T.ui("- **Stands for**: {n} symbol(s) with the same link to the change: {names}",
                          n=len(s["members"]), names=", ".join(names) + more))
        L.append(T.ui("- **Covers**: {cases} — {why}", cases=", ".join(s["cases"]), why=_scenario_why(s, T)))
        shown = top_checks(s, SCENARIO_CHECKS)
        if shown:
            L.append(T.ui("- **Check**:"))
            L += [f"  - [ ] {_md_cell(k['text'])}" + (" *(AI)*" if k["source"] == "ai" else "") for k in shown]
            if len(s["checks"]) > len(shown):
                L.append(T.ui("  - … {n} more check(s) under the covered cases", n=len(s["checks"]) - len(shown)))
        L.append("")
    return L


def to_markdown(r: dict[str, Any]) -> str:
    """The main report: the cases that still need a real test (AI-closed ones: :func:`to_ai_markdown`)."""
    T = translator(r)
    summary, plan = summary_line(r), plan_line(r)
    main = split(r)[0]
    sc = localize_scenarios(scenarios_of(main), T)
    r = localize(main, T)
    L: list[str] = [T.ui("# Change Impact & Test Case Report"), ""]
    ci = r["change_input"]
    src = ci.get("commit_range") or (T.ui("working tree") if ci.get("working_tree") else
                                     ", ".join(ci.get("symbols_requested") or []))
    L += [T.ui("- **Change**: {mode} — {src}", mode=ci["mode"], src=src),
          T.ui("- **Repository**: `{repo}`", repo=ci["target_repo_path"]), T.ui("- **Summary**: {s}", s=summary), ""]
    if sc:
        L += [T.ui("## Test scenarios — what to test now"), "", plan + ".", ""] + scenarios_markdown(sc, r, T)
    if r.get("no_detected_impact"):
        L += [T.ui("> **No detected impact.** The change touches no indexed symbol semantically (e.g. comments, "
                   "whitespace or non-C++ files only). This is a positive result, not a tool failure."), ""]
    if r.get("changed_symbols"):
        L += [T.ui("## Changed symbols"), "", T.ui("| Symbol | Change | Risk groups |"), "|---|---|---|"]
        for s in r["changed_symbols"]:
            groups = ", ".join(sorted({T.ui(GROUP_LABEL[x['risk_group']]) + (f" ({sub_label(x['sub_reason'], T)})" if x['sub_reason'] else "")
                                       for x in s["risks"]}))
            L.append(f"| `{_md_cell(s['symbol']['qualified_name'])}` {s['symbol']['file_path']}:{s['symbol']['line']} "
                     f"| {T.ui(s['change_kind'])} | {groups} |")
        L.append("")
    if r.get("impact_nodes"):
        L += [T.ui("## Impact flow"), "", T.ui("Arrows point from the affected code to what it depends on "
                                               "(red = changed, orange = direct, blue = indirect)."),
              "", "```mermaid", mermaid(r, T), "```", ""]
    cases = r["test_case_candidates"]
    if cases:
        L += [T.ui("## Test case details"), "",
              T.ui("The evidence behind each scenario, one entry per case (`[S<n>]` = the scenario that covers it)."),
              "",
              T.ui("- **Test on target**: the risk only shows up when running on the device (concurrency, lifetime, "
                   "data layout, build configuration, hardware / interrupt / timing / RTOS / bus code), or an AI "
                   "reviewer read the code and could not close it."),
              T.ui("- **Review code**: no runtime signal — reading the code may close it without a run "
                   "(`tcadvisor verify --scope review`); test it on the target if nobody can."),
              T.ui("- **Closed by AI**: an AI reviewer proved from the code that the case cannot fail, or judged that "
                   "no real test is needed (a build settles it); these cases are listed in {ai_report}.md / .html "
                   "with the AI's reason, so the decision stays auditable.", ai_report=AI_REPORT), "",
              T.ui("Inside each group: relevance order (closest to the change, substantive before recompile-only, "
                   "larger changes first); the P1/P2/P3 label is the deterministic priority."), ""]
        L += _md_groups(cases, T, case_scenario(sc))
    elif r.get("ai_closed"):
        L += [T.ui("## Test cases to check"), "", plan + ".", ""]
    L += _md_ai_section(r, T)
    if r.get("existing_tests"):
        L += [T.ui("## Existing tests to re-run"), "",
              "`--gtest_filter=" + ":".join(t["test"] for t in r["existing_tests"]) + "`", ""]
        L += [T.ui("- `{test}` ({file}:{line}, hop {hop})", test=t["test"], file=t["file_path"], line=t["line"],
                   hop=t["hop_distance"]) for t in r["existing_tests"]]
        L.append("")
    if r.get("test_gaps"):
        L += [T.ui("## Test gaps (no existing test reaches the change)"), ""]
        L += [T.ui("- [ ] `{sym}` ({file}:{line}) — {reason}: a new test is likely needed",
                   sym=g["symbol"]["qualified_name"], file=g["symbol"]["file_path"], line=g["symbol"]["line"],
                   reason=g["reason"]) for g in r["test_gaps"]]
        L.append("")
    ts = r.get("trigger_sources") or []
    for t in [t for t in ts if t.get("reason", "guarded") == "guarded"]:
        L += [T.ui("## Trigger sources of `{sym}`", sym=t["target"]["qualified_name"]), "",
              T.ui("Guard added in {where}: `{guard}`", where=", ".join(f"`{c}`" for c in t["covered_by"]),
                   guard=_md_cell("; ".join(t["guard"]))), "",
              T.ui("| Source | Kind | Guard | |"), "|---|---|---|---|"]
        for x in t["sources"]:
            sym = x["symbol"]
            kind = (T.ui("callback registered at {file}:{line}", file=x["registered_at"][0], line=x["registered_at"][1])
                    if x["registered_at"] else T.ui("call"))
            L.append(f"| `{sym['qualified_name']}` {sym['file_path']}:{x['call_line']} | {kind} | {x['guard']} | "
                     f"{T.ui('covered by this change') if x['covered_by_change'] else T.ui('check (see cases)')} |")
        L.append("")
    changed = [t for t in ts if t.get("reason") == "changed"]
    if changed:
        L += [T.ui("## Where each changed function is triggered from"), "",
              T.ui("Every source should be exercised: a fix verified from one source only is the classic miss."), "",
              T.ui("| Changed function | Source (caller) | Entry points behind it |"), "|---|---|---|"]
        for t in changed:
            for x in t["sources"]:
                sym = x["symbol"]
                kind = (T.ui(" (callback registered at {file}:{line})", file=x["registered_at"][0],
                             line=x["registered_at"][1]) if x["registered_at"] else "")
                L.append(f"| `{t['target']['qualified_name']}` | `{sym['qualified_name']}` {sym['file_path']}:"
                         f"{x['call_line']}{kind} | {', '.join(f'`{e}`' for e in x.get('entries') or []) or '-'} |")
            if t.get("total", 0) > len(t["sources"]):
                L.append(f"| `{t['target']['qualified_name']}` | " + T.ui("… {n} more", n=t["total"] - len(t["sources"]))
                         + " | |")
        L.append("")
    if r["uncertainty_flags"]:
        L += [T.ui("## Uncertain — needs manual review"), "", T.ui("| Category | Symbol | Reason |"), "|---|---|---|"]
        for f in r["uncertainty_flags"]:
            sym = f["related_symbol"]
            where = f"`{sym['qualified_name']}` {sym['file_path']}:{sym['line']}" if sym else "-"
            L.append(f"| {f['category']} | {_md_cell(where)} | {_md_cell(f['reason'])} |")
        L.append("")
    if r.get("affected_targets"):
        L += [T.ui("## Build / test scope to rerun"), ""]
        for t in r["affected_targets"]:
            via = T.ui(" (links {via})", via=t["via"]) if t.get("via") else ""
            L.append(f"- `{t['name']}` — {t['relation']}{via}")
        L.append("")
    if r.get("out_of_scope"):
        L += [T.ui("## Skipped (out of scope)"), ""]
        for o in r["out_of_scope"]:
            L.append(f"- `{o['path']}`{' `' + o['symbol'] + '`' if o.get('symbol') else ''}: {o['reason']}")
        L.append("")
    if r.get("not_built") or r.get("not_built_changes"):
        L += not_built_markdown(r, T)
    if r.get("run_notes"):
        L += [T.ui("## Run notes"), ""] + [f"- {n}" for n in r["run_notes"]] + [""]
    m = r.get("metrics", {})
    L += [T.ui("## Metrics"), "", f"- run_id: `{r['run_id']}`", T.ui("- duration: {s}s", s=m.get("duration_seconds")),
          f"- cache_hit: {r['cache_hit']}", f"- index: {m.get('index')}",
          f"- LLM: enabled={r['llm_enabled']} degraded={r['llm_degraded']} tokens={r['llm_token_usage']}", ""]
    return "\n".join(L)


def _md_groups(cases: list[dict[str, Any]], T: Translator, owner: dict[str, str] | None = None) -> list[str]:
    L: list[str] = []
    hops = (("changed code", lambda c: c["hop_distance"] == 0), ("direct impact", lambda c: c["hop_distance"] == 1),
            ("indirect impact", lambda c: c["hop_distance"] > 1))
    for a, label in ACTION_LABEL.items():
        in_a = [c for c in cases if action(c) == a]
        if in_a:
            L += [f"### {T.ui(label)} ({len(in_a)})", ""]
        for title, sel in hops:
            group = [c for c in in_a if sel(c)]
            if not group:
                continue
            L += [f"#### {T.ui(label)} — {T.ui(title)} ({len(group)})", ""]
            for c in group:
                L += _md_case(c, T, (owner or {}).get(c["id"]))
            L.append("")
    return L


def _md_ai_section(r: dict[str, Any], T: Translator) -> list[str]:
    av = r.get("ai_verification")
    if not av:
        return []
    L = [T.ui("## AI verification"), "", f"{_md_cell(av['summary'])}", "",
         T.ui("- verified cases: {n}; models: {models}", n=av["verified_cases"],
              models=", ".join(av.get("models") or []) or "-")]
    for a in av["additional_checks"]:
        ev = f" ({a['evidence']})" if a["evidence"] else T.ui(" (unverified AI suggestion: no resolvable file:line)")
        L.append(T.ui("- [ ] **Also check** (AI): {title} — {why}{ev}", title=_md_cell(a["title"]),
                      why=_md_cell(a["why"]), ev=ev))
    return L + [""]


def to_ai_markdown(r: dict[str, Any]) -> str:
    """``report.ai-verified.md``: the cases an AI closed, each with its reason (and proof), kept out of the main
    report so that one lists only what needs a real test."""
    T = translator(r)
    summary = summary_line(r)
    closed_en = split(r)[1]
    sc = localize_scenarios(scenarios_of(closed_en), T)
    closed = localize(closed_en, T)
    ci = closed["change_input"]
    src = ci.get("commit_range") or (T.ui("working tree") if ci.get("working_tree") else
                                     ", ".join(ci.get("symbols_requested") or []))
    L = [T.ui("# Cases closed by AI (no real test needed)"), "",
         T.ui("- **Change**: {mode} — {src}", mode=ci["mode"], src=src),
         T.ui("- **Repository**: `{repo}`", repo=ci["target_repo_path"]), T.ui("- **Summary**: {s}", s=summary), "",
         T.ui("An AI reviewer closed these {n} case(s): it proved from the code that they cannot fail, or judged that "
              "no real test is needed (its reason is under each case). They are not in report.md / report.html; "
              "re-open one by testing it if you disagree.", n=len(closed["test_case_candidates"])), ""]
    if sc:
        L += [T.ui("## Test scenarios of these cases"), ""] + scenarios_markdown(sc, closed, T)
        L += [T.ui("## Test case details"), ""]
    L += _md_groups(closed["test_case_candidates"], T, case_scenario(sc))
    return "\n".join(L + _md_ai_section(closed, T))


def _md_case(c: dict[str, Any], T: Translator, scenario: str | None = None) -> list[str]:
    tr = c.get("test_result") or {}
    box = "x" if tr.get("verdict") and not tr.get("needs_recheck") else " "
    L = [f"- [{box}] **{c['id']}**{f' [{scenario}]' if scenario else ''} {c['priority']} [{T.ui(GROUP_LABEL[c['risk_group']])}] "
         f"{_md_cell(c['description'])}{_verdict_tag(c, T)}",
         T.ui("  - *When*: {text}", text=_md_cell(c["activation_condition"])),
         T.ui("  - *Evidence*: {text}", text="; ".join(_ev_label(e) for e in c["evidence"]))]
    if c.get("path"):
        L.append(T.ui("  - *Path*: {text}", text=" → ".join(
            f"`{x['symbol']['qualified_name']}` ({x['role']}{T.ui(', checked') if x['checked'] else ''})"
            for x in c["path"])))
    if c.get("corner_cases"):
        L.append(T.ui("  - *Corner cases*: {text}", text="; ".join(c["corner_cases"][:5])))
    L.append(T.ui("  - *Targets*: {text}", text=", ".join(c["related_cmake_targets"])))
    if c.get("target_reasons"):
        L.append(T.ui("  - *Needs the target*: {text}", text="; ".join(_md_cell(x) for x in c["target_reasons"])))
    if tr.get("verdict"):
        names = ", ".join(a["name"] for a in tr.get("attachments", []))
        L.append(T.ui("  - *Test result*: {verdict} by {tester} on {date}", verdict=tr["verdict"],
                      tester=_md_cell(tr.get("tester", "")), date=tr.get("date", ""))
                 + (" — " + _md_cell(tr["comment"]) if tr.get("comment") else "")
                 + (T.ui("; defect {ref}", ref=_md_cell(tr["defect_ref"])) if tr.get("defect_ref") else "")
                 + (T.ui("; evidence: {names}", names=_md_cell(names)) if names else ""))
    v = c.get("verification")
    if v:
        L.append(T.ui("  - *AI verification*: **{verdict}**", verdict=T.ui(AI_VERDICT_LABEL.get(v["verdict"], v["verdict"])))
                 + (T.ui(" — re-check") if v["recheck"] else "") + (": " + _md_cell(v["note"]) if v["note"] else ""))
        if v.get("proof"):
            L.append(T.ui("  - *Proof*: {text}", text=", ".join(v["proof"])))
        if v["extra_corner_cases"]:
            L.append(T.ui("  - *AI corner cases*: {text}", text="; ".join(_md_cell(x) for x in v["extra_corner_cases"])))
    return L


EXCLUSION_LABEL = {"source_not_in_product": "source of no product built in this variant",
                   "source_not_in_compile_db": "not compiled in this variant's build",
                   "conditional_dir": "directory not built in this variant", "preprocessor": "inactive branch"}


def _ev_loc(c: dict[str, Any]) -> str:
    ev = c["evidence"][0]
    loc = ev.get("source_location") or ev
    return f"{loc.get('file_path')}:{loc.get('line')}"


def exclusion_text(xs: list[dict[str, Any]], T: Translator) -> str:
    return "; ".join(f"{x['variant']}: {x.get('condition') or T.ui(EXCLUSION_LABEL.get(x['reason'], x['reason']))}"
                     + (f" ({x['where']})" if x.get("where") else "") for x in xs)


def not_built_markdown(r: dict[str, Any], T: Translator) -> list[str]:
    bp = r.get("build_profile") or {}
    L = [T.ui("## Not built in the confirmed variants"), "",
         T.ui("Build profile: {state}; variants: {variants}. These cases concern code that no selected variant "
              "compiles; they are listed here, not deleted (`--no-variant-filter` shows them in the main list).",
              state=T.ui(bp.get("state", "confirmed")), variants=", ".join(bp.get("variants") or []) or "-"), ""]
    for n in r.get("not_built") or []:
        c = n["case"]
        L.append(f"- {c['id']} {c['priority']} `{_ev_loc(c)}` {c['description']} — {exclusion_text(n['excluded_by'], T)}")
    for n in r.get("not_built_changes") or []:
        sym = f" `{n['symbol']}`" if n.get("symbol") else ""
        L.append(T.ui("- changed `{path}`{sym}: {why}", path=n["path"], sym=sym,
                      why=exclusion_text(n["excluded_by"], T)))
    return L + [""]


def to_brief(r: dict[str, Any], limit: int = 80) -> str:
    """Token-lean summary meant for an AI assistant (Claude) or a PR comment. Line tags (CHANGED, UNCERTAIN, ...)
    stay English in every language: they are markers for tools and AI readers."""
    T = translator(r)
    L = [summary_line(r), plan_line(r)]
    main = split(r)[0]
    sc = localize_scenarios(scenarios_of(main), T)
    owner = case_scenario(sc)
    r = localize(main, T)
    for s in sc[:limit]:
        more = f" (+{len(s['members']) - 1})" if s["kind"] == "group" and len(s["members"]) > 1 else ""
        L.append(f"SCENARIO {s['id']} {s['priority']} {ACTION_TAG[s['action']]} {scenario_flow(s, T, md=False)}{more} :: "
                 + ",".join(s["cases"]))
        shown = top_checks(s, 4)
        if shown:
            L.append("   check: " + " | ".join(k["text"] for k in shown)
                     + (f" | +{len(s['checks']) - len(shown)}" if len(s["checks"]) > len(shown) else ""))
    for s in r.get("changed_symbols", []):
        L.append(f"CHANGED {s['symbol']['qualified_name']} @{s['symbol']['file_path']}:{s['symbol']['line']} "
                 f"[{','.join(sorted({x['risk_group'] for x in s['risks']}))}]")
    for c in r["test_case_candidates"][:limit]:
        ev = c["evidence"][0]
        v = c.get("verification")
        tag = f" [AI:{v['verdict']}]" if v else ""
        sid = f" [{owner[c['id']]}]" if c["id"] in owner else ""
        L.append(f"{c['id']}{sid} {c['priority']} {ACTION_TAG[action(c)]} {c['risk_group']} {ev['file_path']}:{ev['line']}{tag} :: "
                 f"{c['description']}{_verdict_tag(c, T)}")
        if c.get("target_reasons"):
            L.append("   target: " + " | ".join(c["target_reasons"][:2]))
        if c.get("corner_cases") and not sid:  # a scenario's check line already carries them
            L.append("   corner: " + " | ".join(c["corner_cases"][:3]))
    if len(r["test_case_candidates"]) > limit:
        L.append(T.ui("... {n} more in report.json", n=len(r["test_case_candidates"]) - limit))
    if r.get("ai_closed"):
        L.append(f"AI-CLOSED {r['ai_closed']} :: {AI_REPORT}.md")
    ts_brief = [t for t in r.get("trigger_sources") or [] if t.get("reason", "guarded") == "guarded"] + [
        t for t in r.get("trigger_sources") or [] if t.get("reason") == "changed" and t.get("total", 0) >= 2][:10]
    for t in ts_brief:
        L.append(f"SOURCES {t['target']['qualified_name']} :: " + ", ".join(
            f"{x['symbol']['qualified_name']} ({T.ui('covered') if x['covered_by_change'] else T.ui('guard') + ' ' + x['guard']})"
            if t.get("reason", "guarded") == "guarded" else x["symbol"]["qualified_name"]
            for x in t["sources"]))
    bp = r.get("build_profile") or {}
    if bp.get("filtering"):
        L.append(f"PROFILE {bp.get('state')} {','.join(bp.get('variants') or [])} :: "
                 + T.ui("not built (profile): {n}", n=len(r.get("not_built") or [])))
    for n in (r.get("not_built") or [])[:20]:
        c = n["case"]
        L.append(f"NOT-BUILT {c['id']} {_ev_loc(c)} :: {exclusion_text(n['excluded_by'], T)}")
    for f in r["uncertainty_flags"]:
        sym = f["related_symbol"]
        L.append(f"UNCERTAIN {f['category']} {sym['qualified_name'] if sym else '-'} :: {f['reason']}")
    for g in r.get("test_gaps") or []:
        L.append(f"TEST-GAP {g['symbol']['qualified_name']} @{g['symbol']['file_path']}:{g['symbol']['line']} "
                 f"({g['reason']})")
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
        data = {k: v for k, v in _without_attachment_data(r).items() if k != "l10n"}
        data["test_scenarios"] = scenarios_of(split(r)[0])  # spec 013: the cases still to test, as runnable tests
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(p)
    if fmt in ("md", "both", "all"):
        p = out_dir / "report.md"
        p.write_text(to_markdown(r), encoding="utf-8")
        written.append(p)
    if fmt in ("html", "both", "all"):
        p = out_dir / "report.html"
        p.write_text(to_html(r), encoding="utf-8")
        written.append(p)
    has_closed = bool(split(r)[1]["test_case_candidates"])
    for ext, render in (("md", to_ai_markdown), ("html", lambda x: to_html(x, "ai_closed"))):
        p = out_dir / f"{AI_REPORT}.{ext}"
        if has_closed and fmt in (ext, "both" if ext == "md" else "", "all"):
            p.write_text(render(r), encoding="utf-8")
            written.append(p)
        elif not has_closed and p.is_file():
            p.unlink()  # from an earlier verification of another analysis
    p = out_dir / "report.brief.txt"
    p.write_text(to_brief(r), encoding="utf-8")
    written.append(p)
    return written
