"""US1: impact map + evidence-backed test case list."""
from conftest import cases_for


def test_function_change_reaches_direct_and_indirect_callers(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n >= 5) return 5;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    hops = {n["symbol"]["qualified_name"]: n["hop_distance"] for n in r["impact_nodes"]}
    assert hops["clampRetries"] == 0
    assert hops["RemoteDoorLock::processOrderResp"] == 1
    assert hops["handleResponse"] == 2 and hops["RemoteDoorLock::apply"] == 2
    assert "dispatch" not in hops  # 3 hops away, beyond default depth 2
    assert all(c["evidence"] for c in r["test_case_candidates"])
    direct = cases_for(r, "RemoteDoorLock::processOrderResp")
    assert direct and direct[0]["evidence"][1]["relation"] == "call"
    assert any("n = 4, 5, 6" in h for c in cases_for(r, "clampRetries") for h in c["corner_cases"])
    assert r["no_detected_impact"] is False
    assert (project.out / "report.md").read_text().count("TC-0001") == 1
    assert "mermaid" in (project.out / "report.md").read_text()
    assert (project.out / "report.html").exists()


def test_max_hop_depth_option(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--max-hop-depth", "3")
    assert {n["symbol"]["qualified_name"]: n["hop_distance"] for n in r["impact_nodes"]}["dispatch"] == 3


def test_comment_and_format_only_change_has_no_impact(project):
    project.edit("src/lock.cpp", "// Processes the response of a lock order.", "// Handles the lock order response.")
    project.edit("src/lock.cpp", "    if (code == 0) {", "    if (code == 0)   {  // fast path")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert r["no_detected_impact"] is True
    assert r["test_case_candidates"] == [] and r["uncertainty_flags"] == []
    assert "No detected impact" in (project.out / "report.md").read_text()


def test_working_tree_mode(project):
    project.edit("src/util.cpp", "return n;", "return n < 0 ? 0 : n;")
    r = project.analyze("--working-tree")
    assert [s["symbol"]["qualified_name"] for s in r["changed_symbols"]] == ["clampRetries"]


def test_explicit_symbol_mode_uses_only_that_symbol(project):
    r = project.analyze("--symbols", "RemoteDoorLock::processOrderResp")
    roots = [n for n in r["impact_nodes"] if n["hop_distance"] == 0]
    assert [n["symbol"]["qualified_name"] for n in roots] == ["RemoteDoorLock::processOrderResp"]
    names = {n["symbol"]["qualified_name"] for n in r["impact_nodes"]}
    assert {"handleResponse", "RemoteDoorLock::apply", "dispatch"} <= names
    assert "clampRetries" not in names  # a callee, not a dependent
    assert r["change_input"]["mode"] == "explicit_symbols"
    assert r["change_input"]["symbols"][0]["qualified_name"] == "RemoteDoorLock::processOrderResp"


def test_explicit_mode_rejects_file_paths(project):
    project.analyze("--symbols", "src/lock.cpp", expect=2)
    project.analyze("--symbols", "doesNotExist", expect=2)


def test_second_run_is_cache_hit_and_deterministic(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 7) return 7;")
    project.commit()
    r1 = project.analyze("--commit-range", "HEAD~1..HEAD")
    r2 = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert r1["cache_hit"] is False and r2["cache_hit"] is True
    assert r1["test_case_candidates"] == r2["test_case_candidates"]
    assert r2["metrics"]["index"]["reparsed"] == 0
    r3 = project.analyze("--commit-range", "HEAD~1..HEAD", "--no-run-cache")
    assert r3["cache_hit"] is False and r3["metrics"]["index"]["reparsed"] == 0
    assert r3["test_case_candidates"] == r1["test_case_candidates"]


def test_incremental_reindex_only_touches_changed_tus(project):
    project.analyze("--working-tree")
    project.edit("src/util.cpp", "return n;", "return n + 0;")
    r = project.analyze("--working-tree")
    assert r["metrics"]["index"]["reparsed"] == 1


def test_prerequisite_failures(project, tmp_path):
    import shutil
    shutil.rmtree(project.build / ".cmake")
    project.analyze("--working-tree", expect=1)
    (project.build / "compile_commands.json").unlink()
    project.analyze("--working-tree", expect=1)


def test_output_dir_inside_repo_is_rejected(project):
    from tcadvisor.cli.main import main
    rc = main(["analyze", "--repo", str(project.repo), "--build-dir", str(project.build), "--working-tree",
               "--output-dir", str(project.repo / "out"), "--cache-dir", str(project.cache), "-q"])
    assert rc == 2


def test_llm_unavailable_degrades_gracefully(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 9) return 9;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--llm", "--llm-endpoint", "http://127.0.0.1:9")
    assert r["llm_enabled"] is True and r["llm_degraded"] is True and r["llm_token_usage"] is None
    assert r["test_case_candidates"] and any("degraded" in n for n in r["run_notes"])
    assert (project.out / "llm-prompt.log").exists()


def test_external_llm_requires_approval(project):
    project.analyze("--working-tree", "--llm", "--llm-endpoint", "https://api.example.com", expect=2)


def test_changed_call_site_impacts_the_callee(project):
    project.edit("src/lock.cpp", "    return handleResponse(l, code);", "    return handleResponse(l, code + 1);")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    callee = [n for n in r["impact_nodes"] if n["symbol"]["qualified_name"] == "handleResponse"]
    assert callee and callee[0]["hop_distance"] == 1
    assert callee[0]["edges"][0]["relation"] == "called_by_change"
    # terminal: the callee's own callees/callers are not expanded from there
    assert "RemoteDoorLock::processOrderResp" not in {n["symbol"]["qualified_name"] for n in r["impact_nodes"]}


def test_make_unique_call_site_impacts_the_constructor(project):
    project.write({"include/door/builder.h": "#pragma once\nclass Builder {\npublic:\n    Builder(int* sink);\n"
                   "    int* sink_;\n};\n",
                   "src/builder.cpp": '#include "door/builder.h"\nBuilder::Builder(int* sink) : sink_(sink) {}\n'})
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/builder.cpp)")
    project.edit("src/lock.cpp", '#include "door/util.h"', '#include "door/util.h"\n#include "door/builder.h"\n#include <memory>\n'
                 'static int g_a, g_b;\nstd::unique_ptr<Builder> makeBuilder() { return std::make_unique<Builder>(&g_a); }')
    project.commit()
    project.configure()
    project.edit("src/lock.cpp", "std::make_unique<Builder>(&g_a)", "std::make_unique<Builder>(&g_b)")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    ctor = [n for n in r["impact_nodes"] if n["symbol"]["qualified_name"] == "Builder::Builder"]
    assert ctor and ctor[0]["edges"][0]["relation"] == "called_by_change"
    assert ctor[0]["symbol"]["file_path"] == "src/builder.cpp"  # definition, not the header declaration


def _vendor_change(project):
    vendor = project.root / "vendor" / "vendorlib"
    vendor.mkdir(parents=True)
    (vendor / "api.h").write_text("#pragma once\nextern \"C\" int vendor_send(const char* buf, int len);\n"
                                  "namespace vendor { char* open_channel(int id); }\n")
    project.edit("CMakeLists.txt", "target_include_directories(DoorLock PUBLIC include)",
                 f"target_include_directories(DoorLock PUBLIC include {vendor.parent})")
    project.edit("src/lock.cpp", '#include "door/util.h"', '#include "door/util.h"\n#include "vendorlib/api.h"\n#include <string>')
    project.commit()
    project.configure()
    project.edit("src/lock.cpp", "    return handleResponse(l, code);",
                 "    std::string s(\"x\");\n    vendor_send(s.c_str(), code);\n    vendor::open_channel(code);\n"
                 "    return handleResponse(l, code);")
    project.commit()


def test_changed_call_into_third_party_code_is_flagged(project):
    _vendor_change(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    flags = [f for f in r["uncertainty_flags"] if "outside the repository" in f["reason"]]
    assert len(flags) == 1 and "`vendor_send` (vendorlib/api.h)" in flags[0]["reason"]
    assert flags[0]["category"] == "dynamic_runtime_dependency" and flags[0]["related_symbol"]["file_path"] == "src/lock.cpp"
    assert "vendor_send" not in {n["symbol"]["qualified_name"] for n in r["impact_nodes"]}
    assert any("standard-library call(s) on changed lines" in n for n in r["run_notes"])


def test_third_party_call_yields_a_boundary_case_from_its_declaration(project):
    _vendor_change(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    ext = [c for c in r["test_case_candidates"] if c["sub_reason"] == "external_call"]
    assert len(ext) == 1 and ext[0]["hop_distance"] == 0 and ext[0]["evidence"][0]["qualified_name"] == "dispatch"
    assert ext[0]["risk_group"] == "exception_safety" and ext[0]["priority"] == "P1"
    hints = " | ".join(ext[0]["corner_cases"])
    assert "the `int` result of `vendor_send` is ignored" in hints
    assert "`vendor_send`(`buf`, `len`): boundary lengths" in hints
    assert "`vendor::open_channel` returns `char *`: make it return nullptr" in hints
    assert "`vendor::open_channel` is not noexcept" in hints  # C++ linkage, no noexcept
    assert "`vendor_send` is not noexcept" not in hints  # extern "C"
    # not propagated: callers of dispatch get no external_call case
    assert all(c["hop_distance"] == 0 for c in r["test_case_candidates"] if c["sub_reason"] == "external_call")


def test_contract_file_adds_known_library_behaviour(project):
    _vendor_change(project)
    (project.repo / ".tcadvisor").mkdir()
    (project.repo / ".tcadvisor" / "external-contracts.json").write_text(
        '{"vendor_send": ["returns -EAGAIN when the send queue is full"], "vendor::*": ["not thread-safe"]}')
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    hints = [h for c in r["test_case_candidates"] if c["sub_reason"] == "external_call" for h in c["corner_cases"]]
    assert "Contract: vendor_send: returns -EAGAIN when the send queue is full" in hints
    assert "Contract: vendor::open_channel: not thread-safe" in hints
    (project.repo / ".tcadvisor" / "external-contracts.json").write_text("{not json")
    project.analyze("--commit-range", "HEAD~1..HEAD", expect=2)
