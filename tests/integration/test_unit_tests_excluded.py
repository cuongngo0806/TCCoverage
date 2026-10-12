"""include_tests (default off): the report is about the product code, not its unit tests."""
import json

TEST_SRC = """#include "door/util.h"
#define TEST_F(suite, name) void suite##_##name()
TEST_F(DoorTest, Clamp) { clampRetries(5); }
int main() { DoorTest_Clamp(); return 0; }
"""


def _files(r):
    return {c["evidence"][0].get("file_path") or c["evidence"][0]["from_symbol"]["file_path"]
            for c in r["test_case_candidates"]}


def test_unit_tests_left_out_by_default(project):
    project.write({"tests/test_main.cpp": TEST_SRC})
    project.commit("tests")
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n >= 5) return 5;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--include-tests")
    assert "tests/test_main.cpp" in _files(r)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert "tests/test_main.cpp" not in _files(r) and _files(r)
    assert all(not n["symbol"]["file_path"].startswith("tests/") for n in r["impact_nodes"])
    assert any("unit-test code left out" in n for n in r["run_notes"])


def test_changed_test_code_is_out_of_scope(project):
    project.write({"tests/test_main.cpp": TEST_SRC})
    project.commit("tests")
    project.edit("tests/test_main.cpp", "clampRetries(5)", "clampRetries(6)")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert r["test_case_candidates"] == []
    assert any(o["path"] == "tests/test_main.cpp" and "include_tests" in o["reason"] for o in r["out_of_scope"])
    (project.repo / ".tcadvisor").mkdir()
    (project.repo / ".tcadvisor" / "config.json").write_text(json.dumps({"include_tests": True}))
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert r["test_case_candidates"]
