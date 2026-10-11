"""Spec 009 US2/US1: lost side effects reach the readers of the state; edit shapes give concrete corner cases."""
import pytest
from fixtures_us7 import add_state_fixture

# pattern, edit, reader that must be named
SCENARIOS = {
    "removed_write": (("src/store.cpp", "        scheduled_ = true;\n        background();",
                       "        background();"), "Store::pending"),
    "setter_readers": (("src/store.cpp", "    SetCount(Count() + 1);\n    items_.push_back(v);",
                        "    items_.push_back(v);"), "store_user"),
    "lock_coupling": (("src/store.cpp", "int Store::snapshot() {\n    std::lock_guard<std::mutex> g(mu_);\n",
                       "int Store::snapshot() {\n"), "Store::release"),
    "changed_default": (("include/door/store.h", "    int max_items = 16;", "    int max_items = 4;"),
                        "capacity_user"),
    "class_consumer": (("src/store.cpp", "        items_.push_back(v * 2);", "        items_.push_back(v * 3);"),
                       "Store::get"),
}


def _by_pattern(r):
    """(pattern, symbol) -> case, including patterns folded into an existing case ("Also (pattern)")."""
    import re
    out = {}
    for c in r["test_case_candidates"]:
        q = c["evidence"][0]["qualified_name"]
        for p in ([c["pattern"]] if c.get("pattern") else []) + re.findall(r"Also \((\w+)\)", c["description"]):
            out[(p, q)] = c
    return out


@pytest.mark.parametrize("pattern", sorted(SCENARIOS))
def test_state_reader_named(project, pattern):
    add_state_fixture(project)
    (path, old, new), reader = SCENARIOS[pattern]
    project.edit(path, old, new)
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    found = _by_pattern(r)
    assert (pattern, reader) in found, sorted(found)
    c = found[(pattern, reader)]
    assert c["corner_cases"] and "read at" in c["activation_condition"] + c["description"] or c.get("pattern") != pattern
    if c.get("pattern") == pattern:
        assert c["priority"] in ("P2", "P3")


def test_no_state_cases_with_no_patterns(project):
    add_state_fixture(project)
    project.edit("src/store.cpp", "        scheduled_ = true;\n        background();", "        background();")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--no-patterns")
    assert not [c for c in r["test_case_candidates"] if c.get("pattern")]


def test_removed_guard_is_p1_with_reject_input(project):
    add_state_fixture(project)
    project.edit("src/store.cpp", "    if (static_cast<int>(items_.size()) < opts_.max_items) {\n"
                 "        items_.push_back(v * 2);\n    }", "    items_.push_back(v * 2);")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    root = [c for c in r["test_case_candidates"] if c["evidence"][0]["qualified_name"] == "Store::add"
            and c["hop_distance"] == 0 and c["risk_group"] == "logic"]
    assert root and root[0]["priority"] == "P1" and root[0]["sub_reason"] == "removed_guard"
    assert any("Removed condition" in h and "max_items" in h for h in root[0]["corner_cases"])


def test_test_gaps_listed(project):
    add_state_fixture(project)
    project.edit("src/store.cpp", "    return items_[i] / 2;", "    return items_[i] / 4;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert any(g["symbol"]["qualified_name"] == "Store::get" for g in r["test_gaps"])
