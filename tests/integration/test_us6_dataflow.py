"""Spec 006 US1: changed data followed through unchanged modules to the code that sends it."""
from fixtures_us6 import add_flow_fixture


def _change_producer(project):
    project.edit("src/frame.cpp", "    f.code = raw * 2;", "    f.code = raw * 3 + base_;")
    project.commit()


def _by_pattern(r, pattern):
    return {c["evidence"][0]["qualified_name"]: c for c in r["test_case_candidates"] if c.get("pattern") == pattern}


def test_emitter_two_modules_away_gets_a_case(project):
    add_flow_fixture(project)
    _change_producer(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    em = _by_pattern(r, "data_path_emitter")
    assert set(em) == {"Publisher::publish"}, set(em)
    c = em["Publisher::publish"]
    assert [s["symbol"]["qualified_name"] for s in c["path"]] == [
        "Producer::build_status", "Producer::tick", "Relay::relay", "Publisher::publish"]
    assert [s["role"] for s in c["path"]] == ["producer", "forwarder", "forwarder", "emitter"]
    assert c["sub_reason"] == "data_path_emitter" and "transport_send" in c["description"]
    assert c["evidence"][1]["qualified_name"] == "Producer::build_status"
    fw = _by_pattern(r, "data_path_forwarder")
    assert set(fw) == {"Relay::relay"}
    # Producer::tick already has a case (direct caller of the change): the forwarder reason is folded into it
    tick = [c for c in r["test_case_candidates"] if c["evidence"][0]["qualified_name"] == "Producer::tick"]
    assert len([c for c in tick if c["risk_group"] == "logic"]) == 1
    assert any("Also (data_path_forwarder)" in c["description"] for c in tick)
    # neither Relay nor Publisher changed
    assert {s["symbol"]["qualified_name"] for s in r["changed_symbols"]} == {"Producer::build_status"}


def test_check_in_the_emitter_is_reported_and_ranked_lower(project):
    add_flow_fixture(project)
    project.edit("src/frame.cpp", "    transport_send(", "    if (f.code > 100)\n        return;\n    transport_send(")
    project.commit("publisher validates")
    _change_producer(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    c = _by_pattern(r, "data_path_emitter")["Publisher::publish"]
    assert c["sub_reason"] == "data_path_emitter_checked" and "confirm the check" in c["description"]
    assert c["path"][-1]["checked"] is True


def test_value_stored_in_a_member_container_is_flagged(project):
    add_flow_fixture(project)
    project.edit("src/frame.cpp", "    Publisher p;\n    p.publish(copy);", "    q_.push_back(copy);")
    project.commit("relay queues")
    _change_producer(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert not _by_pattern(r, "data_path_emitter")
    assert any("leaves the traced paths" in f["reason"] and "stored into `q_`" in f["reason"]
               for f in r["uncertainty_flags"])


def test_no_patterns_switch(project):
    add_flow_fixture(project)
    _change_producer(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--no-patterns")
    assert not _by_pattern(r, "data_path_emitter")


def test_value_stored_in_a_member_is_followed_to_its_reader(project):
    add_flow_fixture(project)
    project.edit("include/door/frame.h", "    std::deque<Frame> q_;", "    std::deque<Frame> q_;\n    Frame last_;\n    void flush();")
    project.edit("src/frame.cpp", "    Publisher p;\n    p.publish(copy);", "    last_ = copy;")
    project.edit("src/frame.cpp", "void Publisher::publish(", "void Relay::flush() {\n    Publisher p;\n    p.publish(last_);\n}\n"
                 "void Publisher::publish(")
    project.commit("relay stores, flush sends")
    _change_producer(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--max-hop-depth", "3")
    c = _by_pattern(r, "data_path_emitter")["Publisher::publish"]
    names = [s["symbol"]["qualified_name"] for s in c["path"]]
    assert "Relay::relay" in names and "Relay::flush" in names, names
    assert any("stores it in `last_`" in s["detail"] for s in c["path"])


def test_depth_limit_is_reported_where_tracing_stopped(project):
    add_flow_fixture(project)
    project.edit("src/frame.cpp", "    p.publish(copy);", "    p.handle(copy);")
    project.edit("include/door/frame.h", "    void publish(const Frame& f);", "    void publish(const Frame& f);\n"
                 "    void handle(const Frame& f);")
    project.edit("src/frame.cpp", "void Publisher::publish(", "void Publisher::handle(const Frame& f) {\n"
                 "    publish(f);\n}\nvoid Publisher::publish(")
    project.commit("relay -> handle -> publish")
    _change_producer(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--max-hop-depth", "1")
    assert not _by_pattern(r, "data_path_emitter")
    assert any("depth limit" in f["reason"] and "Publisher::handle" in f["reason"]
               for f in r["uncertainty_flags"]), [f["reason"] for f in r["uncertainty_flags"]]
