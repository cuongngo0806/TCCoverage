"""US3: affected CMake targets."""


def _names(r):
    return {t["name"]: t for t in r["affected_targets"]}


def test_single_target(project):
    project.edit("src/unlock.cpp", "s.locked = false;", "s.locked = s.id < 0;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    t = _names(r)
    assert t["DoorUnlock"]["relation"] == "compiles_affected_file"
    assert "DoorLock" not in t
    assert t["DoorTests"]["relation"] == "link_to_target"


def test_shared_header_lists_every_target(project):
    project.edit("include/door/state.h", "    int retries;\n", "    int retries;\n    int flags;\n")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    t = _names(r)
    assert {"DoorLock", "DoorUnlock"} <= {k for k, v in t.items() if v["relation"] == "compiles_affected_file"}


def test_targets_scope_reports_out_of_scope(project):
    project.edit("include/door/state.h", "    int retries;\n", "    int retries;\n    int flags;\n")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--targets", "DoorLock")
    assert r["target_scope"] == ["DoorLock"]
    assert any(o["path"] == "src/unlock.cpp" for o in r["out_of_scope"])
    assert all("DoorUnlock" not in c["related_cmake_targets"] or "DoorLock" in c["related_cmake_targets"]
               for c in r["test_case_candidates"])
    project.analyze("--commit-range", "HEAD~1..HEAD", "--targets", "Nope", expect=2)


def test_split_threshold(project):
    project.edit("src/util.cpp", "return n;", "return n + 1;")
    project.edit("src/unlock.cpp", "s.locked = false;", "s.locked = true;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--split-threshold", "1")
    assert r["split_into_modules"] == ["DoorLock", "DoorUnlock"]
    assert {s["symbol"]["qualified_name"] for s in r["changed_symbols"]} == {"clampRetries", "unlockDoor"}
