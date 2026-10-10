"""Spec 006 US2: every trigger source of a function protected in only one of them."""
from fixtures_us6 import add_sources_fixture


def _sibling(r):
    return {c["evidence"][0]["qualified_name"]: c for c in r["test_case_candidates"]
            if (c.get("pattern") == "sibling_source")}


def test_guard_in_one_source_lists_the_other_three(project):
    add_sources_fixture(project)
    project.edit("src/conn.cpp", "    retries_++;\n    handle_timeout();",
                 "    retries_++;\n    if (!session_)\n        return;\n    handle_timeout();")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    sib = _sibling(r)
    assert set(sib) == {"Conn::on_disconnect", "Conn::on_error", "timeout_cb"}, set(sib)
    assert all(c["sub_reason"] == "sibling_source" and c["priority"] == "P2" for c in sib.values())
    assert "session_" in " ".join(sib["Conn::on_error"]["corner_cases"])
    assert "callback registered at src/conn.cpp" in sib["timeout_cb"]["description"]
    assert [s["role"] for s in sib["Conn::on_disconnect"]["path"]] == ["source", "target"]
    ts = r["trigger_sources"]
    assert len(ts) == 1 and ts[0]["target"]["qualified_name"] == "Conn::handle_timeout"
    assert ts[0]["covered_by"] == ["Conn::on_timer"]
    assert {s["symbol"]["qualified_name"]: s["covered_by_change"] for s in ts[0]["sources"]}["Conn::on_timer"]


def test_sibling_with_the_same_guard_is_only_asked_to_confirm(project):
    add_sources_fixture(project)
    project.edit("src/conn.cpp", "    retries_ = 0;\n    handle_timeout();",
                 "    retries_ = 0;\n    if (session_ == nullptr) return;\n    handle_timeout();")
    project.commit("on_error already guarded")
    project.edit("src/conn.cpp", "    retries_++;\n    handle_timeout();",
                 "    retries_++;\n    if (!session_)\n        return;\n    handle_timeout();")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    sib = _sibling(r)
    assert sib["Conn::on_error"]["sub_reason"] == "sibling_source_guarded"
    assert sib["Conn::on_error"]["priority"] == "P3" and "Confirm the existing check" in sib["Conn::on_error"]["description"]
    assert sib["Conn::on_disconnect"]["sub_reason"] == "sibling_source"


def test_no_guard_no_sibling_cases(project):
    add_sources_fixture(project)
    project.edit("src/conn.cpp", "    retries_++;\n    handle_timeout();", "    retries_ += 2;\n    handle_timeout();")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert not _sibling(r) and r["trigger_sources"] == []
    assert not _sibling(project.analyze("--commit-range", "HEAD~1..HEAD", "--no-patterns", "--no-run-cache"))


def test_target_used_as_callback_is_flagged(project):
    add_sources_fixture(project)
    project.edit("src/conn.cpp", "    retries_ = 0;\n    handle_timeout();", "    retries_ = 0;\n    handle_timeout();\n"
                 "    void (Conn::*h)() = &Conn::handle_timeout;\n    (this->*h)();")
    project.commit("handle_timeout taken as a member pointer")
    project.edit("src/conn.cpp", "    retries_++;\n    handle_timeout();",
                 "    retries_++;\n    if (!session_)\n        return;\n    handle_timeout();")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert any("used as a callback / function pointer" in f["reason"] and
               f["related_symbol"]["qualified_name"] == "Conn::handle_timeout" for f in r["uncertainty_flags"])
