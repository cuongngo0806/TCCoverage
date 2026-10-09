"""US4: blind spots are flagged, never silently dropped, never fabricated into cases."""


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
