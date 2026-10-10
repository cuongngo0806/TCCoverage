"""Test cases at third-party API boundaries (spec 005).

A callee declared outside the repository has no body in the graph, but its *declaration* (parsed by
libclang from the module's include path) and the call site still say what can go wrong: a null or
failure return, an ignored result, an exception, an out-parameter, a callback, a buffer + length pair.
Each such signal becomes a corner case on the calling function. Deterministic, no model; known library
behaviour that a declaration cannot show comes from an optional, hand-written contract file.
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tcadvisor.models import RiskClassification, UsageError

CONTRACTS_FILE = ".tcadvisor/external-contracts.json"
MAX_HINTS = 10
# most severe first: the case takes the first group any of its signals produced
GROUP_ORDER = ("exception_safety", "ownership_lifetime", "thread_safety", "logic")
C_STD_HEADERS = {"assert.h", "ctype.h", "errno.h", "fenv.h", "float.h", "inttypes.h", "limits.h", "locale.h",
                 "math.h", "setjmp.h", "signal.h", "stdarg.h", "stddef.h", "stdint.h", "stdio.h", "stdlib.h",
                 "string.h", "strings.h", "time.h", "uchar.h", "wchar.h", "wctype.h", "memory.h"}


@dataclass
class ExternalCall:
    name: str  # callee qualified name
    header: str  # last two path components of the declaring file
    call_file: str
    call_line: int
    sig: dict[str, Any] = field(default_factory=dict)


def is_standard(qualified_name: str, decl_file: str) -> bool:
    """C++ standard library, compiler internals and C standard headers are not third-party code."""
    if qualified_name.startswith(("std::", "__")) or "/bits/" in decl_file.replace("\\", "/"):
        return True
    p = Path(decl_file)
    return p.name in C_STD_HEADERS and p.parent.name == "include"


def signals(call: ExternalCall, caller: str) -> list[tuple[str, str]]:
    """(risk group, corner case) pairs derived from the callee declaration and the call site."""
    s, api = call.sig, f"`{call.name}`"
    out: list[tuple[str, str]] = []
    rt = s.get("result_type", "")
    if s.get("result") == "pointer":
        out.append(("ownership_lifetime", f"{api} returns `{rt}`: make it return nullptr and check `{caller}` does "
                                          "not dereference it; check who owns/frees the returned object"))
    elif s.get("result") == "status":
        if call.call_line in s.get("discarded", []):
            out.append(("logic", f"the `{rt}` result of {api} is ignored at line {call.call_line}: make the call fail "
                                 f"and check the failure is not lost in `{caller}`"))
        else:
            out.append(("logic", f"make {api} return its failure / sentinel `{rt}` value and check the error path "
                                 f"of `{caller}`"))
    if s.get("may_throw"):
        out.append(("exception_safety", f"{api} is not noexcept: make it throw and check `{caller}` leaves no "
                                        "partial state, held lock or leaked resource"))
    for p in s.get("out_params", [])[:2]:
        out.append(("ownership_lifetime", f"{api} writes through `{p}`: check the value `{caller}` uses when the "
                                          "call fails or returns early (out-parameter left unset)"))
    for p in s.get("callbacks", [])[:2]:
        out.append(("thread_safety", f"{api} takes callback `{p}`: check it may run later, on another thread or "
                                     f"re-entrantly, and that state it captures from `{caller}` is still alive"))
    for buf, n in s.get("buffers", [])[:2]:
        out.append(("logic", f"{api}(`{buf}`, `{n}`): boundary lengths 0, 1, exact capacity and capacity + 1"))
    if not out:
        out.append(("logic", f"{api} has no checkable contract in its declaration: replace it with a stub that "
                             f"fails, blocks or returns unusual data and check `{caller}`"))
    return out


def external_risk(caller: str, calls: list[ExternalCall],
                  contracts: dict[str, list[str]] | None = None) -> RiskClassification:
    """One classification per calling function: the most severe group, one hint per signal."""
    groups: set[str] = set()
    hints: list[str] = []
    for c in calls:
        for h in contract_hints(c.name, contracts or {}):
            hints.append(f"Contract: {c.name}: {h}")
        for grp, h in signals(c, caller):
            groups.add(grp)
            hints.append(h)
    group = next(g for g in GROUP_ORDER if g in groups)
    names = ", ".join(f"`{c.name}` ({c.header}, {c.call_file}:{c.call_line})" for c in calls[:6])
    more = f" and {len(calls) - 6} more" if len(calls) > 6 else ""
    return RiskClassification(group, "external_call",
                              f"`{caller}` now calls third-party code outside the repository: {names}{more}",
                              list(dict.fromkeys(hints))[:MAX_HINTS])


def contract_hints(name: str, contracts: dict[str, list[str]]) -> list[str]:
    short = name.split("::")[-1]
    out: list[str] = []
    for pattern, items in contracts.items():
        if fnmatch.fnmatchcase(name, pattern) or fnmatch.fnmatchcase(short, pattern):
            out.extend(items)
    return out


def load_contracts(repo: Path, explicit: Path | None = None) -> dict[str, list[str]]:
    """``{"<qualified name or fnmatch pattern>": ["corner case", ...]}``; absent default file = no contracts."""
    path = explicit if explicit is not None else repo / CONTRACTS_FILE
    if explicit is None and not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read external contracts {path}: {exc}") from exc
    if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v) for k, v in data.items()):
        raise UsageError(f"external contracts {path} must map API names to lists of strings")
    return data
