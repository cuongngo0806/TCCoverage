"""Build log → compile_commands.json (spec 012 US2, research R2).

Yocto keeps the full compiler command lines of every recipe build in `${WORKDIR}/temp/log.do_compile` (OE's
`autotools.bbclass` configures with `--disable-silent-rules`); a local build gives the same with `make V=1`. This
module reads such a log — plain compiler lines and libtool `libtool: compile:` lines, with `make[N]: Entering
directory` tracking for relative paths — and writes a deterministic compile database. The tool never runs the
build itself (Principle VIII).

Source paths of the build (`${S}` of a Yocto recipe when it is not the workspace itself, e.g. `${WORKDIR}/git`) are
mapped onto the workspace with an explicit `src` prefix, or automatically: the longest leading path whose remainder
exists in the repository. Build-directory paths (`${B}`: generated `config.h`, objects) are kept as they are — the
tool runs on the build host — unless an explicit `maps` entry moves them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from tcadvisor.index.compile_db import CPP_SOURCE_EXT
from tcadvisor.models import PrerequisiteError

_COMPILER = re.compile(r"^(?:.*/)?(?:[\w.+-]+-)?(gcc|g\+\+|cc|c\+\+|clang|clang\+\+|icc|icpc)(?:-\d+(?:\.\d+)*)?$")
_ENTER = re.compile(r"^make(?:\[\d+\])?: Entering directory ['`\"]?(.+?)['\"]?$")
_LEAVE = re.compile(r"^make(?:\[\d+\])?: Leaving directory")
_TEST_F = re.compile(r"`test -f '([^']+)' \|\| echo '([^']*)'`(\S+)")
_LIBTOOL = re.compile(r"^libtool: compile:\s+(.*)$")
_VALUE_FLAGS = {"-o", "-MF", "-MT", "-MQ", "-I", "-isystem", "-iquote", "-include", "-idirafter", "-D", "-U", "-x",
                "-imacros", "--sysroot", "-isysroot", "-Xclang", "-target", "--param", "-arch", "-aux-info"}
NO_COMMANDS_HINT = ("no compiler command found in the build log. Build with full command lines: locally `make V=1 "
                    "2>&1 | tee build.log`; in Yocto the recipe must not use silent rules (autotools.bbclass passes "
                    "--disable-silent-rules; check EXTRA_OECONF / EXTRA_OEMAKE), then use "
                    "${WORKDIR}/temp/log.do_compile")


@dataclass
class LogParse:
    entries: list[dict] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)  # source files that do not exist in the workspace
    prefix_map: dict[str, str] = field(default_factory=dict)


def _source_arg(argv: list[str]) -> int | None:
    skip = False
    found = None
    for i, a in enumerate(argv[1:], 1):
        if skip:
            skip = False
            continue
        if a in _VALUE_FLAGS:
            skip = True
            continue
        if a.startswith("-"):
            continue
        if PurePosixPath(a).suffix.lower() in CPP_SOURCE_EXT:
            found = i
    return found


def _command(line: str, cwd: str | None) -> list[str] | None:
    """argv of a compile command on this log line, or None."""
    line = line.strip()
    m = _LIBTOOL.match(line)
    if m:
        line = m.group(1)
    elif line.startswith("+ "):  # shell trace (set -x)
        line = line[2:]
    if "--mode=compile" in line or "--mode=link" in line:  # the libtool wrapper; its `libtool: compile:` follows
        return None

    def test_f(mm: re.Match) -> str:
        name, alt, rest = mm.group(1), mm.group(2), mm.group(3)
        if cwd and os.path.exists(os.path.join(cwd, name)):
            return rest
        return alt + rest
    line = _TEST_F.sub(test_f, line)
    for sep in (" >/dev/null", " 2>&1", "&&", ";"):
        if sep in line and not line.startswith(sep):
            line = line.split(sep, 1)[0]
    try:
        argv = shlex.split(line)
    except ValueError:
        return None
    if not argv:
        return None
    # `ccache gcc`, `env X=1 gcc`, `${CCACHE}arm-poky-linux-gnueabi-gcc`
    while argv and (argv[0] in ("ccache", "sccache", "distcc", "env") or "=" in argv[0]) and len(argv) > 1:
        argv = argv[1:]
    if not _COMPILER.match(argv[0]) or "-c" not in argv:
        return None
    return argv


def _remap(path: str, prefix_map: dict[str, str]) -> str:
    for old, new in sorted(prefix_map.items(), key=lambda kv: -len(kv[0])):
        if path == old or path.startswith(old.rstrip("/") + "/"):
            return new.rstrip("/") + path[len(old.rstrip("/")):]
    return path


def _auto_prefix(path: str, repo: Path) -> tuple[str, str] | None:
    """(build-machine prefix, workspace root) when the tail of `path` exists in the repository."""
    parts = PurePosixPath(path).parts
    for i in range(1, len(parts) - 1):
        tail = Path(*parts[i:])
        if (repo / tail).is_file():
            return str(PurePosixPath(*parts[:i])), str(repo)
    return None


def parse_build_log(text: str, repo: Path, src: str | None = None, maps: dict[str, str] | None = None,
                    start_dir: str | None = None) -> LogParse:
    """Compile commands of a make / libtool / Yocto build log, source paths mapped onto `repo`."""
    repo = repo.resolve()
    out = LogParse()
    out.prefix_map.update(maps or {})
    if src:
        out.prefix_map[src.rstrip("/")] = str(repo)
    stack: list[str] = [start_dir] if start_dir else []
    seen: set[str] = set()
    for raw in text.splitlines():
        m = _ENTER.match(raw.strip())
        if m:
            stack.append(m.group(1))
            continue
        if _LEAVE.match(raw.strip()):
            if stack:
                stack.pop()
            continue
        cwd = stack[-1] if stack else None
        argv = _command(raw, cwd)
        if argv is None:
            continue
        i = _source_arg(argv)
        if i is None:
            continue
        directory = cwd or str(repo)
        file_abs = os.path.normpath(os.path.join(directory, argv[i]))
        mapped = _remap(file_abs, out.prefix_map)
        if not Path(mapped).is_file() and not src:
            guess = _auto_prefix(file_abs, repo)
            if guess and guess[0] not in out.prefix_map:
                out.prefix_map[guess[0]] = guess[1]
                mapped = _remap(file_abs, out.prefix_map)
        if mapped in seen:  # libtool compiles twice (PIC and non-PIC); keep the first
            continue
        seen.add(mapped)
        if not Path(mapped).is_file():
            out.unmapped.append(file_abs)
        out.entries.append({"directory": directory, "file": file_abs, "arguments": argv})
    # apply the final prefix map to every path-like token (directory, -I, file) for a self-consistent database
    final = []
    for e in out.entries:
        args = [e["arguments"][0]] + [_remap_token(a, e["directory"], out.prefix_map) for a in e["arguments"][1:]]
        final.append({"directory": _remap(e["directory"], out.prefix_map),
                      "file": _remap(e["file"], out.prefix_map), "arguments": args})
    out.entries = final
    out.unmapped = sorted(set(out.unmapped))
    return out


def _remap_token(tok: str, directory: str, prefix_map: dict[str, str]) -> str:
    for flag in ("-I", "-isystem", "-iquote", "-include", ""):
        if flag and tok.startswith(flag) and len(tok) > len(flag):
            val = tok[len(flag):]
            if not os.path.isabs(val):
                val = os.path.normpath(os.path.join(directory, val))
            return flag + _remap(val, prefix_map)
        if not flag and os.path.isabs(tok):
            return _remap(tok, prefix_map)
    if not tok.startswith("-") and PurePosixPath(tok).suffix.lower() in CPP_SOURCE_EXT:
        return _remap(os.path.normpath(os.path.join(directory, tok)), prefix_map)
    return tok


def log_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_compile_db(log: Path, repo: Path, out: Path, src: str | None = None, maps: dict[str, str] | None = None
                     ) -> LogParse:
    """Parse `log` and write `out` (compile_commands.json); PrerequisiteError when the log has no compile line."""
    if not log.is_file():
        raise PrerequisiteError(f"build log '{log}' not found")
    res = parse_build_log(log.read_text(encoding="utf-8", errors="replace"), repo, src, maps,
                          start_dir=str(log.resolve().parent))
    if not res.entries:
        raise PrerequisiteError(f"{log}: {NO_COMMANDS_HINT}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res.entries, indent=1), encoding="utf-8")
    return res
