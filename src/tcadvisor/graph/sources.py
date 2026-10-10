"""Every trigger source of a shared function (spec 006 US2, research R3).

Lesson: a function F was reached from four places; the fix added a guard in one of them and the other three
kept triggering the bug. When a change adds a condition before a call to F in one caller (S1), this module
lists the other callers of F (and callbacks registered for them), checks each one textually for a condition
on the same identifiers before its own call to F, and reports the ones without it.
Deterministic: call edges come from the graph, guards from the comment-free source text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tcadvisor.graph.impact import Graph
from tcadvisor.ingest.changes import SymbolChange, strip_comments, textual_functions
from tcadvisor.models import SymbolRef

_COND = re.compile(r"\b(if|while|switch)\s*\(|\?[^:]*:|\bassert\s*\(|\bif\s+constexpr\b")
_IDENT = re.compile(r"[A-Za-z_]\w*")
_NOISE = {"if", "else", "while", "switch", "return", "nullptr", "NULL", "true", "false", "this", "const", "auto",
          "and", "or", "not", "break", "continue", "case", "default", "sizeof", "static_cast", "reinterpret_cast",
          "const_cast", "dynamic_cast", "int", "bool", "char", "long", "unsigned", "size_t", "void", "assert",
          "std", "constexpr", "throw", "new", "delete"}
MAX_EXPANDED = 8


@dataclass
class TriggerSource:
    symbol: SymbolRef  # the caller of the target (or the callback that calls it)
    call_line: int
    kind: str = "call"  # call | registration
    registered_at: tuple[str, int] | None = None  # where the callback is registered (registration only)
    covered_by_change: bool = False
    guard: str = "unknown"  # present | absent | unknown


@dataclass
class GuardedTarget:
    target_id: str
    target: SymbolRef
    covered: list[str]  # changed callers that add the guard
    guard_ids: set[str]
    guard_lines: list[str]
    sources: list[TriggerSource] = field(default_factory=list)


def guard_identifiers(lines: list[str], target_name: str) -> set[str]:
    out: set[str] = set()
    short = target_name.split("::")[-1]
    for ln in lines:
        code = strip_comments(ln)
        if _COND.search(code):
            out |= {w for w in _IDENT.findall(code) if w not in _NOISE and len(w) > 1 and w != short}
    return out


_EXIT = re.compile(r"\b(return|continue|break|throw)\b")


def guard_scope(lines: list[str], ln: int) -> tuple[int, int] | None:
    """Lines (first, last) protected by the condition on 1-based line ``ln``: an early exit protects the rest
    of the function, a ``{`` block its body, a braceless ``if`` the next statement."""
    def code(i: int) -> str:
        return strip_comments(lines[i - 1]) if 0 < i <= len(lines) else ""
    head = code(ln)
    nxt = code(ln + 1).strip()
    if _EXIT.search(head) or _EXIT.match(nxt) or (nxt == "{" and _EXIT.match(code(ln + 2).strip())):
        return ln, 10**9
    start = ln if "{" in head.split(")")[-1] else (ln + 1 if nxt.startswith("{") else None)
    if start is None:
        return ln, ln + 1
    depth, seen = 0, False
    for i in range(start, len(lines) + 1):
        for chr_ in code(i):
            if chr_ == "{":
                depth, seen = depth + 1, True
            elif chr_ == "}":
                depth -= 1
                if seen and depth == 0:
                    return ln, i
    return ln, len(lines)


def guarded_calls(ch: SymbolChange, lines: list[str]) -> list[tuple[str, str, int, list[str]]]:
    """(callee usr, callee name, call line, guarding condition lines) for calls a change put behind a new or
    altered condition (inside its block, right after it, or after an added early exit)."""
    if ch.new is None or ch.is_test_code or ch.kind not in ("function", "method") or not lines:
        return []
    added = dict(zip(ch.added_line_numbers, ch.added_lines))
    scopes = [(ln, t, guard_scope(lines, ln)) for ln, t in sorted(added.items()) if _COND.search(strip_comments(t))]
    if not scopes:
        return []
    out, seen = [], set()
    for usr, qn, _kind, _df, _dl, call_line in ch.new.calls:
        if usr in seen or usr == ch.node_id:
            continue
        guards = [t for ln, t, sc in scopes if sc and sc[0] <= call_line <= sc[1]]
        if guards:
            seen.add(usr)
            out.append((usr, qn, call_line, guards))
    return out


def _function_text(repo: Path, ref: SymbolRef, cache: dict[str, list[str]]) -> list[tuple[int, str]]:
    if ref.file_path not in cache:
        try:
            cache[ref.file_path] = (repo / ref.file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            cache[ref.file_path] = []
    lines = cache[ref.file_path]
    spans = [f for f in textual_functions(lines) if f[1] <= ref.line <= f[2]]
    if not spans:  # one-line definition (the text scan only finds multi-line bodies)
        one = lines[ref.line - 1] if 0 < ref.line <= len(lines) else ""
        return [(ref.line, one)] if "{" in one and "}" in one else []
    _n, a, b = min(spans, key=lambda f: f[2] - f[1])
    return [(i, lines[i - 1]) for i in range(a, b + 1)]


def has_guard(repo: Path, source: SymbolRef, ids: set[str], target_name: str, cache: dict[str, list[str]]) -> str:
    """present: a condition reading one of ``ids`` precedes the source's call to the target; absent: the call
    is found without such a condition; unknown: the call is not visible in the text (macro, callback)."""
    body = _function_text(repo, source, cache)
    call = re.compile(rf"\b{re.escape(target_name.split('::')[-1])}\s*\(")
    seen_guard = False
    for n, (_i, raw) in enumerate(body):
        code = strip_comments(raw)
        if n == 0:  # signature line: only what follows the opening brace is body
            code = code.split("{", 1)[1] if "{" in code else ""
        guard_here = bool(_COND.search(code)) and bool(ids & set(_IDENT.findall(code)))
        if call.search(code):
            return "present" if seen_guard or guard_here else "absent"
        seen_guard = seen_guard or guard_here
    return "unknown"


def find_guarded_targets(repo: Path, graph: Graph, changes: list[SymbolChange],
                         roots: dict[str, SymbolRef]) -> list[GuardedTarget]:
    targets: dict[str, GuardedTarget] = {}
    cache: dict[str, list[str]] = {}
    for ch in changes:
        if ch.node_id not in roots:
            continue
        if ch.rel_path not in cache:
            try:
                cache[ch.rel_path] = (repo / ch.rel_path).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                cache[ch.rel_path] = []
        for usr, qn, _line, conds in guarded_calls(ch, cache[ch.rel_path]):
            ref = graph.symbol_ref(usr)
            if ref is None or ref.kind == "file":
                continue  # third-party / unknown target: covered by spec 005 boundary cases
            ids = guard_identifiers(conds, qn)
            if not ids:
                continue
            t = targets.setdefault(usr, GuardedTarget(usr, ref, [], set(), []))
            t.covered.append(ch.node_id)
            t.guard_ids |= ids
            t.guard_lines += [strip_comments(c).strip() for c in conds]
    for t in targets.values():
        seen: set[str] = set()
        for dep in graph.callers(t.target_id):
            if dep.dependent in seen or dep.dependent == t.target_id:
                continue
            seen.add(dep.dependent)
            ref = graph.symbol_ref(dep.dependent)
            if ref is None or ref.kind == "file":
                continue
            src = TriggerSource(ref, dep.line, covered_by_change=dep.dependent in t.covered)
            reg = graph.facts.address_taken.get(dep.dependent)
            if reg is not None:
                src.kind, src.registered_at = "registration", (reg[0], reg[1])
            if src.covered_by_change:
                src.guard = "present"
            else:
                src.guard = has_guard(repo, ref, t.guard_ids, t.target.qualified_name, cache)
            t.sources.append(src)
        t.sources.sort(key=lambda s: (not s.covered_by_change, s.guard != "absent", s.symbol.file_path,
                                      s.symbol.qualified_name))
    return list(targets.values())


def unresolved_source_flags(graph: Graph, guarded: list[GuardedTarget], roots: dict[str, SymbolRef]):
    """FR-607: ways to reach a guarded target that the static graph cannot list."""
    from tcadvisor.models import UncertaintyFlag
    out = []
    for t in guarded:
        cov = ", ".join(f"`{roots[r].qualified_name}`" for r in t.covered if r in roots)
        reg = graph.facts.address_taken.get(t.target_id)
        if reg is not None:
            out.append(UncertaintyFlag(
                "dynamic_runtime_dependency",
                f"`{t.target.qualified_name}` is also used as a callback / function pointer ({reg[0]}:{reg[1]}); "
                f"calls made through it are trigger sources the guard added in {cov} does not cover", t.target))
        if graph.override_group.get(t.target_id):
            out.append(UncertaintyFlag(
                "di_config_routing",
                f"`{t.target.qualified_name}` is virtual: calls through a base-class pointer reach it from sources "
                f"that cannot be listed statically; check them against the guard added in {cov}", t.target))
    return out
