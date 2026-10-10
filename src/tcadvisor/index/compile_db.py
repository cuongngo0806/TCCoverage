"""compile_commands.json loading and FR-013 prerequisite checks."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from tcadvisor.models import PrerequisiteError

CPP_SOURCE_EXT = {".c", ".cc", ".cpp", ".cxx", ".c++", ".cp", ".m", ".mm"}
CPP_HEADER_EXT = {".h", ".hh", ".hpp", ".hxx", ".h++", ".inl", ".ipp", ".tpp", ".tcc"}
CPP_EXT = CPP_SOURCE_EXT | CPP_HEADER_EXT

# Flags that only make sense to the real (often cross-) compiler and confuse libclang.
_DROP_WITH_VALUE = {"-o", "-MF", "-MT", "-MQ", "--serialize-diagnostics"}
_DROP_EXACT = {"-c", "-MD", "-MMD", "-MP", "-pipe", "-fpch-preprocess"}
_DROP_PREFIX = ("-mfpu", "-mfloat-abi", "-mcpu", "-march", "-mtune", "-mthumb", "-mabi", "-fstack-usage",
                "-Werror", "-fdiagnostics-color", "-fno-tree-", "-fcallgraph-info")


@dataclass(frozen=True)
class CompileCommand:
    file: Path  # absolute, resolved
    directory: Path
    args: tuple[str, ...]  # libclang-ready arguments (no compiler, no -o/-c, no input file)

    @property
    def defines(self) -> frozenset[str]:
        out = set()
        it = iter(self.args)
        for a in it:
            if a == "-D":
                a = "-D" + next(it, "")
            if a.startswith("-D"):
                out.add(a[2:].split("=", 1)[0])
        return frozenset(out)

    def macros(self) -> dict[str, str]:
        """Macros defined when this command is parsed: the compiler's predefined macros for its target
        (``__linux__``, ``__GNUC__``, ``_WIN32``, ...) plus/minus its own ``-D``/``-U`` in command-line order."""
        out = dict(predefined_macros(_target_args(self.args), self.file.suffix.lower() or ".cpp"))
        it = iter(self.args)
        for a in it:
            if a in ("-D", "-U"):
                a += next(it, "")
            if a.startswith("-D"):
                name, _, value = a[2:].partition("=")
                out[name] = value if "=" in a else "1"
            elif a.startswith("-U"):
                out.pop(a[2:], None)
        return out


def _split(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def _clean_args(raw: list[str], file: str, directory: Path) -> tuple[str, ...]:
    args = raw[1:]  # drop compiler executable
    out: list[str] = []
    skip = False
    file_abs = os.path.normcase(os.path.abspath(os.path.join(directory, file)))
    path_flags = ("-I", "-isystem", "-iquote", "-include", "-idirafter", "--sysroot")
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if skip:
            skip = False
            continue
        if a in _DROP_WITH_VALUE:
            skip = True
            continue
        if a in _DROP_EXACT or a.startswith(_DROP_PREFIX):
            continue
        if not a.startswith("-") and os.path.normcase(os.path.abspath(os.path.join(directory, a))) == file_abs:
            continue
        # make include paths absolute so parsing does not depend on cwd
        for pf in path_flags:
            if a == pf and i < len(args):
                out.append(a)
                out.append(str((directory / args[i]).resolve()) if not os.path.isabs(args[i]) else args[i])
                i += 1
                break
            if a.startswith(pf) and len(a) > len(pf) and not a.startswith(pf + "="):
                val = a[len(pf):]
                if pf == "--sysroot" and val.startswith("="):
                    out.append(a)
                else:
                    out.append(pf + (str((directory / val).resolve()) if not os.path.isabs(val) else val))
                break
        else:
            out.append(a)
    return tuple(out)


@lru_cache(maxsize=1)
def resource_dir_args() -> tuple[str, ...]:
    """Point libclang at clang's builtin headers (stddef.h, ...) when a clang binary is available."""
    clang = shutil.which("clang") or shutil.which("clang++")
    if not clang:
        return ()
    try:
        res = subprocess.run([clang, "-print-resource-dir"], capture_output=True, text=True, timeout=10)
        d = res.stdout.strip()
        if res.returncode == 0 and d and os.path.isdir(d):
            return ("-resource-dir", d)
    except (OSError, subprocess.SubprocessError):
        pass
    return ()


# Flags that cannot change which macros the compiler predefines (dropped so configurations share one probe).
_NO_PREDEF_WITH_VALUE = {"-I", "-isystem", "-iquote", "-idirafter", "-D", "-U"}
_NO_PREDEF_PREFIX = ("-I", "-isystem", "-iquote", "-idirafter", "-D", "-U", "-W")


def _target_args(args: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    it = iter(args)
    for a in it:
        if a in _NO_PREDEF_WITH_VALUE:
            next(it, None)
        elif not a.startswith(_NO_PREDEF_PREFIX):
            out.append(a)
    return tuple(out)


@lru_cache(maxsize=None)
def predefined_macros(target_args: tuple[str, ...], suffix: str = ".cpp") -> dict[str, str]:
    """Macros libclang predefines for one compile configuration (target, language, -std, -include ...).

    Parses an empty translation unit with the same flags the index uses, once per distinct configuration.
    Returns {} when libclang is unavailable, so callers fall back to the ``-D`` defines alone.
    """
    try:
        import clang.cindex as ci  # local import: compile_db is also used without libclang
        tu = ci.Index.create().parse(
            "tcadvisor_predef" + suffix, args=[*target_args, *resource_dir_args()],
            unsaved_files=[("tcadvisor_predef" + suffix, "")],
            options=ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    except Exception:  # noqa: BLE001 - missing/old libclang or unparsable flags: degrade, do not fail
        return {}
    out: dict[str, str] = {}
    for c in tu.cursor.get_children():
        if c.kind == ci.CursorKind.MACRO_DEFINITION and c.location.file is None:  # <built-in> / command line
            toks = [t.spelling for t in c.get_tokens()][1:]
            out[c.spelling] = " ".join(toks) if toks else "1"
    return out


class CompileDatabase:
    def __init__(self, build_dir: Path, entries: list[CompileCommand], digest: str):
        self.build_dir = build_dir
        self.entries = entries
        self.digest = digest
        self.by_file: dict[Path, CompileCommand] = {}
        for e in entries:
            self.by_file.setdefault(e.file, e)

    @classmethod
    def load(cls, build_dir: Path, repo: Path, allow_stale: bool = False) -> "CompileDatabase":
        path = build_dir / "compile_commands.json"
        if not path.is_file():
            raise PrerequisiteError(
                f"compile_commands.json not found in build dir '{build_dir}'. Configure the module with "
                "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON (see quickstart.md, Prerequisites)."
            )
        data = path.read_bytes()
        try:
            raw = json.loads(data)
        except json.JSONDecodeError as exc:
            raise PrerequisiteError(f"compile_commands.json in '{build_dir}' is not valid JSON: {exc}") from exc
        if not raw:
            raise PrerequisiteError(f"compile_commands.json in '{build_dir}' is empty.")
        if not allow_stale:
            _check_stale(path, repo, build_dir)
        entries = []
        for item in raw:
            directory = Path(item["directory"])
            argv = item.get("arguments") or _split(item["command"])
            file = (directory / item["file"]).resolve()
            entries.append(CompileCommand(file, directory, _clean_args(argv, item["file"], directory)))
        return cls(build_dir, entries, hashlib.sha256(data).hexdigest())

    def args_for(self, file: Path) -> tuple[str, ...] | None:
        cc = self.by_file.get(file)
        return cc.args if cc else None

    def configurations(self) -> list[str]:
        """Best-effort list of build configurations visible in the compile database."""
        cfgs = set()
        for e in self.entries:
            d = e.defines
            cfgs.add("Release" if "NDEBUG" in d else "Debug")
        return sorted(cfgs)


def _check_stale(db_path: Path, repo: Path, build_dir: Path) -> None:
    db_mtime = db_path.stat().st_mtime
    build_dir = build_dir.resolve()
    newer = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"
                   and (Path(root) / d).resolve() != build_dir and not (Path(root) / d / "CMakeCache.txt").exists()]
        for f in files:
            if f == "CMakeLists.txt" or f.endswith(".cmake"):
                p = Path(root) / f
                if p.stat().st_mtime > db_mtime + 1:
                    newer.append(p)
    if newer:
        names = ", ".join(str(p.relative_to(repo)) for p in newer[:5])
        raise PrerequisiteError(
            f"compile_commands.json in '{db_path.parent}' is stale: older than {names}. Re-run the CMake "
            "configure step (or pass --allow-stale-compile-db to accept reduced accuracy explicitly)."
        )
