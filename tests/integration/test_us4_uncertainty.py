"""US4: blind spots are flagged, never silently dropped, never fabricated into cases."""
import sys

import pytest

from conftest import cases_for


def _flags(r):
    return {(f["category"], f["related_symbol"]["qualified_name"] if f["related_symbol"] else None)
            for f in r["uncertainty_flags"]}


def test_uninstantiated_template(project):
    project.edit("include/door/util.h", "return a > b ? a : b;", "return a >= b ? a : b;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("uninstantiated_template", "maxOf") in _flags(r)
    assert not [c for c in r["test_case_candidates"] if c["evidence"][0]["qualified_name"] == "maxOf"]


def test_instantiated_template_is_not_flagged(project):
    project.edit("src/util.cpp", "    return n;", "    return maxOf(n, 0);")
    project.commit()
    project.edit("include/door/util.h", "return a > b ? a : b;", "return a >= b ? a : b;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("uninstantiated_template", "maxOf") not in _flags(r)
    assert any(n["symbol"]["qualified_name"] == "clampRetries" for n in r["impact_nodes"])


def test_di_only_virtual_method(project):
    project.edit("src/handlers.cpp", "    last = code;", "    last = code * 2;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("di_config_routing", "AuditHandler::onEvent") in _flags(r)
    assert not [c for c in r["test_case_candidates"] if c["evidence"][0]["qualified_name"] == "AuditHandler::onEvent"]


def test_virtual_method_with_callers_through_base(project):
    # RemoteDoorLock::apply overrides ILock::apply; add a caller through the interface
    project.edit("src/lock.cpp", "int dispatch(int code) {", "bool applyAny(ILock& l, DoorState& s) { return l.apply(s); }\n\nint dispatch(int code) {")
    project.commit()
    project.edit("src/lock.cpp", "    return s.locked;\n}", "    return !s.locked ? false : s.locked;\n}")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("di_config_routing", "RemoteDoorLock::apply") not in _flags(r)
    hops = {n["symbol"]["qualified_name"]: n["hop_distance"] for n in r["impact_nodes"]}
    assert hops.get("ILock::apply") == 1 and hops.get("applyAny") == 2


def test_callback_is_dynamic_dependency(project):
    project.edit("src/handlers.cpp", "    (void)tick;", "    (void)tick;\n    if (tick > 10) return;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("dynamic_runtime_dependency", "onTimer") in _flags(r)
    # still a concrete case: the function itself is real evidence
    assert [c for c in r["test_case_candidates"] if c["evidence"][0]["qualified_name"] == "onTimer"]


def test_change_in_inactive_ifdef_becomes_a_named_root(project):
    project.edit("src/util.cpp", "int clampRetries(int n) {",
                 "#ifdef DOOR_EXTRA\nint extraCheck(int v) {\n    return v;\n}\n#endif\nint clampRetries(int n) {")
    project.commit()
    project.edit("src/util.cpp", "    return v;\n}\n#endif", "    return v > 1 ? 1 : v;\n}\n#endif")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    roots = {s["symbol"]["qualified_name"]: s for s in r["changed_symbols"]}
    assert "extraCheck" in roots  # named although the parser never saw it
    assert any(f["category"] == "build_config_incomplete_macro" and f["related_symbol"]
               and f["related_symbol"]["qualified_name"] == "extraCheck" for f in r["uncertainty_flags"])


def _macro_flags(r, name):
    return [f["reason"] for f in r["uncertainty_flags"] if f["category"] == "build_config_incomplete_macro"
            and f["related_symbol"] and f["related_symbol"]["qualified_name"] == name]


_PLATFORM_GUARDS = ("int clampRetries(int n) {\n"
                    "#if defined(__linux__)\n    if (n < 0) return 0;\n#endif\n"
                    "#ifdef _WIN32\n    if (n < -1) return -1;\n#else\n    if (n < -2) return -2;\n#endif\n")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="compiler predefines __linux__ only on Linux")
def test_compiler_predefined_macro_counts_as_defined(project):
    project.edit("src/util.cpp", "int clampRetries(int n) {\n", _PLATFORM_GUARDS)
    project.commit()
    project.edit("src/util.cpp", "if (n < 0) return 0;", "if (n <= 0) return 0;")  # inside #if defined(__linux__)
    project.edit("src/util.cpp", "if (n < -2) return -2;", "if (n <= -2) return -2;")  # #else of #ifdef _WIN32
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert _macro_flags(r, "clampRetries") == []  # libclang parsed both branches on Linux
    assert cases_for(r, "clampRetries")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="compiler predefines __linux__ only on Linux")
def test_other_platform_branch_is_flagged(project):
    project.edit("src/util.cpp", "int clampRetries(int n) {\n", _PLATFORM_GUARDS)
    project.commit()
    project.edit("src/util.cpp", "if (n < -1) return -1;", "if (n <= -1) return -1;")  # inside #ifdef _WIN32
    project.edit("src/util.cpp", "if (n < 0) return 0;", "if (n <= 0) return 0;")  # parsed: must not be blamed
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    reasons = _macro_flags(r, "clampRetries")
    assert len(reasons) == 1
    assert "`_WIN32` is not defined for the indexed target (" in reasons[0]
    assert "-linux)" in reasons[0] and "the Windows branch was never parsed" in reasons[0]
    assert "__linux__" not in reasons[0]
