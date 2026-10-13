"""configure.ac + Makefile.am reader (spec 012 US2, research R3): build products → the same `TargetModel` the CMake
File API reader returns, without running automake (which needs matching autotools versions and writes into the
module — Principle VIII).

Read: primaries `<dir>_{PROGRAMS,LTLIBRARIES,LIBRARIES}`, `<canon>_SOURCES` (+ `nodist_`, `EXTRA_`; default
`<name>.c`), `_LDADD`/`_LIBADD` on internal `.la`/`.a` (product dependencies), `SUBDIRS` recursion, `if COND` /
`else` / `endif` (per source: the automake conditionals that must hold), `include`. From configure.ac:
`AC_CONFIG_FILES`, `AM_CONDITIONAL`, `AC_ARG_ENABLE` / `AC_ARG_WITH`, `AC_DEFINE`, `AC_CONFIG_HEADERS`.
Anything else in a product / sources / SUBDIRS value (`$(shell ...)`, variables defined elsewhere, m4 output) is
reported as `unresolved` (→ uncertainty flag `build_description_unresolved`), never guessed (Principle IV).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from tcadvisor.index.cmake_targets import TargetInfo, TargetModel

_PRIMARY = re.compile(r"^(?:(?:nobase|dist|nodist)_)*([A-Za-z0-9]+)_(PROGRAMS|LTLIBRARIES|LIBRARIES)$")
_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(\+=|:=|\?=|=)\s*(.*)$")
_VAR = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)|\$\{([A-Za-z_][A-Za-z0-9_]*)\}|@([A-Za-z_][A-Za-z0-9_]*)@")
_FUNC = re.compile(r"\$\((?:shell|wildcard|patsubst|subst|filter|foreach|call)\s[^)]*\)")
_BUILTIN = {"srcdir": "", "top_srcdir": None, "builddir": "", "top_builddir": None, "abs_srcdir": "",
            "abs_top_srcdir": None, "EXEEXT": "", "OBJEXT": "o", "LIBEXT": "a"}
_M4_CALL = r"{name}\(\s*\[?([^\],)\s]+)"
BUILD_FILE_NAMES = ("configure.ac", "configure.in", "Makefile.am")
BUILD_FILE_SUFFIXES = (".am", ".m4", ".bb", ".bbappend", ".bbclass", ".inc")


def is_build_file(rel: str) -> bool:
    """Files whose change is a build-configuration change (CMake or autotools / Yocto)."""
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    return (name == "CMakeLists.txt" or name.endswith(".cmake") or name in BUILD_FILE_NAMES
            or name.endswith(BUILD_FILE_SUFFIXES))


@dataclass
class Unresolved:
    file: str  # repo-relative
    line: int
    construct: str


@dataclass
class ConfigureInfo:
    config_files: list[str] = field(default_factory=list)
    am_conditionals: dict[str, int] = field(default_factory=dict)  # name -> configure.ac line
    enables: dict[str, int] = field(default_factory=dict)  # --enable-x / --with-y -> line
    defines: dict[str, int] = field(default_factory=dict)  # AC_DEFINE names -> line
    config_headers: list[str] = field(default_factory=list)


@dataclass
class BuildModel:
    system: str  # cmake | autotools
    targets: TargetModel
    unresolved: list[Unresolved] = field(default_factory=list)
    build_files: list[str] = field(default_factory=list)  # repo-relative
    fingerprint: str = ""
    configure: ConfigureInfo = field(default_factory=ConfigureInfo)
    # per source file: alternatives of automake conditions under which it is built (one list per product use);
    # [] in the list = built unconditionally by that product
    source_conditions: dict[Path, list[list[str]]] = field(default_factory=dict)
    dir_conditions: dict[Path, list[str]] = field(default_factory=dict)  # conditions inherited from SUBDIRS
    test_sources: set[Path] = field(default_factory=set)  # sources of check_* products only
    defined_at: dict[str, str] = field(default_factory=dict)  # product -> Makefile.am:line


@dataclass
class _Assign:
    name: str
    op: str
    value: str
    conds: list[str]
    line: int
    file: Path


def _logical_lines(text: str) -> list[tuple[int, str]]:
    out, buf, start = [], "", 0
    for i, raw in enumerate(text.splitlines(), 1):
        if not buf:
            start = i
        if raw.startswith("\t"):  # recipe line of a make rule
            if not buf:
                continue
        line = raw
        if not line.lstrip().startswith("#") and "#" in line:
            line = re.sub(r"(^|\s)##?[^\n]*$", "", line)
        elif line.lstrip().startswith("#"):
            line = ""
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        out.append((start, (buf + line).strip()))
        buf = ""
    if buf:
        out.append((start, buf.strip()))
    return out


def _parse_am(path: Path, repo: Path, unresolved: list[Unresolved], seen: set[Path]) -> list[_Assign]:
    """Assignments of one Makefile.am (with its includes), each tagged with the enclosing conditions."""
    if path in seen or not path.is_file():
        return []
    seen.add(path)
    rel = path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path)
    stack: list[str] = []
    out: list[_Assign] = []
    for ln, line in _logical_lines(path.read_text(encoding="utf-8", errors="replace")):
        if not line:
            continue
        m = re.match(r"^if\s+(!?)\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
        if m:
            stack.append(("!" if m.group(1) else "") + m.group(2))
            continue
        if re.match(r"^else\b", line):
            if stack:
                c = stack.pop()
                stack.append(c[1:] if c.startswith("!") else "!" + c)
            continue
        if re.match(r"^endif\b", line):
            if stack:
                stack.pop()
            continue
        m = re.match(r"^-?include\s+(.+)$", line)
        if m:
            inc = m.group(1).strip()
            inc = inc.replace("$(srcdir)/", "").replace("$(top_srcdir)/", str(repo) + "/")
            inc = inc.replace("$(top_srcdir)", str(repo)).replace("$(srcdir)", ".")
            if "$(" in inc or "@" in inc:
                unresolved.append(Unresolved(rel, ln, f"include {m.group(1).strip()}"))
                continue
            p = Path(inc) if Path(inc).is_absolute() else path.parent / inc
            for a in _parse_am(p.resolve(), repo, unresolved, seen):
                a.conds = stack + a.conds
                out.append(a)
            continue
        m = _ASSIGN.match(line)
        if m:
            out.append(_Assign(m.group(1), m.group(2), m.group(3).strip(), list(stack), ln, path))
    return out


class _Dir:
    def __init__(self, path: Path, repo: Path, unresolved: list[Unresolved]):
        self.path = path
        self.repo = repo
        self.unresolved = unresolved
        self.assigns = _parse_am(path / "Makefile.am", repo, unresolved, set())
        self.rel = (path / "Makefile.am").relative_to(repo).as_posix()

    def values(self, name: str) -> list[tuple[list[str], list[str], int]]:
        """[(tokens, conditions, line)] of every assignment to `name` (expanded)."""
        out = []
        for a in self.assigns:
            if a.name == name:
                out.append((self.expand(a.value, a.line).split(), a.conds, a.line))
        return out

    def expand(self, value: str, line: int, depth: int = 0) -> str:
        top = str(self.repo)

        def sub(m: re.Match) -> str:
            name = m.group(1) or m.group(2) or m.group(3)
            if name in ("top_srcdir", "abs_top_srcdir", "top_builddir"):
                return top
            if name in _BUILTIN:
                return str(self.path) if name in ("srcdir", "abs_srcdir", "builddir") else _BUILTIN[name]
            vals = [a.value for a in self.assigns if a.name == name]
            if vals and depth < 8:
                return " ".join(self.expand(v, line, depth + 1) for v in vals)
            self.unresolved.append(Unresolved(self.rel, line, m.group(0)))
            return ""
        def func(m: re.Match) -> str:
            self.unresolved.append(Unresolved(self.rel, line, m.group(0)[:80]))
            return ""
        return _VAR.sub(sub, _FUNC.sub(func, value))


def canonical(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9@]", "_", name)


def _display(name: str) -> str:
    return re.sub(r"\.(la|a)$", "", name)


def read_configure(repo: Path) -> ConfigureInfo:
    info = ConfigureInfo()
    path = repo / "configure.ac"
    if not path.is_file():
        path = repo / "configure.in"
    if not path.is_file():
        return info
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    def line_of(pos: int) -> int:
        return text.count("\n", 0, pos) + 1
    for m in re.finditer(r"AC_CONFIG_FILES\(\s*\[?([^\])]*)", text):
        info.config_files += m.group(1).split()
    for macro, target, fmt in (("AM_CONDITIONAL", info.am_conditionals, "{}"),
                               ("AC_ARG_ENABLE", info.enables, "--enable-{}"),
                               ("AC_ARG_WITH", info.enables, "--with-{}"),
                               ("AC_DEFINE", info.defines, "{}"), ("AC_DEFINE_UNQUOTED", info.defines, "{}")):
        for m in re.finditer(_M4_CALL.format(name=macro), text):
            target.setdefault(fmt.format(m.group(1).strip("[]")), line_of(m.start()))
    for m in re.finditer(r"A[CM]_CONFIG_HEADERS?\(\s*\[?([^\])]*)", text):
        info.config_headers += [h.split(":")[0] for h in m.group(1).split()]
    del lines
    return info


def load_automake_model(repo: Path) -> BuildModel:
    repo = repo.resolve()
    unresolved: list[Unresolved] = []
    configure = read_configure(repo)
    targets: dict[str, TargetInfo] = {}
    source_conds: dict[Path, list[list[str]]] = {}
    dir_conds: dict[Path, list[str]] = {}
    test_sources_all: dict[Path, bool] = {}
    defined_at: dict[str, str] = {}
    raw_deps: dict[str, set[Path]] = {}
    lib_paths: dict[Path, str] = {}
    build_files: list[str] = []
    product_dirs: dict[str, Path] = {}

    queue: list[tuple[Path, list[str]]] = [(repo, [])]
    visited: set[Path] = set()
    while queue:
        d, inherited = queue.pop(0)
        if d in visited or not (d / "Makefile.am").is_file():
            continue
        visited.add(d)
        dir_conds[d] = inherited
        md = _Dir(d, repo, unresolved)
        build_files.append(md.rel)
        for tokens, conds, _ln in md.values("SUBDIRS"):
            for t in tokens:
                if t == ".":
                    continue
                sub = (d / t).resolve()
                if (sub / "Makefile.am").is_file():
                    queue.append((sub, inherited + conds))
                elif "$" not in t:
                    unresolved.append(Unresolved(md.rel, _ln, f"SUBDIRS entry '{t}' has no Makefile.am"))
        for a in md.assigns:
            pm = _PRIMARY.match(a.name)
            if not pm:
                continue
            where = pm.group(1)
            kind = {"PROGRAMS": "program", "LTLIBRARIES": "ltlibrary", "LIBRARIES": "library"}[pm.group(2)]
            for prod in md.expand(a.value, a.line).split():
                if where == "EXTRA":
                    continue  # products configure may substitute in; their sources follow the same rules
                cname = canonical(prod.rsplit("/", 1)[-1])
                name = _display(prod.rsplit("/", 1)[-1])
                if name in targets and product_dirs.get(name) != d:
                    name = f"{d.relative_to(repo).as_posix()}/{name}" if d != repo else name
                info = targets.setdefault(name, TargetInfo(name, kind, d))
                product_dirs[name] = d
                defined_at[name] = f"{md.rel}:{a.line}"
                prod_conds = inherited + a.conds
                srcs: list[tuple[str, list[str]]] = []
                any_sources = False
                for var in (f"{cname}_SOURCES", f"nodist_{cname}_SOURCES", f"EXTRA_{cname}_SOURCES"):
                    for toks, conds, _l in md.values(var):
                        any_sources = True
                        srcs += [(t, conds) for t in toks]
                if not any_sources:
                    srcs = [(re.sub(r"\.(la|a)$", "", prod.rsplit("/", 1)[-1]) + ".c", [])]
                for s, conds in srcs:
                    p = (d / s).resolve()
                    info.sources.add(p)
                    source_conds.setdefault(p, []).append(prod_conds + conds)
                    test_sources_all[p] = test_sources_all.get(p, True) and where == "check"
                if kind != "program":
                    lib_paths[(d / prod).resolve()] = name
                for var in (f"{cname}_LDADD", f"{cname}_LIBADD"):
                    for toks, _c, _l in md.values(var):
                        raw_deps.setdefault(name, set()).update(
                            (d / t).resolve() for t in toks if t.endswith((".la", ".a")) and not t.startswith("-"))
    for name, deps in raw_deps.items():
        targets[name].dependencies = {lib_paths[p] for p in deps if p in lib_paths} - {name}
    file_to_targets: dict[Path, set[str]] = {}
    for t in targets.values():
        for s in t.sources:
            file_to_targets.setdefault(s, set()).add(t.name)
    cfg_file = repo / "configure.ac" if (repo / "configure.ac").is_file() else repo / "configure.in"
    if cfg_file.is_file():
        build_files.insert(0, cfg_file.name)
    h = hashlib.sha256()
    for rel in sorted(build_files):
        h.update(rel.encode() + b"\0" + (repo / rel).read_bytes())
    return BuildModel("autotools", TargetModel(targets, file_to_targets), unresolved, build_files, h.hexdigest(),
                      configure, source_conds, dir_conds, {p for p, t in test_sources_all.items() if t}, defined_at)


def detect_build_system(repo: Path) -> str | None:
    """`cmake` / `autotools` from the files at the repository root (None: neither)."""
    if (repo / "CMakeLists.txt").is_file():
        return "cmake"
    if (repo / "configure.ac").is_file() or (repo / "configure.in").is_file() or (repo / "Makefile.am").is_file():
        return "autotools"
    return None
