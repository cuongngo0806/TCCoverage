"""Spec 013: cases grouped into runnable test scenarios."""
from tcadvisor.report.scenarios import build, case_scenario, top_checks


def _s(name, line=1, kind="function"):
    return {"qualified_name": name, "kind": kind, "file_path": "a.cpp", "line": line}


def _node(name, hop, calls=(), rel="call"):
    return {"id": f"n:{name}", "symbol": _s(name), "hop_distance": hop,
            "edges": [{"relation": rel, "from_symbol": _s(name), "to_symbol": _s(t),
                       "source_location": {"file_path": "a.cpp", "line": 10}} for t in calls]}


def _case(cid, name, hop, to=None, rel="call", prio="P2", corners=(), group="logic", ai=()):
    ev = [_s(name)] + ([{"relation": rel, "from_symbol": _s(name), "to_symbol": _s(to),
                         "source_location": {"file_path": "a.cpp", "line": 10}}] if to else [])
    c = {"id": cid, "key": cid.lower(), "description": cid, "evidence": ev, "priority": prio, "risk_group": group,
         "hop_distance": hop, "node_id": f"n:{name}", "corner_cases": list(corners), "verify_by": "target"}
    if ai:
        c["verification"] = {"verdict": "confirmed", "extra_corner_cases": list(ai), "note": "", "recheck": False}
    return c


GUARD = "Removed condition `x`: make `x` hold"
GENERIC = "Exercise every branch whose condition changed (true and false paths)"


def test_call_chain_is_one_scenario_with_checks_once():
    nodes = [_node("c", 0), _node("b", 1, ["c"]), _node("a", 2, ["b"])]
    cases = [_case("TC-1", "c", 0, prio="P1", corners=[GUARD, GENERIC]),
             _case("TC-2", "b", 1, "c", corners=[GUARD, GENERIC]),
             _case("TC-3", "a", 2, "b", prio="P3", corners=[GUARD, GENERIC])]
    sc = build(cases, nodes)
    assert len(sc) == 1
    s = sc[0]
    assert [x["symbol"]["qualified_name"] for x in s["steps"]] == ["a", "b", "c"]
    assert s["steps"][-1]["changed"] and s["priority"] == "P1" and s["action"] == "test_on_target"
    assert sorted(s["cases"]) == ["TC-1", "TC-2", "TC-3"]
    assert [k["text"] for k in s["checks"]] == [GUARD]  # de-duplicated, generic dropped next to a concrete one


def test_two_callers_two_scenarios_root_covered_once():
    nodes = [_node("c", 0), _node("x", 1, ["c"]), _node("y", 1, ["c"])]
    cases = [_case("TC-1", "c", 0), _case("TC-2", "x", 1, "c"), _case("TC-3", "y", 1, "c")]
    sc = build(cases, nodes)
    assert len(sc) == 2
    owner = case_scenario(sc)
    assert set(owner) == {"TC-1", "TC-2", "TC-3"} and sum(s["cases"].count("TC-1") for s in sc) == 1
    assert all(s["steps"][-1]["symbol"]["qualified_name"] == "c" for s in sc)


def test_non_call_relation_forms_one_group():
    nodes = [_node("K", 0)] + [_node(f"K::m{i}", 1, ["K"], rel="contains") for i in range(5)]
    cases = [_case("TC-0", "K", 0, prio="P1")] + [
        _case(f"TC-{i + 1}", f"K::m{i}", 1, "K", rel="contains", group="abi_layout" if i % 2 else "logic",
              prio="P1" if i == 3 else "P2") for i in range(5)]
    sc = build(cases, nodes)
    groups = [s for s in sc if s["kind"] == "group"]
    assert len(sc) == 2 and len(groups) == 1
    g = groups[0]
    assert g["relation"] == "contains" and len(g["cases"]) == 5 and len(g["members"]) == 5
    assert g["entry"]["qualified_name"] == "K::m3"  # representative: best priority


def test_every_case_once_deterministic_and_ai_first():
    nodes = [_node("c", 0), _node("d", 0), _node("b", 1, ["c", "d"]), _node("a", 2, ["b"])]
    cases = [_case("TC-1", "c", 0, corners=["r1"]), _case("TC-2", "d", 0, prio="P1", corners=["r2"]),
             _case("TC-3", "b", 1, "c", ai=["ai1"]), _case("TC-4", "a", 2, "b"),
             {**_case("TC-5", "lonely", 0), "node_id": "", "evidence": [_s("lonely")]}]
    sc = build(cases, nodes)
    assert sc == build(cases, nodes)
    ids = [i for s in sc for i in s["cases"]]
    assert sorted(ids) == ["TC-1", "TC-2", "TC-3", "TC-4", "TC-5"] and len(ids) == 5
    first = sc[0]
    assert first["priority"] == "P1" and first["steps"][-1]["symbol"]["qualified_name"] == "d"
    assert [s["id"] for s in sc] == [f"S{i}" for i in range(1, len(sc) + 1)]
    s_c = next(s for s in sc if "TC-3" in s["cases"])
    assert s_c["checks"][0] == {"text": "ai1", "source": "ai"}


def test_top_checks_keeps_rule_checks_next_to_many_ai():
    s = {"checks": [{"text": f"a{i}", "source": "ai"} for i in range(8)] + [{"text": "r", "source": "rule"}]}
    shown = top_checks(s, 6)
    assert len(shown) == 6 and shown[-1]["text"] == "r"


def _report(cases, nodes, lang="en"):
    return {"change_input": {"mode": "git_diff", "target_repo_path": "/r", "commit_range": "A..B"},
            "test_case_candidates": cases, "impact_nodes": nodes, "changed_symbols": [], "uncertainty_flags": [],
            "target_scope": [], "cache_hit": False, "llm_enabled": False, "llm_degraded": False,
            "llm_token_usage": None, "run_id": "x", "metrics": {}, "report_language": lang}


def test_renderers_show_scenarios_first(tmp_path):
    import json
    from tcadvisor.report.render import to_brief, to_markdown, write_outputs
    nodes = [_node("c", 0), _node("b", 1, ["c"])]
    cases = [{**_case("TC-1", "c", 0, prio="P1", corners=[GUARD]), "activation_condition": "x",
              "related_cmake_targets": ["t"]},
             {**_case("TC-2", "b", 1, "c", corners=[GUARD]), "activation_condition": "x", "related_cmake_targets": ["t"]}]
    r = _report(cases, nodes)
    md = to_markdown(r)
    assert md.index("## Test scenarios") < md.index("## Test case details")
    assert "- [ ] **Run**: `b` (a.cpp:1) → `c` *(changed)*" in md and md.count(GUARD) == 3  # plan once + 2 details
    assert "**TC-2** [S1]" in md and "```mermaid\nflowchart LR" in md
    brief = to_brief(r)
    assert "SCENARIO S1 P1 TARGET b → c* :: TC-2,TC-1" in brief and "corner:" not in brief
    write_outputs(r, tmp_path, "all")
    data = json.loads((tmp_path / "report.json").read_text())
    assert [s["cases"] for s in data["test_scenarios"]] == [["TC-2", "TC-1"]]
    html = (tmp_path / "report.html").read_text()
    assert '"test_scenarios"' in html and 'id="planSec"' in html
    vi = to_markdown({**r, "report_language": "vi"})
    assert "## Kịch bản test — cần test ngay" in vi and "**Chạy**" in vi and "*(đã thay đổi)*" in vi
