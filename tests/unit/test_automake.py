"""Spec 012 US2: Makefile.am / configure.ac reader (no automake run)."""
from pathlib import Path

from tcadvisor.index.automake import detect_build_system, is_build_file, load_automake_model, read_configure


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def test_products_sources_conditions_and_deps(tmp_path):
    _write(tmp_path, {
        "configure.ac": "AC_INIT([m],[1])\nAC_ARG_ENABLE([pro])\nAC_ARG_WITH([ssl])\nAM_CONDITIONAL([PRO], [true])\n"
                        "AM_CONDITIONAL([HAS_EXTRA], [true])\nAC_DEFINE([HAVE_X], [1])\nAC_CONFIG_HEADERS([config.h])\n"
                        "AC_CONFIG_FILES([Makefile src/Makefile extra/Makefile])\n",
        "Makefile.am": "SUBDIRS = src\nif HAS_EXTRA\nSUBDIRS += extra\nendif\n",
        "src/Makefile.am": "# comment\nCOMMON = a.c \\\n  b.c\nlib_LTLIBRARIES = libcore.la\n"
                           "libcore_la_SOURCES = $(COMMON) core.h\nif PRO\nlibcore_la_SOURCES += pro.c\nelse\n"
                           "libcore_la_SOURCES += basic.c\nendif\nbin_PROGRAMS = tool\ntool_SOURCES = tool.c\n"
                           "tool_LDADD = libcore.la -lm\ncheck_PROGRAMS = t_core\nt_core_SOURCES = t_core.c\n"
                           "noinst_PROGRAMS = helper\ninclude extra.am\n",
        "src/extra.am": "helper_SOURCES = helper.c\n",
        "extra/Makefile.am": "noinst_LIBRARIES = libx.a\nlibx_a_SOURCES = x.c $(shell ls *.c)\n",
    })
    m = load_automake_model(tmp_path)
    t = m.targets.targets
    assert set(t) == {"libcore", "tool", "t_core", "helper", "libx"}
    src = tmp_path / "src"
    assert t["libcore"].sources == {src / n for n in ("a.c", "b.c", "core.h", "pro.c", "basic.c")}
    assert t["tool"].dependencies == {"libcore"}
    assert t["helper"].sources == {src / "helper.c"}
    assert m.source_conditions[src / "pro.c"] == [["PRO"]]
    assert m.source_conditions[src / "basic.c"] == [["!PRO"]]
    assert m.source_conditions[src / "a.c"] == [[]]
    assert m.source_conditions[tmp_path / "extra" / "x.c"] == [["HAS_EXTRA"]]  # conditional SUBDIRS
    assert m.test_sources == {src / "t_core.c"}
    assert any("$(shell" in u.construct and u.file == "extra/Makefile.am" for u in m.unresolved)
    assert m.configure.am_conditionals.keys() == {"PRO", "HAS_EXTRA"}
    assert set(m.configure.enables) == {"--enable-pro", "--with-ssl"} and "HAVE_X" in m.configure.defines
    assert m.configure.config_headers == ["config.h"]
    assert "configure.ac" in m.build_files and len(m.fingerprint) == 64


def test_default_source_and_duplicate_names(tmp_path):
    _write(tmp_path, {"configure.ac": "AC_INIT([m],[1])\n", "Makefile.am": "SUBDIRS = a b\n",
                      "a/Makefile.am": "bin_PROGRAMS = tool\n", "b/Makefile.am": "bin_PROGRAMS = tool\n"})
    t = load_automake_model(tmp_path).targets.targets
    assert t["tool"].sources == {tmp_path / "a" / "tool.c"}
    assert t["b/tool"].sources == {tmp_path / "b" / "tool.c"}


def test_unknown_variable_is_unresolved(tmp_path):
    _write(tmp_path, {"Makefile.am": "bin_PROGRAMS = app\napp_SOURCES = main.c $(GENERATED_SRC)\n"})
    m = load_automake_model(tmp_path)
    assert m.targets.targets["app"].sources == {tmp_path / "main.c"}
    assert [u.construct for u in m.unresolved] == ["$(GENERATED_SRC)"]


def test_detection_and_build_files(tmp_path):
    assert detect_build_system(tmp_path) is None
    (tmp_path / "configure.ac").write_text("AC_INIT([m],[1])\n")
    assert detect_build_system(tmp_path) == "autotools"
    (tmp_path / "CMakeLists.txt").write_text("project(x)\n")
    assert detect_build_system(tmp_path) == "cmake"
    assert all(is_build_file(f) for f in ("Makefile.am", "sub/x.am", "m4/ax.m4", "configure.ac", "recipe_1.0.bb",
                                          "a.bbappend", "CMakeLists.txt", "x.cmake"))
    assert not is_build_file("src/main.c")
    assert read_configure(tmp_path / "nope").am_conditionals == {}
