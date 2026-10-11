"""Def-use facts for data-path tracing (spec 006 US1)."""

import pytest

from tcadvisor.graph.dataflow import _taint, is_emitter, words

SRC = """struct Frame { int code; int len; };
int compute(int x);
void fill(int& out);
void send_frame(const Frame& f);
struct A {
  int base_ = 1;
  Frame build(int x) {
    Frame f;
    f.code = compute(x) + base_;
    int extra = 0;
    fill(extra);
    f.len = extra;
    if (f.code > 9) f.len = 0;
    return f;
  }
};
"""


@pytest.fixture(scope="module")
def build_facts(tmp_path_factory):
    from tcadvisor.index.flow import FlowExtractor
    d = tmp_path_factory.mktemp("flow")
    (d / "a.cpp").write_text(SRC)
    r = FlowExtractor(d).extract_flow(d / "a.cpp", ("-x", "c++", "-std=c++17"))
    return next(f for f in r["functions"].values() if f["name"] == "A::build")


def test_defs_calls_conds(build_facts):
    f = build_facts
    defs = {(d[0], d[1]): set(d[2]) for d in f["defs"]}
    assert {"param:x", "member:base_"} <= defs[(9, "local:f")]
    assert any(s.startswith("call:") for s in defs[(9, "local:f")])
    assert defs[(14, "return")] == {"local:f"}
    fill = next(c for c in f["calls"] if c[2] == "fill")
    assert fill[6] == [[0, "local:extra"]]  # out-argument
    assert [c[0] for c in f["conds"]] == [13]


def test_taint_from_changed_line_and_from_param(build_facts):
    t = _taint(build_facts, set(), {9})
    assert {"local:f", "return"} <= t
    assert "return" in _taint(build_facts, {"param:x"}, set())
    assert "return" not in _taint(build_facts, set(), set())


def test_emitter_names():
    third = lambda n, d: True  # noqa: E731
    call = lambda name, ext="": [1, "u", name, "", ext, [], [], None]  # noqa: E731
    assert words("transportSendFrame") == {"transport", "send", "frame"}
    assert is_emitter(call("Publisher::publish"), [], third)
    assert is_emitter(call("ipc_write_msg"), [], third)
    assert not is_emitter(call("write_log"), [], third)  # logging
    assert not is_emitter(call("std::ostream::write"), [], third)
    assert not is_emitter(call("compute"), [], third)
    assert is_emitter(call("compute"), ["comp*"], third)  # project sink
    assert is_emitter(call("curl_easy_perform", "/usr/include/curl/easy.h"), [], third)
