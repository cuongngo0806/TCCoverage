"""Spec 010 US3: state written under a condition the edit changed -> readers of that state."""
FILES = {
    "include/door/cfg.h": """#pragma once
struct Config {
    bool longKey = true;
    int limit = 0;
};
void apply(Config* g, int n);
int key_user(const Config& c);
""",
    "src/cfg.cpp": """#include "door/cfg.h"
void apply(Config* g, int n) {
    if (n % 2 == 0) g->longKey = false;
    g->limit = n;
}
""",
    "src/cfg_user.cpp": """#include "door/cfg.h"
int key_user(const Config& c) {
    return c.longKey ? 8 : 4;
}
""",
}


def test_conditional_write_names_reader(project):
    project.write(FILES)
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/cfg.cpp src/cfg_user.cpp)")
    project.commit("cfg")
    project.configure()
    project.edit("src/cfg.cpp", "n % 2 == 0", "n % 2 == 1")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    hits = [c for c in r["test_case_candidates"] if c.get("pattern") == "conditional_write"]
    assert any(c["evidence"][0]["qualified_name"] == "key_user" for c in hits), \
        [(c.get("pattern"), c["evidence"][0]["qualified_name"]) for c in r["test_case_candidates"]]
    assert all(c["priority"] in ("P2", "P3") for c in hits)


def test_no_conditional_write_without_condition_edit(project):
    project.write(FILES)
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/cfg.cpp src/cfg_user.cpp)")
    project.commit("cfg")
    project.configure()
    project.edit("src/cfg.cpp", "g->limit = n;", "g->limit = n + 1;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert not [c for c in r["test_case_candidates"] if c.get("pattern") == "conditional_write"]
