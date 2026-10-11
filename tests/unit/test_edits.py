"""Spec 007 US1/US3: edit shapes -> concrete corner cases; noise fixes."""
from tcadvisor.classify.edits import analyse, input_classes, tokens
from tcadvisor.classify.rules import classify
from tcadvisor.graph.sources import guarded_calls
from tcadvisor.ingest.changes import SymInfo, SymbolChange


def kinds(old, new):
    return {s.kind: s.hint for s in analyse(old, new)}


def fn(*body):
    return ["void f() {", *body, "}"]


def test_operator_flip_names_the_equality_case():
    k = kinds(fn("  while (left < right) {", "    mid = (left + right) / 2;", "  }"),
              fn("  while (left <= right) {", "    mid = (left + right) / 2;", "  }"))
    assert "left == right" in k["operator_flip"] and "now also holds" in k["operator_flip"]
    k = kinds(fn("  return size_ >= x.size_;"), fn("  return size_ > x.size_;"))
    assert "operator_flip" in k and "return_change" not in k and "no longer holds" in k["operator_flip"]


def test_constant_change_lists_old_and_new_limits():
    h = kinds(fn("  if (bits < 64) bits = 64;"), fn("  if (bits < 8) bits = 8;"))["constant_change"]
    assert "7, 8, 9" in h and "63, 64, 65" in h


def test_removed_guard_and_reject_input():
    h = kinds(fn("  if (opt.snap != nullptr) {", "    s = opt.snap->seq();", "  }"),
              fn("  {", "    s = opt.snap->seq();", "  }"))["removed_guard"]
    assert "opt.snap != nullptr" in h and "nullptr (null)" in h
    # a dropped conjunct is a removed guard too
    h = kinds(fn("  if (p && p->ok()) {", "    use(p);", "  }"), fn("  if (p->ok()) {", "    use(p);", "  }"))
    assert "removed_guard" in h


def test_operator_tweak_is_not_a_removed_guard():
    assert "removed_guard" not in kinds(fn("  if (a < b) {", "  }"), fn("  if (a <= b) {", "  }"))


def test_return_change_error_swallowed():
    h = kinds(fn('  return Status::Corruption("bad");'), fn("  return Status::OK();"))["return_change"]
    assert "error" in h and "Status::OK()" in h


def test_reorder_use_after_free():
    h = kinds(fn("  e->deleter(e->key);", "  free(e);"), fn("  free(e);", "  e->deleter(e->key);"))["reorder"]
    assert "`free(e);` now runs before" in h and "use after free" in h


def test_removed_call_assignment_and_term():
    k = kinds(fn("  SetCount(this, Count(this) + 1);", "  rep_.push_back(1);"), fn("  rep_.push_back(1);"))
    assert "SetCount" in k["removed_call"]
    k = kinds(fn("  if (x) {", "    flag_ = true;", "    run();", "  }"), fn("  if (x) {", "    run();", "  }"))
    assert "flag_" in k["removed_assignment"]
    k = kinds(fn("  n = a + VarintLength(v) +", "      v;"), fn("  n = a +", "      v;"))
    assert "VarintLength(v)" in k["removed_term"]


def test_lock_added_and_removed():
    k = kinds(fn("  MutexLock l(&mutex_);", "  return snaps_.New();"), fn("  return snaps_.New();"))
    assert "mutex_" in k["lock_removed"] and "removed_call" not in k
    k = kinds(fn("  x = 1;"), fn("  std::lock_guard<std::mutex> g(mu_);", "  x = 1;"))
    assert "mu_" in k["lock_added"]


def test_value_change_and_logical_negation():
    assert "write_size" in kinds(["struct O {", "  int write_size = 4 * 1024;", "};"],
                                 ["struct O {", "  int write_size = 64;", "};"])["value_change"]
    assert "logical_flip" in kinds(fn("  if (a && b) {", "  }"), fn("  if (a || b) {", "  }"))
    assert "negation_flip" in kinds(fn("  if (ok) {", "  }"), fn("  if (!ok) {", "  }"))


def test_textual_changes_without_bodies_and_garbage():
    assert analyse([], [], ["if (a < 3) {"], ["if (a <= 3) {"])
    assert analyse(["{{{ ((("], ["))) }}}"]) is not None
    assert analyse([], []) == []


def test_parameter_input_classes():
    decl = tokens("int f(const std::vector<int>& v, const char* s, size_t n, int k, bool on, Foo* p, double d)")
    got = input_classes(decl, ["use(v, s, n, k, on, p, d)"], limit=10)
    joined = " | ".join(got)
    assert "`v`" in joined and "empty, one element" in joined and "nullptr, empty string" in joined
    assert "0, 1 and the maximum value" in joined and "negative, 0" in joined and "true and false" in joined
    assert "`p` (Foo*): nullptr" in joined and "NaN" in joined
    assert input_classes(decl, ["nothing here"]) == []


def _sym(tokens_, start=1, end=6, inline=False, decl=None):
    return SymInfo(usr="u", name="f", kind="method", display="f()", start=start, end=end, tokens=tokens_,
                   decl_tokens=decl or ["int", "f", "(", ")"], is_inline=inline)


def test_removed_guard_case_is_p1_and_hints_first():
    ch = SymbolChange(node_id="u", rel_path="a.cpp", change_kind="modified", name="f", kind="method", line=1,
                      old=_sym(["if", "(", "p", ")", "use", "(", "p", ")"]), new=_sym(["use", "(", "p", ")"]),
                      removed_lines=["  if (p) {", "    use(p);", "  }"], added_lines=["  use(p);"],
                      old_body=fn("  if (p) {", "    use(p);", "  }"), new_body=fn("  use(p);"))
    rs = classify(ch, ["Debug"])
    logic = [r for r in rs if r.risk_group == "logic"][0]
    assert logic.sub_reason == "removed_guard" and logic.hints[0].startswith("Removed condition `p`")
    from tcadvisor.classify.cases import priority
    assert priority(0, "logic", "removed_guard") == "P1" and priority(1, "logic", "removed_guard") == "P2"
    assert priority(1, "thread_safety", "lock_coupling") == "P2"


def test_inline_change_only_for_headers():
    def ch(path, header):
        return SymbolChange(node_id="u", rel_path=path, change_kind="modified", name="f", kind="method", line=1,
                            old=_sym(["return", "1"], inline=True), new=_sym(["return", "2"], inline=True),
                            is_header=header, removed_lines=["return 1;"], added_lines=["return 2;"])
    assert not any(r.sub_reason == "inline_change" for r in classify(ch("a.cc", False), ["Debug"]))
    assert any(r.sub_reason == "inline_change" for r in classify(ch("a.h", True), ["Debug"]))


def test_loop_condition_tweak_is_not_a_guard():
    lines = ["int f() {", "  while (left <= right) {", "    g(left);", "  }", "  return 0;", "}"]
    new = _sym([], start=1, end=6)
    new.calls = [("usr:g", "g", "function", "/x.cpp", 1, 3)]
    ch = SymbolChange(node_id="u", rel_path="a.cpp", change_kind="modified", name="f", kind="function", line=1,
                      new=new, added_lines=["  while (left <= right) {"], removed_lines=["  while (left < right) {"],
                      added_line_numbers=[2])
    assert guarded_calls(ch, lines) == []
    lines[1] = "  if (ready_) {"
    ch.added_lines, ch.removed_lines = ["  if (ready_) {"], []
    assert [c[1] for c in guarded_calls(ch, lines)] == ["g"]
