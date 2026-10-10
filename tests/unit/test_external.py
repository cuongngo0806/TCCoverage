"""Third-party API boundary signals (spec 005)."""
import pytest

from tcadvisor.classify.external import ExternalCall, external_risk, is_standard, load_contracts, signals
from tcadvisor.models import UsageError


def _call(name="lib::send", **sig):
    base = {"result": "", "result_type": "", "may_throw": False, "out_params": [], "callbacks": [], "buffers": [],
            "discarded": []}
    return ExternalCall(name, "lib/api.h", "src/a.cpp", 10, {**base, **sig})


def test_standard_library_is_not_third_party():
    assert is_standard("std::vector::push_back", "/usr/include/c++/13/bits/stl_vector.h")
    assert is_standard("memcpy", "/usr/include/string.h")
    assert is_standard("__builtin_expect", "")
    assert not is_standard("curl_easy_perform", "/usr/include/curl/easy.h")
    assert not is_standard("lib::send", "/opt/lib/include/lib/api.h")


def test_signals_from_declaration_and_call_site():
    groups = dict((g, h) for g, h in signals(_call(result="status", result_type="int", discarded=[10]), "f"))
    assert "ignored at line 10" in groups["logic"]
    sig = [g for g, _ in signals(_call(may_throw=True, callbacks=["cb"], out_params=["out"]), "f")]
    assert sig == ["exception_safety", "ownership_lifetime", "thread_safety"]
    assert signals(_call(), "f")[0][0] == "logic" and "stub" in signals(_call(), "f")[0][1]


def test_one_classification_takes_the_most_severe_group_and_contract_hints():
    r = external_risk("f", [_call(buffers=[("b", "n")]), _call("lib::open", result="pointer", result_type="T *")],
                      {"lib::*": ["blocks for up to 30 s"]})
    assert r.risk_group == "ownership_lifetime" and r.sub_reason == "external_call"
    assert r.hints[0] == "Contract: lib::send: blocks for up to 30 s"
    assert "`lib::send` (lib/api.h, src/a.cpp:10)" in r.detail


def test_contracts_file_validation(tmp_path):
    assert load_contracts(tmp_path) == {}
    bad = tmp_path / "c.json"
    bad.write_text('{"x": "not a list"}')
    with pytest.raises(UsageError):
        load_contracts(tmp_path, bad)
    with pytest.raises(UsageError):
        load_contracts(tmp_path, tmp_path / "missing.json")


def test_operators_constructors_and_queries_are_not_boundary_cases():
    assert signals(_call("lib::Addr::operator==", role="operator", result="status", result_type="bool"), "f") == []
    assert signals(_call("lib::Addr::Addr", role="special", may_throw=True), "f") == []
    q = _call("lib::Addr::port", role="const_method", result="status", result_type="int", may_throw=True)
    assert signals(q, "f") == []
    assert external_risk("f", [q]) is None
    assert external_risk("f", [q], {"lib::Addr::port": ["0 when unbound"]}).hints == [
        "Contract: lib::Addr::port: 0 when unbound"]
    p = _call("lib::Tree::get_child", role="const_method", result="pointer", result_type="Node *")
    assert [g for g, _ in signals(p, "f")] == ["ownership_lifetime"]


def test_log_statement_lines_cover_multiline_logs_and_preprocessor_lines():
    from tcadvisor.ingest.changes import log_statement_lines
    src = ["void f() {",
           "    int r = vendor_send(b, n);",
           '    VSOMEIP_INFO << "stopped"',
           "#if defined(__linux__)",
           "                 << syscall(SYS_gettid)",
           "#endif",
           "            ;",
           "    vendor_close();",
           "}"]
    assert log_statement_lines(src, 1, 9) == {3, 4, 5, 6, 7}
