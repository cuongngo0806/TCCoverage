import json

from tcadvisor.report.render import to_brief, to_markdown
from tcadvisor.verify.annotate import merge
from tcadvisor.verify.pack import build_packets


def _report(tmp_path):
    (tmp_path / "a.cpp").write_text("int x;\nint f(int a) {\n  if (a > 1) {\n    return 2;\n  }\n  return a;\n}\nint g;\n")
    sym = {"qualified_name": "f", "kind": "function", "file_path": "a.cpp", "line": 2}
    case = lambda i, p: {"id": i, "priority": p, "risk_group": "logic", "sub_reason": None, "description": "d",
                         "activation_condition": "w", "evidence": [sym], "corner_cases": [], "hop_distance": 0,
                         "related_cmake_targets": ["T"], "node_id": "f"}
    return {"change_input": {"target_repo_path": str(tmp_path), "mode": "git_diff", "commit_range": "a..b"},
            "test_case_candidates": [case("TC-0001", "P1"), case("TC-0002", "P2"), case("TC-0003", "P3")],
            "uncertainty_flags": [], "changed_symbols": [], "target_scope": [], "cache_hit": False,
            "llm_enabled": False, "llm_degraded": False, "llm_token_usage": None, "run_id": "r"}


def test_packets_share_code_and_respect_priorities(tmp_path):
    packets, notes = build_packets(_report(tmp_path), {"P1", "P2"}, 10)
    assert len(packets) == 1 and [c["id"] for c in packets[0]["cases"]] == ["TC-0001", "TC-0002"]
    assert "return a;" in packets[0]["code"] and "int g;" not in packets[0]["code"]
    _, notes = build_packets(_report(tmp_path), {"P1", "P2"}, 1)
    assert "TC-0002" in notes[0]


def test_annotate_only_annotates(tmp_path):
    r = _report(tmp_path)
    before = [(c["id"], c["priority"]) for c in r["test_case_candidates"]]
    w = merge(r, {"cases": {"TC-0001": {"verdict": "confirmed", "note": "real", "extra_corner_cases": ["a=1"]},
                            "TC-0003": {"verdict": "weak", "recheck": False}, "TC-9": {"verdict": "confirmed"},
                            "TC-0002": {"verdict": "drop"}},
                  "summary": "s", "additional_checks": [{"title": "t", "why": "y"}], "models": ["haiku"]})
    assert [(c["id"], c["priority"]) for c in r["test_case_candidates"]] == before
    assert r["test_case_candidates"][0]["verification"]["verdict"] == "confirmed"
    assert "verification" not in r["test_case_candidates"][1]
    assert len(w) == 2 and r["ai_verification"]["verified_cases"] == 2
    assert "AI:confirmed" in to_brief(r) and "Also check" in to_markdown(r)
    json.dumps(r)


def test_verify_runner_with_fake_claude(tmp_path):
    import stat
    import pytest
    from tcadvisor.models import UsageError
    from tcadvisor.verify.runner import verify

    rp = tmp_path / "out" / "report.json"
    rp.parent.mkdir()
    rp.write_text(json.dumps(_report(tmp_path)))
    fake = tmp_path / "claude"
    fake.write_text("#!/usr/bin/env python3\nimport json,sys\nprompt=sys.stdin.read()\n"
                    "res={'summary':'s','additional_checks':[{'title':'t','why':'w','evidence':'a.cpp:2'}]} "
                    "if 'VERDICTS:' in prompt else {'cases':{'TC-0001':{'verdict':'confirmed','note':'n',"
                    "'extra_corner_cases':['a=1'],'recheck':True}}}\n"
                    "print(json.dumps({'result':json.dumps(res),'total_cost_usd':0.001,'usage':{'input_tokens':10,'output_tokens':5}}))\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(UsageError):
        verify(rp, approved=False, claude=str(fake))
    res = verify(rp, approved=True, claude=str(fake))
    r = json.loads(rp.read_text())
    assert res["verified"] == 1 and res["usage"]["calls"] == 2
    assert r["test_case_candidates"][0]["verification"]["extra_corner_cases"] == ["a=1"]
    assert r["ai_verification"]["additional_checks"][0]["evidence"] == "a.cpp:2"


def test_ai_evidence_must_resolve_inside_repo(tmp_path):
    r = _report(tmp_path)
    merge(r, {"cases": {}, "additional_checks": [{"title": "ok", "why": "w", "evidence": "a.cpp:2"},
                                                 {"title": "escape", "why": "w", "evidence": "../../etc/passwd:1"},
                                                 {"title": "bad line", "why": "w", "evidence": "a.cpp:999"}]})
    st = [(c["title"], c["evidence"], c["evidence_status"]) for c in r["ai_verification"]["additional_checks"]]
    assert st[0] == ("ok", "a.cpp:2", "resolved")
    assert st[1][1] == "" and st[2][1] == "" and st[1][2] == "unverified AI suggestion"
