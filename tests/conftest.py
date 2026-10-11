"""Synthetic C++/CMake fixture project (plan.md: one fixture per risk-group rule)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tcadvisor.cli.main import main as cli_main

BASE_FILES = {
    "CMakeLists.txt": """cmake_minimum_required(VERSION 3.10)
project(Door CXX)
set(CMAKE_CXX_STANDARD 14)
add_library(DoorLock src/lock.cpp src/util.cpp src/handlers.cpp)
target_include_directories(DoorLock PUBLIC include)
add_library(DoorUnlock src/unlock.cpp)
target_include_directories(DoorUnlock PUBLIC include)
add_executable(DoorTests tests/test_main.cpp)
target_link_libraries(DoorTests DoorLock DoorUnlock)
""",
    "include/door/state.h": """#pragma once
struct DoorState {
    int id;
    bool locked;
    int retries;
};
""",
    "include/door/util.h": """#pragma once
int clampRetries(int n);
template <typename T>
T maxOf(T a, T b) { return a > b ? a : b; }
""",
    "include/door/lock.h": """#pragma once
#include "door/state.h"

class ILock {
public:
    virtual ~ILock() {}
    virtual bool apply(DoorState& s) = 0;
};

class RemoteDoorLock : public ILock {
public:
    bool apply(DoorState& s) override;
    int processOrderResp(int code);
private:
    int retries_ = 0;
};

int handleResponse(RemoteDoorLock& lock, int code);
int dispatch(int code);
""",
    "include/door/handlers.h": """#pragma once
class IHandler {
public:
    virtual ~IHandler() {}
    virtual void onEvent(int code) = 0;
};
class AuditHandler : public IHandler {
public:
    void onEvent(int code) override;
    int last = 0;
};
void registerTimer(void (*cb)(int));
void onTimer(int tick);
void setupTimers();
""",
    "src/util.cpp": """#include "door/util.h"
int clampRetries(int n) {
    if (n > 3) return 3;
    return n;
}
""",
    "src/lock.cpp": """#include "door/lock.h"
#include "door/util.h"

// Processes the response of a lock order.
int RemoteDoorLock::processOrderResp(int code) {
    retries_ = clampRetries(retries_ + 1);
    if (code == 0) {
        return 0;
    }
    return code + retries_;
}

bool RemoteDoorLock::apply(DoorState& s) {
    s.locked = processOrderResp(s.id) == 0;
    return s.locked;
}

int handleResponse(RemoteDoorLock& lock, int code) {
    return lock.processOrderResp(code);
}

int dispatch(int code) {
    RemoteDoorLock l;
    return handleResponse(l, code);
}
""",
    "src/handlers.cpp": """#include "door/handlers.h"
void AuditHandler::onEvent(int code) {
    last = code;
}
static void (*g_cb)(int) = nullptr;
void registerTimer(void (*cb)(int)) { g_cb = cb; }
void onTimer(int tick) {
    (void)tick;
}
void setupTimers() { registerTimer(&onTimer); }
""",
    "src/unlock.cpp": """#include "door/state.h"
int unlockDoor(DoorState& s) {
    s.locked = false;
    return s.id;
}
""",
    "tests/test_main.cpp": """int main() { return 0; }
""",
}


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


class Project:
    def __init__(self, root: Path):
        self.root = root
        self.repo = root / "repo"
        self.build = root / "build"
        self.out = root / "out"
        self.cache = root / "cache"

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

    def edit(self, rel: str, old: str, new: str) -> None:
        p = self.repo / rel
        text = p.read_text()
        assert old in text, f"{old!r} not in {rel}"
        p.write_text(text.replace(old, new, 1))

    def commit(self, msg: str = "change") -> None:
        _run(["git", "add", "-A"], self.repo)
        _run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", msg], self.repo)

    def configure(self) -> None:
        q = self.build / ".cmake" / "api" / "v1" / "query"
        q.mkdir(parents=True, exist_ok=True)
        (q / "codemodel-v2").touch()
        _run(["cmake", "-S", str(self.repo), "-B", str(self.build), "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
              "-DCMAKE_CXX_COMPILER=clang++"], self.root)

    def analyze(self, *extra: str, expect: int = 0) -> dict:
        args = ["analyze", "--repo", str(self.repo), "--build-dir", str(self.build), "--output-dir", str(self.out),
                "--cache-dir", str(self.cache), "-q", *extra]
        rc = cli_main(args)
        assert rc == expect, f"exit {rc}"
        if rc != 0:
            return {}
        return json.loads((self.out / "report.json").read_text())


@pytest.fixture
def project(tmp_path: Path) -> Project:
    if not shutil.which("cmake"):
        pytest.skip("cmake not available")
    pr = Project(tmp_path)
    pr.repo.mkdir()
    _run(["git", "init", "-q"], pr.repo)
    pr.write(BASE_FILES)
    pr.commit("base")
    pr.configure()
    return pr


def cases_for(report: dict, name: str) -> list[dict]:
    return [c for c in report["test_case_candidates"] if c["evidence"][0].get("qualified_name") == name]


def groups_for(report: dict, name: str) -> set[str]:
    out = set()
    for s in report["changed_symbols"]:
        if s["symbol"]["qualified_name"] == name:
            out |= {r["risk_group"] for r in s["risks"]}
    return out
