from tcadvisor.graph.sources import guard_scope
from tcadvisor.ingest.changes import mask_literals, textual_functions


def names(src: str):
    return [(n, a, b) for n, a, b in textual_functions(src.splitlines())]


def test_mask_literals_basic():
    assert mask_literals('f("a{b", \'}\')') == 'f("   ", \' \')'
    assert "{" not in mask_literals(r'x = "q\"{";')


def test_braces_in_strings_and_chars():
    src = 'void A::f() {\n  puts("}}");\n  char c = \'{\';\n}\nvoid A::g() {\n}\n'
    assert names(src) == [("A::f", 1, 4), ("A::g", 5, 6)]


def test_escaped_quote():
    src = 'void A::f() {\n  s = "\\"}";\n}\n'
    assert names(src) == [("A::f", 1, 3)]


def test_multiline_init_list_not_a_head():
    src = ('A::A(int x)\n    : a_(x),\n      b_(foo(x)) {\n  init();\n}\n')
    assert [n for n, *_ in names(src)] == ["A::A"]


def test_plain_call_is_not_head():
    src = 'void A::f() {\n  helper(1,\n    2);\n  if (x) {\n    g(a);\n  }\n}\n'
    assert names(src) == [("A::f", 1, 7)]


def test_template_and_destructor():
    src = ('template <class T>\nvoid Foo<T>::bar(int x) {\n}\nA::~A() {\n}\n')
    assert [n for n, *_ in names(src)] == ["Foo::bar", "A::~A"]


def test_prefixless_unqualified_rejected():
    assert names('foo(1) {\n}\n') == []


def test_guard_scope_ignores_braces_in_strings():
    lines = ['if (x) {', '  log("}");', '  y();', '}', 'z();']
    assert guard_scope(lines, 1) == (1, 4)


def test_one_line_definitions_and_deleted_declarations():
    from tcadvisor.ingest.changes import textual_functions
    got = textual_functions(["struct S {", "  S() : a(1) {}", "  S(const S&) = delete;",
                             "  int get() const { return a; }", "  bool ok() const noexcept { return a > 0; }", "};",
                             "int f(int a);", "void g() {", "  if (x) { y(); }", "}"])
    assert [g[0] for g in got] == ["S", "get", "ok", "g"]
    assert got[1][1] == got[1][2] == 4


def test_forwarding_accessor_detection(tmp_path):
    from tcadvisor.classify.patterns import _Files, _forwards
    from tcadvisor.models import SymbolRef
    (tmp_path / "a.h").write_text("struct R {\n  bool is_defined() const { return m_p->is_defined(); }\n"
                                  "  int twice() const { return g.level() * 2; }\n};\n")
    files = _Files(tmp_path, None)
    assert _forwards(files, SymbolRef("R::is_defined", "method", "a.h", 2), "is_defined")
    assert not _forwards(files, SymbolRef("R::twice", "method", "a.h", 3), "level")
