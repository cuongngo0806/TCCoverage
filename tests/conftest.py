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


_REPORTS: list[dict] = []  # every report the suite produced: its sentences must all have a translation


def pytest_sessionfinish(session, exitstatus):
    """Report language gate: a sentence the pipeline emits without a `report/l10n/vi_*.py` entry fails the run."""
    from tcadvisor.report.l10n import Translator, localize
    T = Translator("vi")
    for r in _REPORTS:
        localize(r, T)
    if T.misses():
        print("\nuntranslated report sentence(s) (add them to src/tcadvisor/report/l10n/vi_*.py):")
        for text in sorted(T.misses()):
            print(f"  {text}")
        session.exitstatus = 1


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
                "--exact-output-dir", "--cache-dir", str(self.cache), "-q", *extra]
        if "--graph" not in extra:  # the default (codegraph) needs codegraph installed
            args += ["--graph", "clang"]
        if "--language" not in extra:  # assertions read the English text; report language tests pass --language
            args += ["--language", "en"]
        rc = cli_main(args)
        assert rc == expect, f"exit {rc}"
        if rc != 0:
            return {}
        report = json.loads((self.out / "report.json").read_text())
        _REPORTS.append(report)
        return report


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


# ---- spec 012: synthetic autotools module (configure.ac + Makefile.am, two variants) -------------------------------
AUTOTOOLS_FILES = {
    ".gitignore": "Makefile.in\n/configure\n/configure~\naclocal.m4\nautom4te.cache/\nbuild-aux/\nm4/\nconfig.h.in\n"
                  "config.h.in~\n",
    "configure.ac": """AC_INIT([remote], [1.0])
AC_CONFIG_AUX_DIR([build-aux])
AC_CONFIG_MACRO_DIRS([m4])
AM_INIT_AUTOMAKE([foreign subdir-objects])
AC_PROG_CC
LT_INIT
AC_ARG_ENABLE([feature-x], AS_HELP_STRING([--enable-feature-x], [pro feature]), [], [enable_feature_x=no])
AM_CONDITIONAL([FEATURE_X], [test "x$enable_feature_x" = xyes])
AS_IF([test "x$enable_feature_x" = xyes], [AC_DEFINE([HAVE_FEATURE_X], [1], [pro feature])])
AC_CONFIG_HEADERS([config.h])
AC_CONFIG_FILES([Makefile lib/Makefile app/Makefile])
AC_OUTPUT
""",
    "Makefile.am": "ACLOCAL_AMFLAGS = -I m4\nSUBDIRS = lib app\n",
    "lib/Makefile.am": """lib_LTLIBRARIES = libremote.la
libremote_la_SOURCES = remote.c remote.h
libremote_la_CPPFLAGS = -I$(top_builddir)
if FEATURE_X
libremote_la_SOURCES += pro.c
endif
""",
    "app/Makefile.am": """bin_PROGRAMS = remoteapp
remoteapp_SOURCES = main.c
remoteapp_CPPFLAGS = -I$(top_srcdir)/lib
remoteapp_LDADD = ../lib/libremote.la
""",
    "lib/remote.h": "int remote_send(int code);\nint remote_level(int code);\nint pro_boost(int code);\n",
    "lib/remote.c": """#include "config.h"
#include "remote.h"

int remote_level(int code) {
    if (code > 3) return 3;
    return code;
}

int remote_send(int code) {
    int level = remote_level(code);
#ifdef HAVE_FEATURE_X
    level += pro_boost(level);
#endif
#if UNKNOWN_LIMIT > 2
    level -= 1;
#endif
    return level;
}
""",
    "lib/pro.c": "#include \"remote.h\"\nint pro_boost(int code) {\n    return code * 2;\n}\n",
    "lib/orphan.c": "int orphan_helper(int x) {\n    return x + 1;\n}\n",
    "app/main.c": """#include "remote.h"

int dispatch(int code) {
    return remote_send(code);
}

int main(void) {
    return dispatch(1);
}
""",
}


class AutotoolsProject(Project):
    """A git repo with an autotools module; `make_variant(variant, *configure_args)` builds it out of tree (VPATH) with
    `make V=1` and keeps the log, as a Yocto `log.do_compile` would."""

    def __init__(self, root: Path):
        super().__init__(root)
        self.logs: dict[str, Path] = {}

    def bootstrap(self) -> None:
        _run(["autoreconf", "-fi"], self.repo)

    def make_variant(self, variant: str, *configure_args: str) -> Path:
        b = self.root / f"b-{variant}"
        b.mkdir(exist_ok=True)
        _run([str(self.repo / "configure"), *configure_args], b)
        log = self.root / f"build-{variant}.log"
        res = subprocess.run(["make", "V=1"], cwd=b, capture_output=True, text=True)
        log.write_text(res.stdout + res.stderr)
        assert res.returncode == 0, res.stderr[-2000:]
        self.logs[variant] = log
        return log

    def analyze(self, *extra: str, expect: int = 0) -> dict:
        args = ["analyze", "--repo", str(self.repo), "--output-dir", str(self.out), "--exact-output-dir",
                "--cache-dir", str(self.cache), "-q", "--graph", "clang", "--language", "en", *extra]
        rc = cli_main(args)
        assert rc == expect, f"exit {rc}"
        if rc != 0:
            return {}
        report = json.loads((self.out / "report.json").read_text())
        _REPORTS.append(report)
        return report


@pytest.fixture
def autotools_project(tmp_path: Path) -> AutotoolsProject:
    if not all(shutil.which(t) for t in ("autoreconf", "libtoolize", "make", "cc")):
        pytest.skip("autotools (autoconf, automake, libtool, make, cc) not available")
    pr = AutotoolsProject(tmp_path)
    pr.repo.mkdir()
    _run(["git", "init", "-q"], pr.repo)
    pr.write(AUTOTOOLS_FILES)
    pr.bootstrap()
    pr.commit("base")
    return pr
