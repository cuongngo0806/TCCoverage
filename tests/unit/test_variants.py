"""Spec 012 US3: #if evaluation per variant (three-valued) and switch detection from build artefacts."""
from tcadvisor.classify.variants import am_condition, evaluate, evaluate_chain, evaluate_expr
from tcadvisor.index.variants import build_values, configure_options

V = {"A": "1", "B": False, "N": "3", "HEX": "0x10", "EMPTY": "", "ALIAS": "N + 1", "FN": "1"}


def test_expressions():
    assert evaluate_expr("defined(A)", V) == 1 and evaluate_expr("defined A", V) == 1
    assert evaluate_expr("defined(B)", V) == 0 and evaluate_expr("B", V) == 0
    assert evaluate_expr("N > 2 && HEX == 16", V) == 1
    assert evaluate_expr("10UL >= 0xAu", V) == 1
    assert evaluate_expr("!(A) || N < 1", V) == 0
    assert evaluate_expr("(N + 1) * 2 - 8 == 0", V) == 1
    assert evaluate_expr("ALIAS == 4", V) == 1
    assert evaluate_expr("EMPTY", V) == 1
    assert evaluate_expr("N ? 5 : 6", V) == 5


def test_unknown_is_three_valued():
    assert evaluate_expr("UNKNOWN > 2", V) is None
    assert evaluate_expr("defined(UNKNOWN)", V) is None
    assert evaluate_expr("B && UNKNOWN", V) == 0  # false && unknown = false
    assert evaluate_expr("A || UNKNOWN", V) == 1  # true || unknown = true
    assert evaluate_expr("A && UNKNOWN", V) is None
    assert evaluate_expr("FN(2)", V) is None  # function-like macro
    assert evaluate_expr("__has_include(<x.h>)", V) is None
    assert evaluate_expr("'a' == 97", V) is None
    assert evaluate_expr("A &&", V) is None  # malformed


def test_chains():
    assert evaluate_chain("#ifdef A", V) is True
    assert evaluate_chain("#ifndef A", V) is False
    assert evaluate_chain("#ifdef B / #else", V) is True
    assert evaluate_chain("#if N == 1 / #elif N == 3", V) is True
    assert evaluate_chain("#if N == 3 / #elif A / #else", V) is False
    assert evaluate_chain("#ifdef UNKNOWN / #else", V) is None
    assert evaluate(["#ifdef A", "#if N > 5"], V) is False
    assert evaluate(["#ifdef A", "#if UNKNOWN"], V) is None


def test_automake_conditions():
    vals = {"AM:PRO": False, "AM:EXTRA": True}
    assert am_condition(["PRO"], vals) is False and am_condition(["!PRO"], vals) is True
    assert am_condition(["EXTRA", "PRO"], vals) is False and am_condition(["OTHER"], vals) is None
    assert am_condition([], vals) is True


def test_configure_options_and_build_values(tmp_path):
    assert configure_options(["--enable-x", "--disable-y", "--with-z=/opt", "--without-w", "--prefix=/usr",
                              "--enable-q=no"]) == {"--enable-x": True, "--enable-y": False, "--with-z": "/opt",
                                                     "--with-w": False, "--enable-q": False}
    b = tmp_path / "b"
    b.mkdir()
    (b / "config.status").write_text('S["PRO_TRUE"]="#"\nS["PRO_FALSE"]=""\nS["NET_TRUE"]=""\nS["NET_FALSE"]="#"\n')
    (b / "config.log").write_text("## Command line ##\n\n  $ ../configure --enable-net --disable-pro\n")
    (b / "config.h").write_text("/* #undef HAVE_PRO */\n#define HAVE_NET 1\n#define VERSION \"1.0\"\n")
    vals = build_values(tmp_path, {"name": "x", "build_dir": str(b)})
    assert vals["AM:PRO"] is False and vals["AM:NET"] is True
    assert vals["--enable-net"] is True and vals["--enable-pro"] is False
    assert vals["HAVE_PRO"] is False and vals["HAVE_NET"] == "1" and vals["VERSION"] == '"1.0"'
