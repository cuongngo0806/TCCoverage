"""Tester results block (spec 006 US3)."""
import pytest

from tcadvisor.models import UsageError
from tcadvisor.report.results import carry_over, read_results, summary, validate_record


def _rep(*cases):
    return {"tool": {"version": "x"}, "change_input": {"mode": "git_diff", "commit_range": "a..b"},
            "test_case_candidates": [{"key": k, "code_fingerprint": fp, "description": k} for k, fp in cases]}


def test_rules_match_the_form():
    ok = {"verdict": "pass", "tester": "a", "date": "2026-10-10"}
    assert validate_record(ok) == [] and validate_record({"verdict": None}) == []
    assert "tester is required" in validate_record({**ok, "tester": " "})
    assert any("justification" in x for x in validate_record({**ok, "verdict": "cannot_occur"}))
    assert validate_record({**ok, "verdict": "not_testable", "comment": "no HW"}) == []
    assert any("attachment or a defect" in x for x in validate_record({**ok, "verdict": "fail"}))
    assert validate_record({**ok, "verdict": "fail", "defect_ref": "J-1"}) == []
    assert validate_record({**ok, "verdict": "fail", "attachments": ["a"]}, {"a": {}}) == []
    assert validate_record({**ok, "verdict": "fail", "attachments": ["gone"]}, {}) != []
    assert validate_record({**ok, "verdict": "maybe"}) == ["unknown verdict 'maybe'"]


def test_summary_counts_and_completeness():
    block = {"results": {"k1": {"verdict": "pass", "tester": "a", "date": "2026-10-10"},
                         "k2": {"verdict": "fail", "tester": "a", "date": "2026-10-10"},
                         "k3": {"verdict": "pass", "tester": "a", "date": "2026-10-10", "needs_recheck": True}},
             "attachments": {"x": {"size": 10}}, "orphaned_results": {}}
    s = summary(block, ["k1", "k2", "k3", "k4"])
    assert (s["pass"], s["fail"], s["untested"], s["invalid"], s["needs_recheck"]) == (2, 1, 1, 1, 1)
    assert not s["complete"] and s["attachment_bytes"] == 10
    assert summary({"results": {"k1": block["results"]["k1"]}, "attachments": {}}, ["k1"])["complete"]


def test_carry_over_by_key():
    prev = {"report_key": "old", "results": {
        "k1": {"verdict": "pass", "fingerprint": "f1", "attachments": ["a"]},
        "k2": {"verdict": "pass", "fingerprint": "zz", "attachments": []},
        "k9": {"verdict": "fail", "attachments": ["b"], "description": "gone case"}},
        "orphaned_results": {}, "attachments": {"a": {"name": "a.png"}, "b": {"name": "b.log"}, "c": {"name": "c"}}}
    rep = _rep(("k1", "f1"), ("k2", "f2"), ("k3", "f3"))
    block = carry_over(prev, rep)
    assert block["results"]["k1"]["carried_from"] == "old" and not block["results"]["k1"].get("needs_recheck")
    assert block["results"]["k2"]["needs_recheck"] is True
    assert block["orphaned_results"]["k9"]["last_description"] == "gone case"
    assert set(block["attachments"]) == {"a", "b"}  # unreferenced 'c' dropped
    cases = {c["key"]: c for c in rep["test_case_candidates"]}
    assert cases["k1"]["test_result"]["attachments"] == [{"id": "a", "name": "a.png"}]
    assert cases["k3"]["test_result"] is None


def test_read_results_rejects_foreign_files(tmp_path):
    p = tmp_path / "r.html"
    p.write_text('<script type="application/json" id="results">{"schema": 9, "results": {}}</script>')
    with pytest.raises(UsageError):
        read_results(p)
    with pytest.raises(UsageError):
        read_results(tmp_path / "missing.html")
