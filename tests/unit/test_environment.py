"""Spec 005: which cases must run on the target, which may be closed by reading code."""
from tcadvisor.classify.environment import action, assign, load_patterns
from tcadvisor.models import SymbolRef, UncertaintyFlag
from tcadvisor.models import TestCaseCandidate as Case
from tcadvisor.report.render import plan_line, split, to_ai_markdown, to_brief, to_markdown, write_outputs
from tcadvisor.verify.annotate import merge
from tcadvisor.verify.pack import build_packets

SRC = """int pure(int a) {
  return a + 1;
}
void blink() {
  *(volatile unsigned*)0x40020014 = 1u;
}
int wait_ready(int n) {
  return poll_with_timeout(n);
}
"""


def _case(name, line, group="logic", sub=None, node=None):
    sym = SymbolRef(name, "function", "a.cpp", line)
    return Case(id=f"TC-{line:04d}", description=f"check {name}", activation_condition="w",
                             evidence=[sym], priority="P1", risk_group=group, related_cmake_targets=["T"],
                             node_id=node or name, sub_reason=sub, hop_distance=0)


def test_assign_marks_runtime_cases_with_resolvable_reasons(tmp_path):
    (tmp_path / "a.cpp").write_text(SRC)
    cases = [_case("pure", 1), _case("blink", 4), _case("wait_ready", 7), _case("pure", 1, "thread_safety", "mutex"),
             _case("pure", 1, "logic", "logging"), _case("caller", 1, node="caller")]
    flag = UncertaintyFlag("dynamic_runtime_dependency", "called through a function pointer", SymbolRef("x", "function", "b.cpp", 1))
    assign(cases, tmp_path, {"blink": [("a.cpp", 5, "  *(volatile unsigned*)0x40020014 = 1u;")]},
           {"caller": {"blink"}}, [flag], load_patterns(None))
    by = [(c.verify_by, c.target_reasons) for c in cases]
    assert by[0] == ("review", [])
    assert by[1][0] == "target" and any("hardware access" in r and "a.cpp:5" in r for r in by[1][1])
    assert by[2][0] == "target" and any(r.startswith("timing") and "a.cpp:8" in r for r in by[2][1])
    assert by[3][0] == "target" and "concurrency" in by[3][1][0]
    assert by[4] == ("review", [])  # log text never needs the device by itself
    # a caller of changed hardware code inherits the reason from the changed lines
    assert by[5][0] == "target" and any(r.startswith("changed code") for r in by[5][1])


def test_project_patterns(tmp_path):
    (tmp_path / "a.cpp").write_text(SRC)
    (tmp_path / "p.json").write_text('{"own HAL": "\\\\bpoll_with_\\\\w+"}')
    c = _case("wait_ready", 7)
    assign([c], tmp_path, {}, {}, [], load_patterns(tmp_path / "p.json"))
    assert any(r.startswith("own HAL") for r in c.target_reasons)


def _report(tmp_path):
    (tmp_path / "a.cpp").write_text(SRC)
    cases = [_case("pure", 1), _case("blink", 4)]
    assign(cases, tmp_path, {}, {}, [], load_patterns(None))
    return {"change_input": {"target_repo_path": str(tmp_path), "mode": "git_diff", "commit_range": "a..b"},
            "test_case_candidates": [c.to_dict() for c in cases], "uncertainty_flags": [], "changed_symbols": [],
            "target_scope": [], "cache_hit": False, "llm_enabled": False, "llm_degraded": False,
            "llm_token_usage": None, "run_id": "r"}


def test_pass_by_review_is_gated_and_keeps_the_case(tmp_path):
    r = _report(tmp_path)
    review, target = r["test_case_candidates"]
    assert (review["verify_by"], target["verify_by"]) == ("review", "target")
    assert action(review) == "review" and action(target) == "test_on_target"
    w = merge(r, {"cases": {review["id"]: {"verdict": "pass_by_review", "note": "pure arithmetic, no change reaches it",
                                           "proof": ["a.cpp:2"]},
                            target["id"]: {"verdict": "pass_by_review", "note": "n", "proof": ["a.cpp:5"]}}})
    assert len(r["test_case_candidates"]) == 2
    assert action(review) == "closed_by_review" and review["verification"]["proof"] == ["a.cpp:2"]
    assert review["verification"]["recheck"] is False
    assert target["verification"]["verdict"] == "needs_info" and action(target) == "test_on_target" and len(w) == 1
    assert r["ai_verification"]["closed_by_review"] == 1
    assert "1 to test on target, 0 to review" in plan_line(r) and "1 closed by AI" in plan_line(r)
    md = to_markdown(r)  # the main report lists only what needs a real test
    assert review["id"] not in md and target["id"] in md and "report.ai-verified" in md
    ai = to_ai_markdown(r)
    assert "### Closed by code review (1)" in ai and "*Proof*: a.cpp:2" in ai and ai.count(review["id"]) == 1
    assert target["id"] not in ai
    brief = to_brief(r)
    assert "TARGET" in brief and review["id"] not in brief and "AI-CLOSED 1 :: report.ai-verified.md" in brief


def test_not_needed_moves_the_case_to_the_ai_report(tmp_path):
    r = _report(tmp_path)
    review, target = r["test_case_candidates"]
    w = merge(r, {"cases": {target["id"]: {"verdict": "weak", "note": "recompile only: a clean build settles it"},
                            review["id"]: {"verdict": "not_needed", "note": " "}}})
    assert target["verification"]["verdict"] == "not_needed" and action(target) == "not_needed"
    assert target["verification"]["recheck"] is False
    assert review["verification"]["verdict"] == "needs_info" and len(w) == 1  # a closing verdict needs a reason
    main, closed = split(r)
    assert [c["id"] for c in main["test_case_candidates"]] == [review["id"]] and main["ai_closed"] == 1
    assert [c["id"] for c in closed["test_case_candidates"]] == [target["id"]]
    assert len(r["test_case_candidates"]) == 2  # report.json keeps every case
    out = write_outputs({**r, "report_language": "en"}, tmp_path / "out", "all")
    names = sorted(p.name for p in out)
    assert "report.ai-verified.md" in names and "report.ai-verified.html" in names
    assert "recompile only" in (tmp_path / "out" / "report.ai-verified.md").read_text(encoding="utf-8")
    target.pop("verification")
    write_outputs(r, tmp_path / "out", "all", same_analysis=True)
    assert not (tmp_path / "out" / "report.ai-verified.md").exists()  # nothing closed any more: no stale file


def test_pass_by_review_needs_resolvable_proof(tmp_path):
    r = _report(tmp_path)
    review = r["test_case_candidates"][0]
    for proof in ([], ["a.cpp:999"], ["../x.cpp:1"]):
        merge(r, {"cases": {review["id"]: {"verdict": "pass_by_review", "note": "n", "proof": proof}}})
        assert review["verification"]["verdict"] == "needs_info" and action(review) == "test_on_target"


def test_old_reports_without_verify_by_stay_on_target(tmp_path):
    r = _report(tmp_path)
    c = r["test_case_candidates"][0]
    del c["verify_by"]
    merge(r, {"cases": {c["id"]: {"verdict": "pass_by_review", "note": "n", "proof": ["a.cpp:2"]}}})
    assert action(c) == "test_on_target"


def test_pack_review_scope(tmp_path):
    r = _report(tmp_path)
    packets, _ = build_packets(r, {"P1"}, 10, "review")
    assert [c["id"] for p in packets for c in p["cases"]] == [r["test_case_candidates"][0]["id"]]
    packets, _ = build_packets(r, {"P1"}, 10)
    assert packets[0]["cases"][0]["verify_by"] == "review" and "target_reasons" in packets[1]["cases"][0]
