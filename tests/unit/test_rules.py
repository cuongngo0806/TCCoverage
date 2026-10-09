from tcadvisor.classify.cases import priority
from tcadvisor.classify.rules import boundary_hints, classify, token_delta
from tcadvisor.ingest.changes import SymInfo, SymbolChange, conditional_stack, strip_comments


def _fn(tokens, decl=None, **kw):
    return SymInfo(usr="u", name="f", kind="function", display="f()", start=1, end=5, tokens=tokens,
                   decl_tokens=decl or ["int", "f", "(", ")"], **kw)


def _change(old, new, **kw):
    return SymbolChange(node_id="u", rel_path="a.cpp", change_kind="modified", name="f", kind="function", line=1,
                        old=old, new=new, **kw)


def groups(rs):
    return {(r.risk_group, r.sub_reason) for r in rs}


def test_priority_rule_is_deterministic():
    assert priority(0, "abi_layout") == "P1"
    assert priority(1, "thread_safety") == "P1"
    assert priority(1, "logic") == "P2"
    assert priority(2, "exception_safety") == "P2"
    assert priority(2, "build_config") == "P3"


def test_logic_is_fallback_and_boundaries():
    rs = classify(_change(_fn(["return", "a", ">", "3"]), _fn(["return", "a", ">=", "5"]),
                          added_lines=["return a >= 5;"], removed_lines=["return a > 3;"]), ["Debug"])
    assert groups(rs) == {("logic", None)}
    assert any("a = 4, 5, 6" in h for h in rs[0].hints)
    assert any(h.startswith("Previous boundary") for h in rs[0].hints)


def test_lock_order():
    old = ["lock_guard", "<", "mutex", ">", "a", "(", "m1", ")", ";", "lock_guard", "<", "mutex", ">", "b", "(", "m2", ")"]
    new = ["lock_guard", "<", "mutex", ">", "b", "(", "m2", ")", ";", "lock_guard", "<", "mutex", ">", "a", "(", "m1", ")"]
    assert ("thread_safety", "lock_order") in groups(classify(_change(_fn(old), _fn(new)), []))


def test_atomic_and_move():
    rs = classify(_change(_fn(["x", "=", "y"]), _fn(["x", ".", "store", "(", "std", "::", "move", "(", "y", ")", ")"])), [])
    assert {("thread_safety", "atomic"), ("ownership_lifetime", "move_semantics")} <= groups(rs)


def test_reference_param_change():
    rs = classify(_change(_fn(["{", "}"], ["int", "f", "(", "T", "t", ")"]),
                          _fn(["{", "}"], ["int", "f", "(", "T", "&", "t", ")"])), [])
    assert ("ownership_lifetime", "reference") in groups(rs)
    assert ("abi_layout", "signature_change") in groups(rs)


def test_debug_release():
    rs = classify(_change(_fn(["x"]), _fn(["assert", "(", "x", ")"])), ["Release"])
    assert ("build_config", "debug_release") in groups(rs)


def test_helpers():
    assert token_delta(["a", "b"], ["a", "c"]) == (["c"], ["b"])
    assert strip_comments("int a; // x\n/* y */int b;") == "int a; \nint b;"
    cs = conditional_stack(["#ifdef A", "x", "#else", "y", "#endif", "z"])
    assert cs[2] == ["#ifdef A"] and "#else" in cs[4][0] and 6 not in cs
    assert boundary_hints(["if (len <= 0x10)"])[0].endswith("15, 16, 17")


def test_include_guard_is_not_a_condition():
    lines = ["// c", "#ifndef A_H_", "#define A_H_", "int f();", "#ifdef X", "int g();", "#endif", "#endif"]
    cs = conditional_stack(lines)
    assert 4 not in cs and cs[6] == ["#ifdef X"]


def test_logical_and_is_not_move_semantics():
    rs = classify(_change(_fn(["if", "(", "a", ")"]), _fn(["if", "(", "a", "&&", "b", ")"])), [])
    assert not any(r.risk_group == "ownership_lifetime" for r in rs)


def test_new_pure_virtual_hint_and_propagation():
    def cls(virtuals):
        return SymInfo(usr="c", name="C", kind="class", display="C", start=1, end=9, tokens=["class", "C"] + virtuals,
                       decl_tokens=[], virtuals=virtuals)
    ch = SymbolChange(node_id="c", rel_path="c.h", change_kind="modified", name="C", kind="class", line=1,
                      old=cls(["f()"]), new=cls(["f()", "g(int) = 0"]), is_header=True)
    rs = classify(ch, [])
    abi = [r for r in rs if r.risk_group == "abi_layout"][0]
    assert "pure virtual" in abi.detail and any("must now override" in h for h in abi.hints)
    assert ch.propagation() == {"inherit_override", "include"}


def test_project_lock_wrappers_count_as_thread_safety():
    rs = classify(_change(_fn(["x", "=", "1"]), _fn(["MutexLock", "l", "(", "&", "mutex_", ")", ";", "x", "=", "1"])), [])
    assert ("thread_safety", "mutex") in groups(rs)


def test_log_only_change_is_low_priority_and_does_not_propagate():
    ch = _change(_fn(["VSOMEIP_INFO", "<<", "\"a\""]), _fn(["VSOMEIP_WARNING", "<<", "\"b\"", "<<", "x"]),
                 added_lines=['    VSOMEIP_WARNING << "b: "', "        << x;"], removed_lines=['    VSOMEIP_INFO << "a";'])
    rs = classify(ch, [])
    assert [(r.risk_group, r.sub_reason) for r in rs] == [("logic", "logging")]
    assert ch.propagation() == set()
    mixed = _change(_fn(["x"]), _fn(["y"]), added_lines=['    LOG(INFO) << "a";', "    x = y;"])
    assert not mixed.is_log_only


def test_recompile_only_subreasons_rank_low():
    assert priority(0, "abi_layout", "header_change") == "P2"
    assert priority(2, "abi_layout", "inline_change") == "P3"
    assert priority(0, "abi_layout", "member_change") == "P1"
    assert priority(0, "logic", "logging") == "P3"


def test_test_code_changes_do_not_propagate():
    ch = SymbolChange(node_id="t", rel_path="db/db_sst_test.cc", change_kind="modified", name="X_Test::TestBody",
                      kind="method", line=3, old=_fn(["a"]), new=_fn(["b"]))
    assert ch.is_test_code and ch.propagation() == set()
    assert [(r.risk_group, r.sub_reason) for r in classify(ch, [])] == [("logic", "test_code")]
    assert not SymbolChange(node_id="u", rel_path="db/attest.cc", change_kind="modified", name="f", kind="function",
                            line=1).is_test_code


def test_const_reference_and_const_char_pointer_are_not_lifetime_risks():
    rs = classify(_change(_fn(["{", "}"], ["void", "f", "(", "int", "a", ")"]),
                          _fn(["{", "}"], ["void", "f", "(", "int", "a", ",", "const", "std", "::", "string", "&", "s",
                                           ",", "const", "char", "*", "p", ")"])), [])
    assert not any(r.risk_group == "ownership_lifetime" for r in rs)
    rs = classify(_change(_fn(["{", "}"], ["void", "f", "(", "Foo", "*", "p", ")"]),
                          _fn(["{", "}"], ["void", "f", "(", "Foo", "&", "p", ")"])), [])
    assert {("ownership_lifetime", "raw_pointer"), ("ownership_lifetime", "reference")} <= groups(rs)
