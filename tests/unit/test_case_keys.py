"""Stable case identity (spec 006 FR-612)."""
from tcadvisor.classify.cases import assign_keys
from tcadvisor.models import ImpactNode, SymbolRef
from tcadvisor.models import TestCaseCandidate as Case

SRC = "int helper(int x) {\n  return x + 1;\n}\n\nint other(int y) {\n  return y;\n}\n"


def _case(name, line, group="logic", sub=None, nid="n1"):
    return Case(id="", description="d", activation_condition="a",
                             evidence=[SymbolRef(name, "function", "a.cpp", line)], priority="P2",
                             risk_group=group, related_cmake_targets=["t"], node_id=nid, sub_reason=sub)


def _nodes():
    return {"n1": ImpactNode("n1", SymbolRef("helper", "function", "a.cpp", 1), 0, root_ids={"n1"}),
            "n2": ImpactNode("n2", SymbolRef("other", "function", "a.cpp", 5), 0, root_ids={"n2"})}


def test_key_is_independent_of_order_and_unique(tmp_path):
    (tmp_path / "a.cpp").write_text(SRC)
    a = [_case("helper", 1), _case("other", 5, nid="n2"), _case("helper", 1, "thread_safety")]
    b = [a_.__class__(**{**vars(x)}) for x in reversed(a) for a_ in [x]]
    assign_keys(a, _nodes(), tmp_path)
    assign_keys(b, _nodes(), tmp_path)
    assert {c.key for c in a} == {c.key for c in b} and len({c.key for c in a}) == 3
    dup = [_case("helper", 1), _case("helper", 1)]
    assign_keys(dup, _nodes(), tmp_path)
    assert dup[1].key == dup[0].key + "-2"


def test_fingerprint_follows_the_evidence_function_only(tmp_path):
    (tmp_path / "a.cpp").write_text(SRC)
    c1, c2 = _case("helper", 1), _case("other", 5, nid="n2")
    assign_keys([c1, c2], _nodes(), tmp_path)
    (tmp_path / "a.cpp").write_text(SRC.replace("return y;", "return y * 2;").replace("x + 1", "x + 1 /* c */"))
    d1, d2 = _case("helper", 1), _case("other", 5, nid="n2")
    assign_keys([d1, d2], _nodes(), tmp_path)
    assert d1.key == c1.key and d1.code_fingerprint == c1.code_fingerprint  # comment-only edit
    assert d2.key == c2.key and d2.code_fingerprint != c2.code_fingerprint
