"""Graph providers (spec 002). Real-tool tests run only when the tool is installed."""
import shutil

import pytest

from tcadvisor.graph.providers.base import ProviderResult, Root, build_overlay, gtest_label
from tcadvisor.graph.providers.codegraph import CodegraphProvider, _choose
from tcadvisor.graph.providers.gitnexus import GitNexusProvider
from tcadvisor.index.clang_index import IndexFacts
from tcadvisor.models import SymbolRef


def _def(name, file, line, qn=None):
    return {"definition": {"id": name, "name": name.split("::")[-1], "filePath": file, "startLine": line,
                           "qualifiedName": qn or name}}


def test_choose_prefers_same_file_and_line_then_qualified_name():
    root = Root("u", "ns::(anonymous)::A::f", "f", "method", "a.cc", 10)
    defs = [_def("x", "b.cc", 10), _def("y", "a.cc", 11), _def("z", "a.cc", 40)]
    assert [d["definition"]["id"] for d in _choose(defs, root)] == ["y"]
    defs = [_def("x", "b.cc", 10, "ns::A::f"), _def("z", "c.cc", 40, "ns::B::f")]
    assert [d["definition"]["id"] for d in _choose(defs, root)] == ["x"]


def test_codegraph_adapter_maps_edges_and_rejects_fake_inheritance(tmp_path, monkeypatch):
    (tmp_path / "u.cc").write_text("class Holder {\n  int a;\n  Cache* cache_;\n};\nclass Impl : public Cache {\n};\n")
    monkeypatch.setenv("TCADVISOR_CODEGRAPH", "/bin/true")
    p = CodegraphProvider(tmp_path, 2)
    data = {"definitions": [{
        "definition": {"id": "c", "name": "Cache", "kind": "class", "filePath": "c.h", "startLine": 3, "qualifiedName": "Cache"},
        "affected": [{"id": "h", "name": "Holder", "kind": "class", "filePath": "u.cc", "startLine": 1},
                     {"id": "i", "name": "Impl", "kind": "class", "filePath": "u.cc", "startLine": 5},
                     {"id": "m", "name": "Get", "kind": "method", "filePath": "c.h", "startLine": 9},
                     {"id": "t", "name": "TEST_F", "kind": "function", "filePath": "u.cc", "startLine": 1}],
        "edges": [{"source": "h", "target": "c", "kind": "extends", "line": 3, "metadata": {"refName": "Cache"}},
                  {"source": "i", "target": "c", "kind": "extends", "line": 5, "metadata": {"refName": "Cache"}},
                  {"source": "c", "target": "m", "kind": "contains"},
                  {"source": "t", "target": "m", "kind": "calls", "line": 2, "provenance": "heuristic"}]}]}
    monkeypatch.setattr(p, "run_json", lambda *a: data)
    res = p.impact([Root("USR_CACHE", "Cache", "Cache", "class", "c.h", 3)])
    rel = {(e.dependent, e.dependency): e.relation for e in res.edges}
    assert rel[("h", "USR_CACHE")] == "uses_type"  # data member, not a base class
    assert rel[("i", "USR_CACHE")] == "inherit_override"
    assert rel[("m", "USR_CACHE")] == "contains"
    assert res.refs["m"].qualified_name == "Cache::Get"
    g = build_overlay(None, IndexFacts(tmp_path), res)
    assert {d.dependent for d in g.dependents["USR_CACHE"]} == {"h", "i", "m"}


def test_gitnexus_cypher_parsing_restores_pipes(tmp_path, monkeypatch):
    monkeypatch.setenv("TCADVISOR_GITNEXUS", "/bin/true")
    p = GitNexusProvider(tmp_path, 2)
    md = "| a | b |\n| --- | --- |\n| Function:x.cc:f~shape:int¦char | 12 |"
    monkeypatch.setattr(p, "run_json", lambda *a: {"markdown": md})
    assert p.cypher("q") == [["Function:x.cc:f~shape:int|char", "12"]]


def test_gtest_label(tmp_path):
    (tmp_path / "t.cc").write_text("#include <x>\nTEST_F(CacheTest, SetCapacity) {\n}\n")
    assert gtest_label(tmp_path, SymbolRef("TEST_F", "function", "t.cc", 2)) == "CacheTest.SetCapacity"
    assert gtest_label(tmp_path, SymbolRef("Foo", "function", "t.cc", 2)) is None


@pytest.mark.skipif(not shutil.which("codegraph"), reason="codegraph not installed")
def test_codegraph_end_to_end(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--graph", "codegraph")
    assert r["graph_provider"] == "codegraph"
    names = {n["symbol"]["qualified_name"] for n in r["impact_nodes"]}
    assert any(n.endswith("processOrderResp") for n in names)
    assert ".codegraph/" in (project.repo / ".git" / "info" / "exclude").read_text()
    assert not [ln for ln in __import__("subprocess").run(["git", "status", "--porcelain"], cwd=project.repo,
                capture_output=True, text=True).stdout.splitlines()]


def test_compile_db_optional_with_provider(project, monkeypatch):
    if not shutil.which("codegraph"):
        pytest.skip("codegraph not installed")
    (project.build / "compile_commands.json").unlink()
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    project.analyze("--commit-range", "HEAD~1..HEAD", expect=1)  # clang graph still requires it
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--graph", "codegraph")
    assert any("reduced accuracy" in n for n in r["run_notes"])
    assert [s["symbol"]["qualified_name"] for s in r["changed_symbols"]] == ["clampRetries"]
