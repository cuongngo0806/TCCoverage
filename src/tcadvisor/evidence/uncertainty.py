"""Explicit uncertainty flags (FR-007, Principle IV). Blind spots are reported, never dropped."""
from __future__ import annotations

import re
from dataclasses import dataclass

from tcadvisor.graph.impact import Graph
from tcadvisor.index.compile_db import CompileDatabase
from tcadvisor.ingest.changes import SymbolChange
from tcadvisor.models import SymbolRef, UncertaintyFlag

_IDENT = re.compile(r"[A-Za-z_]\w*")
_PP_WORDS = {"if", "ifdef", "ifndef", "elif", "else", "defined", "endif"}
_DYNAMIC_TOKENS = {"dlopen", "dlsym", "GetProcAddress", "LoadLibrary", "function", "bind", "QMetaObject",
                   "invokeMethod", "connect", "signal", "slot", "emit"}


# Compiler/platform macros: never passed as -D, their value is fixed by the indexed target.
_PLATFORM = {"_WIN32": "Windows", "_WIN64": "Windows", "_MSC_VER": "MSVC", "__MINGW32__": "MinGW",
             "__MINGW64__": "MinGW", "__CYGWIN__": "Cygwin", "__APPLE__": "Apple", "__MACH__": "Mach",
             "TARGET_OS_IPHONE": "iOS", "__linux__": "Linux", "__linux": "Linux", "linux": "Linux",
             "__gnu_linux__": "GNU/Linux", "__ANDROID__": "Android", "__QNX__": "QNX", "__QNXNTO__": "QNX",
             "__FreeBSD__": "FreeBSD", "__NetBSD__": "NetBSD", "__OpenBSD__": "OpenBSD", "__unix__": "Unix",
             "__unix": "Unix", "unix": "Unix", "__sun": "Solaris", "__VXWORKS__": "VxWorks",
             "__ZEPHYR__": "Zephyr", "__clang__": "Clang", "__GNUC__": "GCC", "__INTEL_COMPILER": "Intel C++",
             "__x86_64__": "x86_64", "_M_X64": "x86_64", "__i386__": "x86", "_M_IX86": "x86",
             "__aarch64__": "AArch64", "_M_ARM64": "ARM64", "__arm__": "ARM", "_M_ARM": "ARM"}
_ARCH = [("__x86_64__", "x86_64"), ("_M_X64", "x86_64"), ("__aarch64__", "aarch64"), ("_M_ARM64", "aarch64"),
         ("__arm__", "arm"), ("_M_ARM", "arm"), ("__i386__", "i386"), ("_M_IX86", "i386"), ("__riscv", "riscv"),
         ("__powerpc64__", "ppc64"), ("__powerpc__", "ppc"), ("__mips__", "mips")]
_OS = [("__ANDROID__", "android"), ("__linux__", "linux"), ("_WIN32", "windows"), ("__APPLE__", "apple"),
       ("__QNX__", "qnx"), ("__FreeBSD__", "freebsd"), ("__NetBSD__", "netbsd"), ("__OpenBSD__", "openbsd"),
       ("__sun", "solaris"), ("__unix__", "unix")]


@dataclass(frozen=True)
class _MacroConfig:
    macros: dict[str, str]  # effective: compiler-predefined for the target +/- the command's -D/-U
    predefined: frozenset[str]  # names the compiler (not a -D) defines
    target: str  # e.g. "x86_64-linux", "" if unknown


def _macro_configs(cdb: CompileDatabase) -> list[_MacroConfig]:
    """One entry per distinct macro configuration in compile_commands.json (deterministic order)."""
    seen: dict[frozenset, _MacroConfig] = {}
    for e in cdb.entries:
        m = e.macros()
        key = frozenset(m.items())
        if key not in seen:
            pre = frozenset(m) - e.defines
            arch = next((a for n, a in _ARCH if n in m), "")
            os_ = next((o for n, o in _OS if n in m), "")
            seen[key] = _MacroConfig(m, pre, "-".join(x for x in (arch, os_) if x))
    return list(seen.values())


_PP_TOKEN = re.compile(r"\s*(?:(0[xX][0-9a-fA-F]+|\d+)[uUlL]*|([A-Za-z_]\w*)|(&&|\|\||==|!=|<=|>=|<<|>>|[-!~+*/%<>&^|()?:]))")
_BINARY = {"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5, "==": 6, "!=": 6, "<": 7, "<=": 7, ">": 7, ">=": 7,
           "<<": 8, ">>": 8, "+": 9, "-": 9, "*": 10, "/": 10, "%": 10}


def _pp_eval(expr: str, macros: dict[str, str]) -> bool | None:
    """Evaluate an ``#if`` expression against a macro set; None when it cannot be decided statically."""
    toks: list[tuple[str, object]] = []
    pos = 0
    expr = expr.strip()
    while pos < len(expr):
        m = _PP_TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        if m.group(1):
            toks.append(("num", _pp_eval_int(m.group(1))))
        elif m.group(2):
            toks.append(("id", m.group(2)))
        elif m.group(3):
            toks.append(("op", m.group(3)))
    i = 0

    def value(name: str, depth: int = 0) -> int | None:
        if name in ("true", "false"):
            return int(name == "true")
        if name not in macros:
            return 0  # undefined identifiers evaluate to 0
        v = macros[name].strip()
        if re.fullmatch(r"(0[xX][0-9a-fA-F]+|\d+)[uUlL]*", v):
            return _pp_eval_int(v)
        if re.fullmatch(r"[A-Za-z_]\w*", v) and depth < 8:
            return value(v, depth + 1)
        return None

    def unary() -> int | None:
        nonlocal i
        if i >= len(toks):
            raise ValueError
        kind, t = toks[i]
        i += 1
        if kind == "num":
            return t  # type: ignore[return-value]
        if kind == "id":
            if t == "defined":
                paren = i < len(toks) and toks[i] == ("op", "(")
                i += paren
                if i >= len(toks) or toks[i][0] != "id":
                    raise ValueError
                name = toks[i][1]
                i += 1
                if paren:
                    if i >= len(toks) or toks[i] != ("op", ")"):
                        raise ValueError
                    i += 1
                return int(name in macros)
            if i < len(toks) and toks[i] == ("op", "("):
                raise ValueError  # function-like macro invocation: not decided here
            return value(t)  # type: ignore[arg-type]
        if t == "(":
            v = ternary()
            if i >= len(toks) or toks[i] != ("op", ")"):
                raise ValueError
            i += 1
            return v
        v = unary()
        if v is None:
            return None
        return {"!": lambda x: int(not x), "~": lambda x: ~x, "-": lambda x: -x, "+": lambda x: x}[t](v)  # type: ignore[index]

    def binary(level: int) -> int | None:
        nonlocal i
        lhs = unary()
        while i < len(toks) and toks[i][0] == "op" and _BINARY.get(toks[i][1], 0) >= level:  # type: ignore[arg-type]
            op = toks[i][1]
            i += 1
            rhs = binary(_BINARY[op] + 1)  # type: ignore[index]
            if op == "&&":
                lhs = 0 if lhs == 0 or rhs == 0 else None if lhs is None or rhs is None else 1
            elif op == "||":
                lhs = 1 if lhs or rhs else None if lhs is None or rhs is None else 0
            elif lhs is None or rhs is None:
                lhs = None
            elif op in ("/", "%") and rhs == 0:
                lhs = None
            else:
                lhs = {"|": lambda a, b: a | b, "^": lambda a, b: a ^ b, "&": lambda a, b: a & b,
                       "==": lambda a, b: int(a == b), "!=": lambda a, b: int(a != b),
                       "<": lambda a, b: int(a < b), "<=": lambda a, b: int(a <= b),
                       ">": lambda a, b: int(a > b), ">=": lambda a, b: int(a >= b),
                       "<<": lambda a, b: a << b if 0 <= b < 64 else 0, ">>": lambda a, b: a >> b if 0 <= b < 64 else 0,
                       "+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b,
                       "/": lambda a, b: int(a / b), "%": lambda a, b: a - b * int(a / b)}[op](lhs, rhs)  # type: ignore[index]
        return lhs

    def ternary() -> int | None:
        nonlocal i
        c = binary(1)
        if i < len(toks) and toks[i] == ("op", "?"):
            i += 1
            a = ternary()
            if i >= len(toks) or toks[i] != ("op", ":"):
                raise ValueError
            i += 1
            b = ternary()
            return None if c is None else a if c else b
        return c

    try:
        v = ternary()
        if i != len(toks):
            return None
    except (ValueError, IndexError, KeyError):
        return None
    return None if v is None else bool(v)


def _pp_eval_int(v: str) -> int:
    v = v.rstrip("uUlL")
    return int(v, 16) if v[:2] in ("0x", "0X") else int(v, 8) if v[0] == "0" and len(v) > 1 else int(v)


_SEGMENT = re.compile(r"#\s*(ifdef|ifndef|if|elif|else)\b\s*(.*)")


def _branch_active(condition: str, macros: dict[str, str]) -> bool | None:
    """Is the branch a line sits in active? ``condition`` is one ``conditional_stack`` entry, e.g.
    ``#ifdef _WIN32 / #else`` -- the line is in its last segment."""
    segs = [_SEGMENT.match(s.strip()) for s in re.split(r"\s/\s(?=#)", condition)]
    if not segs or not all(segs):
        return None
    vals: list[bool | None] = []
    for m in segs:
        d, rest = m.group(1), m.group(2).strip()  # type: ignore[union-attr]
        if d == "else":
            vals.append(True)
        elif d in ("ifdef", "ifndef"):
            name = _IDENT.match(rest)
            vals.append(None if not name else (name.group(0) in macros) == (d == "ifdef"))
        else:
            vals.append(_pp_eval(rest, macros))
    *before, last = vals
    if any(v is True for v in before):
        return False
    if any(v is None for v in before) or last is None:
        return None
    return last


def _line_active(conditions: list[str], macros: dict[str, str]) -> bool | None:
    vals = [_branch_active(c, macros) for c in conditions]
    if any(v is False for v in vals):
        return False
    return None if any(v is None for v in vals) else True


def _names(conditions: list[str]) -> list[str]:
    return sorted({w for c in conditions for w in _IDENT.findall(c)} - _PP_WORDS)


def _macro_flag(ch: SymbolChange, cms: list["_MacroConfig"], configs: list[str]) -> str | None:
    """Reason text for a change guarded by preprocessor conditions, or None when no flag is due.

    A macro is defined in a configuration when the compile command passes it with -D *or* the compiler
    predefines it for the indexed target (``__linux__``, ``__GNUC__``, ``_WIN32`` on Windows ...). Each changed
    line's ``#if`` stack is judged on its own: a line whose branch is inactive in every configuration was never
    parsed and is flagged.
    """
    tail = f" (configurations in compile_commands.json: {', '.join(configs)})"
    if not cms:  # no compile commands: nothing was parsed
        return (f"change in {ch.rel_path}:{ch.line} is guarded by `{' && '.join(ch.conditions)}`; no compile "
                "command was available to decide whether this branch was parsed" + tail)
    stacks = ch.condition_stacks or [[c] for c in ch.conditions]
    status = {}
    for st in stacks:
        act = [_line_active(st, c.macros) for c in cms]
        status[tuple(st)] = "parsed" if True in act else "blind" if all(a is False for a in act) else "unknown"
    names = _names(ch.conditions)
    always = {n for n in names if all(n in c.macros for c in cms)}
    never = {n for n in names if not any(n in c.macros for c in cms)}
    compiler = {n for n in names if n in _PLATFORM or any(n in c.predefined for c in cms)}
    targets = sorted({c.target for c in cms if c.target})
    target = f"the indexed target ({', '.join(targets)})" if targets else "the indexed target"

    def head(sts: list[tuple[str, ...]]) -> str:
        conds = sorted({c for st in sts for c in st})
        return f"change in {ch.rel_path}:{ch.line} is guarded by `{' && '.join(conds)}`; "

    blind = [st for st, v in status.items() if v == "blind"]
    if blind:  # some changed lines are in a branch no configuration parsed
        parts = []
        for n in _names([c for st in blind for c in st]):
            what = _PLATFORM.get(n, f"`{n}`")
            if n in never and n in compiler:
                parts.append(f"`{n}` is not defined for {target}, so the {what} branch was never parsed")
            elif n in always and n in compiler:
                parts.append(f"`{n}` is predefined by the compiler for {target}, so this non-{what} branch "
                             "was never parsed")
            elif n in never:
                parts.append(f"`{n}` is undefined in every compile command, so this branch was never parsed")
            elif n in always:
                parts.append(f"`{n}` has the same value in every compile command, so this branch was never parsed")
        if not parts:
            parts.append("the condition is false in every compile command, so this branch was never parsed")
        return head(blind) + "; ".join(parts) + tail

    unknown = [st for st, v in status.items() if v == "unknown"]
    if unknown:
        un = _names([c for st in unknown for c in st])
        single = [n for n in un if n in always or n in never]
        if single or ch.kind == "file":
            which = ", ".join(f"`{n}`" for n in (single or un)) or "the condition"
            return (head(unknown) + f"{which} cannot be evaluated statically for {target}, so it is unknown "
                    "whether this branch was parsed" + tail)
        return None

    # Every changed line was parsed. Compiler/platform macros are fixed by the target, so their other branch
    # is flagged only when *it* changes; a user macro with one value everywhere leaves its other branch untested.
    user = [n for n in names if n not in compiler]
    single = [n for n in user if n in always or n in never]
    if single or (ch.kind == "file" and user):
        which = ", ".join(f"`{n}`" for n in (single or user))
        return (head(list(status)) + f"{which} has the same value in every compile command, so the other branch "
                "was never parsed" + tail)
    return None


def detect(changes: list[SymbolChange], roots: dict[str, SymbolRef], g: Graph, cdb: CompileDatabase
           ) -> tuple[list[UncertaintyFlag], set[str]]:
    """Return (flags, root ids that must be flagged *instead of* producing cases)."""
    flags: list[UncertaintyFlag] = []
    flag_only: set[str] = set()
    configs = cdb.configurations()
    cms = _macro_configs(cdb) if any(ch.conditions for ch in changes) else []

    for ch in changes:
        ref = roots.get(ch.node_id)
        if ref is None:
            continue
        deps = g.dependents.get(ch.node_id, [])

        if ch.is_template and ch.change_kind != "removed":
            users = [d for d in deps if d.relation in ("instantiate", "call", "uses_type", "inherit_override")]
            if not users:
                flags.append(UncertaintyFlag(
                    "uninstantiated_template",
                    f"template `{ch.name}` has no visible instantiation or use in the indexed translation units; "
                    "its behaviour for concrete type arguments cannot be traced statically", ref))
                flag_only.add(ch.node_id)

        if ch.kind == "method" and (ch.is_virtual or g.override_group.get(ch.node_id)):
            group = {ch.node_id} | g.override_group.get(ch.node_id, set())
            if not any(g.callers(m) for m in group):
                flags.append(UncertaintyFlag(
                    "di_config_routing",
                    f"virtual method `{ch.name}` has no statically resolvable caller (neither it nor the methods it "
                    "overrides are called directly); it is presumably reached through an interface pointer "
                    "injected at runtime (DI / factory / configuration)", ref))
                flag_only.add(ch.node_id)

        if ch.node_id in g.facts.address_taken:
            f, ln = g.facts.address_taken[ch.node_id]
            flags.append(UncertaintyFlag(
                "dynamic_runtime_dependency",
                f"`{ch.name}` is used as a function pointer / callback ({f}:{ln}); the code that finally invokes it "
                "at runtime cannot be resolved statically", ref))
        tokens = set((ch.new.tokens if ch.new else []) + (ch.old.tokens if ch.old else []))
        if ch.kind in ("function", "method") and tokens & _DYNAMIC_TOKENS & {"dlopen", "dlsym", "GetProcAddress",
                                                                          "LoadLibrary", "invokeMethod"}:
            flags.append(UncertaintyFlag(
                "dynamic_runtime_dependency",
                f"`{ch.name}` loads or dispatches code dynamically "
                f"({', '.join(sorted(tokens & _DYNAMIC_TOKENS))}); runtime targets are not in the static graph", ref))

        if ch.conditions:
            flag = _macro_flag(ch, cms, configs)
            if flag:
                flags.append(UncertaintyFlag("build_config_incomplete_macro", flag, ref))
        elif ch.kind != "file":
            words = tokens & {"NDEBUG", "_DEBUG", "DEBUG"}
            if words and len(configs) < 2:
                flags.append(UncertaintyFlag(
                    "build_config_incomplete_macro",
                    f"`{ch.name}` depends on {', '.join(sorted(words))} but compile_commands.json only contains the "
                    f"{', '.join(configs)} configuration", ref))
    return flags, flag_only
