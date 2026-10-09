"""US2: each risk group fires on its characteristic change."""
from conftest import groups_for


def _subs(r, name):
    return {(x["risk_group"], x["sub_reason"]) for s in r["changed_symbols"]
            if s["symbol"]["qualified_name"] == name for x in s["risks"]}


def test_abi_member_reorder(project):
    project.edit("include/door/state.h", "    int id;\n    bool locked;", "    bool locked;\n    int id;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("abi_layout", "member_change") in _subs(r, "DoorState")
    # shared header -> users in both libraries and translation units including it
    names = {n["symbol"]["qualified_name"] for n in r["impact_nodes"]}
    assert {"unlockDoor", "RemoteDoorLock::apply"} <= names
    assert any(c["risk_group"] == "abi_layout" and c["priority"] == "P1" for c in r["test_case_candidates"])


def test_signature_change(project):
    project.edit("include/door/util.h", "int clampRetries(int n);", "int clampRetries(long n);")
    project.edit("src/util.cpp", "int clampRetries(int n) {", "int clampRetries(long n) {")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("abi_layout", "signature_change") in _subs(r, "clampRetries")


def test_thread_safety_mutex(project):
    project.edit("src/util.cpp", '#include "door/util.h"', '#include "door/util.h"\n#include <mutex>\nstatic std::mutex g_m;')
    project.edit("src/util.cpp", "    if (n > 3) return 3;", "    std::lock_guard<std::mutex> g(g_m);\n    if (n > 3) return 3;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("thread_safety", "mutex") in _subs(r, "clampRetries")
    assert any(c["risk_group"] == "thread_safety" and c["priority"] == "P1" for c in r["test_case_candidates"])


def test_exception_safety_noexcept_removed_and_throw(project):
    project.edit("include/door/util.h", "int clampRetries(int n);", "int clampRetries(int n) noexcept;")
    project.edit("src/util.cpp", "int clampRetries(int n) {", "int clampRetries(int n) noexcept {")
    project.commit()
    project.edit("include/door/util.h", "int clampRetries(int n) noexcept;", "int clampRetries(int n);")
    project.edit("src/util.cpp", "int clampRetries(int n) noexcept {", "int clampRetries(int n) {")
    project.edit("src/util.cpp", "    return n;", "    if (n < 0) throw 1;\n    return n;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    subs = _subs(r, "clampRetries")
    assert ("exception_safety", "noexcept_change") in subs
    assert ("exception_safety", "throw_added") in subs


def test_ownership_raw_pointer_and_move(project):
    project.edit("src/lock.cpp", "    RemoteDoorLock l;\n    return handleResponse(l, code);",
                 "    RemoteDoorLock* l = new RemoteDoorLock();\n    int r = handleResponse(*l, code);\n"
                 "    delete l;\n    return r;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert ("ownership_lifetime", "raw_pointer") in _subs(r, "dispatch")


def test_build_config_ifdef(project):
    project.edit("src/util.cpp", "    return n;", "#ifdef DOOR_SAFE_MODE\n    if (n < 0) return 0;\n#endif\n    return n;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert "build_config" in groups_for(r, "clampRetries")
    # DOOR_SAFE_MODE is never defined -> the guarded branch is unanalysed: flagged
    assert any(f["category"] == "build_config_incomplete_macro" for f in r["uncertainty_flags"])


def test_cmake_change_is_build_config_target(project):
    project.edit("CMakeLists.txt", "set(CMAKE_CXX_STANDARD 14)", "set(CMAKE_CXX_STANDARD 17)")
    project.commit()
    project.configure()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    root = r["changed_symbols"][0]
    assert root["symbol"]["kind"] == "file" and root["risks"][0]["risk_group"] == "build_config"
    assert root["risks"][0]["sub_reason"] == "target"


def test_stale_compile_db_is_prerequisite_error(project):
    import os, time
    future = time.time() + 100
    os.utime(project.repo / "CMakeLists.txt", (future, future))
    project.analyze("--working-tree", expect=1)
    project.analyze("--working-tree", "--allow-stale-compile-db")
