"""Spec 008 US2: a reader hidden behind an inline accessor is reported as the accessor's callers."""
FILES = {
    "include/door/gate.h": """#pragma once
class Gate {
public:
    void Open(int n);
    bool Ready() const { return ready_; }
    int level() const {
        return level_;
    }
private:
    bool ready_ = false;
    int level_ = 0;
};
""",
    "src/gate.cpp": """#include "door/gate.h"
void Gate::Open(int n) {
    ready_ = true;
    level_ = n;
}
""",
    "src/gate_user.cpp": """#include "door/gate.h"
int gate_user(const Gate& g) {
    if (g.Ready()) {
        return 1;
    }
    return 0;
}
int level_user(const Gate& g) {
    return g.level() * 2;
}
""",
}


def _setup(project):
    project.write(FILES)
    project.edit("CMakeLists.txt", "src/handlers.cpp)", "src/handlers.cpp src/gate.cpp src/gate_user.cpp)")
    project.commit("gate")
    project.configure()


def _cases(r, pattern):
    return [c for c in r["test_case_candidates"] if c.get("pattern") == pattern]


def test_reader_behind_inline_getter(project):
    _setup(project)
    project.edit("src/gate.cpp", "    ready_ = true;\n", "")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    hits = [c for c in _cases(r, "removed_write") if c["evidence"][0]["qualified_name"] == "gate_user"]
    assert hits, [(c.get("pattern"), c["evidence"][0]["qualified_name"]) for c in r["test_case_candidates"]]
    assert "accessor `Ready`" in hits[0]["description"]


def test_multiline_getter_expanded(project):
    _setup(project)
    project.edit("src/gate.cpp", "    level_ = n;\n", "    level_ = n + 1;\n")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    names = {c["evidence"][0]["qualified_name"] for c in r["test_case_candidates"]}
    assert "level_user" in names, sorted(names)
