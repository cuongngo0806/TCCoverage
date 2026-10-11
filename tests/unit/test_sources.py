"""Guard comparison for trigger sources (spec 006 US2)."""
from tcadvisor.graph.sources import guard_identifiers, has_guard
from tcadvisor.models import SymbolRef

SRC = """void A::one() {
    if (!session_ || state_ != kReady) return;
    run(1);
}
void A::two() {
    run(2);
}
void A::three() { if (session_) run(3); }
void A::four() {
    PROCESS(run_macro);
}
"""


def test_guard_identifiers_ignore_keywords_and_target():
    ids = guard_identifiers(["    if (!session_ || state_ != kReady) return;", "  x = 1;"], "A::run")
    assert ids == {"session_", "state_", "kReady"}


def test_has_guard_present_absent_unknown(tmp_path):
    (tmp_path / "a.cpp").write_text(SRC)
    ids, cache = {"session_"}, {}
    ref = lambda n, l: SymbolRef(n, "method", "a.cpp", l)  # noqa: E731
    assert has_guard(tmp_path, ref("A::one", 1), ids, "A::run", cache) == "present"
    assert has_guard(tmp_path, ref("A::two", 5), ids, "A::run", cache) == "absent"
    assert has_guard(tmp_path, ref("A::three", 8), ids, "A::run", cache) == "present"  # one-line body
    assert has_guard(tmp_path, ref("A::four", 9), ids, "A::run", cache) == "unknown"


def test_guard_scope():
    from tcadvisor.graph.sources import guard_scope
    lines = ["void f() {", "  if (!s) return;", "  if (a) {", "    g();", "  }", "  if (b)", "    h();", "  k();", "}"]
    assert guard_scope(lines, 2) == (2, 10**9)  # early exit protects the rest
    assert guard_scope(lines, 3) == (3, 5)  # block
    assert guard_scope(lines, 6) == (6, 7)  # braceless if: next statement only
