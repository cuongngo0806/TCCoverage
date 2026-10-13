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
# automake VPATH idiom `test -f 'x.c' || echo '../src/'`x.c (backticks may be lost when a log is copied)
_TEST_F = re.compile(r"`?test -f '([^']+)' \|\| echo '([^']*)'`?(\S+)")
# libtool's echo of the command it runs; cross toolchains prefix it (`arm-oe-linux-gnueabi-libtool: compile:`)
_LIBTOOL = re.compile(r"^(?:\S*-)?libtool: compile:\s+(.*)$")
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


_SEGMENT = re.compile(r"\s*(?:&&|\|\||;)\s*")


def _argv(segment: str) -> list[str] | None:
    """argv of one shell command if it is a compile command (`-c`), after unwrapping libtool / ccache / env."""
    seg = segment.strip()
    if seg.startswith("+ "):  # shell trace (set -x)
        seg = seg[2:]
    seg = re.sub(r"\s+\d?>\s*/dev/null|\s+2>&1", "", seg)
    try:
        argv = shlex.split(seg)
    except ValueError:
        return None
    if not argv:
        return None
    if "--mode=compile" in argv:  # `/bin/sh ./libtool --tag=CXX --mode=compile g++ ...` (make -n, make -k logs)
        rest = argv[argv.index("--mode=compile") + 1:]
        while rest and rest[0].startswith("--"):
            rest = rest[1:]
        argv = rest
    elif any(a.startswith("--mode=") for a in argv):  # libtool link / install
        return None
    # `ccache gcc`, `env X=1 gcc`, `${CCACHE}arm-poky-linux-gnueabi-gcc`
    while argv and (argv[0] in ("ccache", "sccache", "distcc", "env") or "=" in argv[0]) and len(argv) > 1:
        argv = argv[1:]
    if not argv or not _COMPILER.match(argv[0]) or "-c" not in argv:
        return None
    return argv


def _commands(line: str, cwd: str | None) -> list[tuple[list[str], bool]]:
    """Compile commands on one (continuation-joined) log line: a plain compiler call, a libtool `compile:` echo, a
    libtool wrapper call, or one of several shell commands joined with `&&` / `;` (as `make -n` prints them)."""
    line = line.strip()
    m = _LIBTOOL.match(line)
    exact = bool(m)  # libtool's own echo of the command it ran: preferred over its wrapper call
    if m:
        line = m.group(1)

    def test_f(mm: re.Match) -> str:
        name, alt, rest = mm.group(1), mm.group(2), mm.group(3)
        if cwd and os.path.exists(os.path.join(cwd, name)):
            return rest
        return alt + rest
    line = _TEST_F.sub(test_f, line)
    out = []
    for seg in _SEGMENT.split(line):
        argv = _argv(seg)
        if argv is not None:
            out.append((argv, exact or "--mode=compile" not in seg))
    return out


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
    seen: dict[str, int] = {}
    for raw in re.sub(r"\\\n", " ", text).splitlines():  # join shell continuation lines (make -n output)
        m = _ENTER.match(raw.strip())
        if m:
            stack.append(m.group(1))
            continue
        if _LEAVE.match(raw.strip()):
            if stack:
                stack.pop()
            continue
        cwd = stack[-1] if stack else None
        for argv, exact in _commands(raw, cwd):
            _add(out, argv, cwd, repo, src, seen, exact)
    _finish(out)
    return out


def _add(out: LogParse, argv: list[str], cwd: str | None, repo: Path, src: str | None, seen: dict[str, int],
         exact: bool) -> None:
    i = _source_arg(argv)
    if i is None:
        return
    directory = cwd or str(repo)
    file_abs = os.path.normpath(os.path.join(directory, argv[i]))
    mapped = _remap(file_abs, out.prefix_map)
    if not Path(mapped).is_file() and not src:
        guess = _auto_prefix(file_abs, repo)
        if guess and guess[0] not in out.prefix_map:
            out.prefix_map[guess[0]] = guess[1]
            mapped = _remap(file_abs, out.prefix_map)
    entry = {"directory": directory, "file": file_abs, "arguments": argv, "_exact": exact}
    if mapped in seen:  # PIC and non-PIC compile: keep the first; libtool's echo replaces its wrapper call
        prev = out.entries[seen[mapped]]
        if exact and not prev["_exact"]:
            out.entries[seen[mapped]] = entry
        return
    seen[mapped] = len(out.entries)
    if not Path(mapped).is_file():
        out.unmapped.append(file_abs)
    out.entries.append(entry)


def _finish(out: LogParse) -> None:
    """Apply the final prefix map to every path-like token (directory, -I, file): a self-consistent database."""
    final = []
    for e in out.entries:
        args = [e["arguments"][0]] + [_remap_token(a, e["directory"], out.prefix_map) for a in e["arguments"][1:]]
        final.append({"directory": _remap(e["directory"], out.prefix_map),
                      "file": _remap(e["file"], out.prefix_map), "arguments": args})
    out.entries = final
    out.unmapped = sorted(set(out.unmapped))


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


def generate_variant(repo: Path, log: Path, variant: str | None, src: str | None = None,
                     maps: dict[str, str] | None = None, out: Path | None = None) -> tuple[Path, LogParse]:
    """`tcadvisor compile-db` and the `build_log` config key: write the compile database of one build variant from
    its log and, with a variant name, record it in the build profile (`build` key; unconfirmed until
    `tcadvisor profile`)."""
    from tcadvisor.config import update_file
    from tcadvisor.ingest.git import git_exclude
    repo = repo.resolve()
    out = (out or repo / ".tcadvisor" / "build" / (variant or "default") / "compile_commands.json").resolve()
    git_exclude(repo, ".tcadvisor/build/")
    res = write_compile_db(log, repo, out, src, maps)
    if variant:
        rel = out.relative_to(repo).as_posix() if out.is_relative_to(repo) else str(out)
        log = log.resolve()
        bdir = next((str(d) for e in res.entries for d in (Path(e["directory"]), *Path(e["directory"]).parents)
                     if (d / "config.status").is_file()), None)  # configure's output: switch values (profile)

        def record(data: dict) -> None:
            prof = data.get("build") or {"system": "autotools", "confirmed": False, "variants": []}
            entry = next((v for v in prof["variants"] if v["name"] == variant), None)
            if entry is None:
                entry = {"name": variant}
                prof["variants"].append(entry)
            entry.update({"compile_db": rel, "build_log": str(log), "log_sha256": log_sha256(log)})
            if bdir:
                entry["build_dir"] = bdir
            data["build"] = prof
        update_file(repo, record)
    return out, res


def configured_logs(repo: Path, cfg: dict) -> dict[str, Path]:
    """`build_log` of the config as {variant: absolute path} (a single path is variant `default`)."""
    logs = cfg.get("build_log")
    if not logs:
        return {}
    items = {"default": logs} if isinstance(logs, str) else dict(logs)
    out = {}
    for name, path in items.items():
        p = Path(os.path.expandvars(str(path))).expanduser()
        out[name] = p if p.is_absolute() else (repo / p)
    return out


def refresh_from_config(repo: Path, cfg: dict) -> list[str]:
    """Before an analysis: (re)generate each configured variant's compile database when it is missing or its log
    changed since (sha256 recorded in the profile). Returns run notes."""
    repo = repo.resolve()
    recorded = {v["name"]: v for v in ((cfg.get("build") or {}).get("variants") or [])}
    notes = []
    for name, log in configured_logs(repo, cfg).items():
        if not log.is_file():
            notes.append(f"build_log of variant {name} not found: {log}; set 'build_log' in .tcadvisor/config.json "
                         "to the recipe's log.do_compile (bitbake -e <recipe> | grep ^WORKDIR=, then "
                         "<WORKDIR>/temp/log.do_compile)")
            continue
        out = repo / ".tcadvisor" / "build" / name / "compile_commands.json"
        if out.is_file() and recorded.get(name, {}).get("log_sha256") == log_sha256(log):
            continue
        try:
            _, res = generate_variant(repo, log, name, cfg.get("build_log_src"))
        except PrerequisiteError as exc:
            notes.append(f"build_log of variant {name}: {exc}")
            continue
        notes.append(f"compile database of variant {name} generated from {log} ({len(res.entries)} compile "
                     "command(s))" + (f"; {len(res.unmapped)} source(s) not found in the workspace: set "
                                      "'build_log_src' to the build's source dir" if res.unmapped else ""))
    return notes


def find_build_logs(repo: Path, recipe: str | None = None) -> str | dict[str, str] | None:
    """`log.do_compile` of the module's recipe under `$BUILDDIR` (set by Yocto's oe-init-build-env): one path, or
    {machine-arch: path} when the recipe was built for several architectures."""
    bb = os.environ.get("BUILDDIR")
    if not bb or not Path(bb).is_dir():
        return None
    name = recipe or repo.resolve().name
    found = sorted(Path(bb).glob(f"tmp*/work/*/{name}/*/temp/log.do_compile"))
    if not found:
        return None
    if len(found) == 1:
        return str(found[0])
    return {re.sub(r"[^A-Za-z0-9._-]", "-", p.parents[3].name): str(p) for p in found}
