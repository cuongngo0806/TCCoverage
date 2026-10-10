"""Diff -> changed symbols (roots of the impact traversal).

Each changed C++ file is parsed twice with libclang (old and new content, same compile flags) and
symbols are compared by USR on their comment-free token streams. Pure comment / whitespace /
formatting edits therefore produce *no* root (spec Edge Case, quickstart Scenario 2). Changed lines
not covered by any symbol (``#include``, ``#if``, file-scope statements) become a file-level root
when their comment-stripped content differs.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import clang.cindex as ci

from tcadvisor.index.clang_index import (CLASS_KINDS, FUNC_KINDS, K, SYMBOL_KINDS, TRANSPARENT_EXPR, TUExtractor,
                                         is_global_var, qualified_name, symbol_kind)
from tcadvisor.index.compile_db import CPP_EXT, CPP_HEADER_EXT, CompileDatabase
from tcadvisor.ingest.git import FileDiff

# Logging statements (override with TCADVISOR_LOG_PATTERN). A change made only of such lines cannot alter
# behaviour beyond log output, so it gets one low-priority case and no propagation (pilot finding: a
# "Log clean-up" commit in vsomeip produced 1510 cases).
_LOG_START = re.compile(os.environ.get("TCADVISOR_LOG_PATTERN", r"^\s*(VSOMEIP_(INFO|WARNING|ERROR|DEBUG|TRACE|FATAL)|"
                        r"ROCKS_LOG_\w+|[A-Z_]*LOG[A-Z_]*\s*\(|D?V?LOG\b|ALOG\w*|SPDLOG_\w+|spdlog::\w+|"
                        r"q(Debug|Info|Warning|Critical)\b|f?printf\s*\(|std::(cout|cerr|clog)\b|syslog\s*\()"))
_LOG_CONT = re.compile(r'^\s*(<<|"[^"]*"\s*[,;)]*\s*$|[)};,]+\s*$|$)')
_TEST_PATH = re.compile(r"(^|/)([Tt]ests?|[Uu]nit_?[Tt]ests?|gtest|testing)(/|$)|(^|/)[Tt]est_[^/]*$|"
                        r"_(unit)?tests?\.[^/]+$|[a-z0-9]Tests?\.[^/]+$")
_GTEST_SYM = re.compile(r"(_Test$|_Test::|^gtest_|::gtest_|AddToRegistry$|gtest_registering_dummy_)")


def is_test_path(rel: str) -> bool:
    return bool(_TEST_PATH.search(rel))


_COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/", re.S | re.M)
_PP_RE = re.compile(r"^\s*#\s*(\w+)\s*(.*)$")


@dataclass
class SymInfo:
    usr: str
    name: str
    kind: str
    display: str
    start: int
    end: int
    tokens: list[str]
    decl_tokens: list[str]  # signature part (before the body) for functions
    fields: list[tuple[str, str]] = field(default_factory=list)  # (name, type) in declaration order
    virtuals: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    is_template: bool = False
    is_virtual: bool = False
    is_inline: bool = False
    is_def: bool = False
    noexcept: str = ""
    # call sites in the body: (callee usr, callee qualified name, callee kind, decl file (abs), decl line, call line)
    calls: list[tuple[str, str, str, str, int, int]] = field(default_factory=list)
    # callee usr -> declaration facts (see callee_sig) + "discarded": call lines whose result is unused
    call_sigs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class SymbolChange:
    node_id: str
    rel_path: str
    change_kind: str  # modified|added|removed|file
    name: str
    kind: str
    line: int
    old: SymInfo | None = None
    new: SymInfo | None = None
    added_lines: list[str] = field(default_factory=list)  # source text of changed lines in this symbol
    removed_lines: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)  # enclosing #if conditions of changed lines
    is_header: bool = False
    added_line_numbers: list[int] = field(default_factory=list)
    textual: bool = False  # located by a text scan: the parser did not see it (inactive #if branch, no flags)

    @property
    def is_template(self) -> bool:
        return any(s.is_template for s in (self.old, self.new) if s)

    @property
    def is_virtual(self) -> bool:
        return any(s.is_virtual for s in (self.old, self.new) if s)

    def changed_calls(self) -> list[tuple[str, str, str, str, int, int]]:
        """Calls on changed lines: the caller now calls these functions differently (new call, new arguments)."""
        if self.new is None or self.is_log_only or self.is_test_code:
            return []
        lines = set(self.added_line_numbers)
        seen, out = set(), []
        for call in self.new.calls:
            if call[5] in lines and call[0] not in seen and call[0] != self.node_id:
                seen.add(call[0])
                out.append(call)
        return out

    @property
    def is_test_code(self) -> bool:
        """Changed test code (or GoogleTest macro-generated symbols): nothing depends on it."""
        return is_test_path(self.rel_path) or bool(_GTEST_SYM.search(self.name))

    @property
    def is_log_only(self) -> bool:
        lines = [strip_comments(ln) for ln in self.added_lines + self.removed_lines]
        if self.kind not in ("function", "method") or not self.old or not self.new or not any(ln.strip() for ln in lines):
            return False
        in_log = False
        for ln in lines:
            if _LOG_START.search(ln):
                in_log = not ln.rstrip().endswith(";")
            elif _LOG_CONT.match(ln) or (in_log and not ln.rstrip().endswith("{")):
                in_log = in_log and not ln.rstrip().endswith(";")
            else:
                return False
        return self.old.decl_tokens == self.new.decl_tokens

    def propagation(self) -> set[str] | None:
        """Relations along which dependents are affected; None = all.

        A class whose data layout and bases are unchanged (e.g. a method declaration was added) does not
        affect every user of the type: only subclasses (inherit/override) and includers (recompile).
        """
        if self.is_log_only or self.is_test_code:
            return set()
        if self.kind in ("class", "struct") and self.old and self.new \
                and self.old.fields == self.new.fields and self.old.bases == self.new.bases:
            return {"inherit_override", "include"}
        return None


@dataclass
class ChangeSet:
    changes: list[SymbolChange] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    non_cpp_files: list[str] = field(default_factory=list)
    out_of_scope: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def conditional_stack(lines: list[str]) -> dict[int, list[str]]:
    """Map 1-based line -> enclosing preprocessor conditions (outermost first)."""
    out: dict[int, list[str]] = {}
    stack: list[str] = []
    guard = _include_guard(lines)
    for i, raw in enumerate(lines, 1):
        m = _PP_RE.match(raw)
        if m:
            d, rest = m.group(1), strip_comments(m.group(2)).strip()
            if d in ("if", "ifdef", "ifndef"):
                cond = "" if guard and i == guard else f"#{d} {rest}"  # include guard: not a build condition
                out[i] = [c for c in list(stack) + [cond] if c]
                stack.append(cond)
                continue
            if d in ("elif", "else") and stack:
                stack[-1] = f"{stack[-1]} / #{d} {rest}".strip()
                out[i] = [c for c in stack if c]
                continue
            if d == "endif" and stack:
                out[i] = [c for c in stack if c]
                stack.pop()
                continue
        if any(stack):
            out[i] = [c for c in stack if c]
    return out


def _include_guard(lines: list[str]) -> int | None:
    """Line number of a classic ``#ifndef X / #define X`` include guard, if the file starts with one."""
    code = [(i, strip_comments(ln).strip()) for i, ln in enumerate(lines, 1)]
    code = [(i, ln) for i, ln in code if ln]
    if len(code) >= 2:
        m1 = re.match(r"#\s*(?:ifndef\s+(\w+)|if\s+!\s*defined\s*\(?\s*(\w+))", code[0][1])
        m2 = re.match(r"#\s*define\s+(\w+)\s*$", code[1][1])
        if m1 and m2 and (m1.group(1) or m1.group(2)) == m2.group(1):
            return code[0][0]
    return None


_STATUS_TYPE = re.compile(r"(?i)(error|status|result|optional|expected|errc)")
_SIZE_NAME = re.compile(r"(?i)^(n|len|length|size|sz|count|cnt|num\w*|\w*_?(len|length|size|count|bytes))$")
_INT_KINDS = {"BOOL", "CHAR_U", "UCHAR", "CHAR16", "CHAR32", "USHORT", "UINT", "ULONG", "ULONGLONG", "CHAR_S",
              "SCHAR", "WCHAR", "SHORT", "INT", "LONG", "LONGLONG", "ENUM"}


def callee_sig(ref: ci.Cursor) -> dict[str, Any]:
    """Facts a reviewer can test at a call site, read from the callee's *declaration* only (spec 005)."""
    sig: dict[str, Any] = {"role": "function", "result": "", "result_type": "", "may_throw": False,
                           "out_params": [], "callbacks": [], "buffers": [], "discarded": []}
    try:
        if ref.kind in (K.CONSTRUCTOR, K.DESTRUCTOR, K.CONVERSION_FUNCTION):
            sig["role"] = "special"
        elif re.match(r"operator(?!\w)", ref.spelling):
            sig["role"] = "operator"
        elif ref.kind == K.CXX_METHOD:
            sig["role"] = "const_method" if ref.is_const_method() else "method"
        rt = ref.result_type
        if rt.kind != ci.TypeKind.INVALID and ref.kind != K.CONSTRUCTOR:
            canon = rt.get_canonical()
            sig["result_type"] = rt.spelling
            if canon.kind == ci.TypeKind.POINTER:
                sig["result"] = "pointer"
            elif canon.kind.name in _INT_KINDS or (canon.kind == ci.TypeKind.RECORD
                                                   and _STATUS_TYPE.search(rt.spelling + " " + canon.spelling)):
                sig["result"] = "status"
        spec = str(ref.exception_specification_kind).split(".")[-1]
        mangled = ref.mangled_name or ""
        sig["may_throw"] = spec in ("NONE", "DYNAMIC", "MS_ANY") and mangled.startswith(("_Z", "?"))
        prev_ptr = None
        for i, a in enumerate(ref.get_arguments()):
            name = a.spelling or f"#{i + 1}"
            t = a.type.get_canonical()
            pointee = t.get_pointee() if t.kind in (ci.TypeKind.POINTER, ci.TypeKind.LVALUEREFERENCE) else None
            if pointee is not None and pointee.kind in (ci.TypeKind.FUNCTIONPROTO, ci.TypeKind.FUNCTIONNOPROTO):
                sig["callbacks"].append(name)
            elif t.kind == ci.TypeKind.RECORD and t.spelling.startswith("std::") and "function<" in t.spelling:
                sig["callbacks"].append(name)
            elif pointee is not None and not pointee.is_const_qualified():
                sig["out_params"].append(name)
            if t.kind == ci.TypeKind.POINTER and pointee is not None and pointee.kind != ci.TypeKind.FUNCTIONPROTO:
                prev_ptr = name
            elif prev_ptr and t.kind.name in _INT_KINDS and _SIZE_NAME.match(a.spelling or ""):
                sig["buffers"].append((prev_ptr, name))
                prev_ptr = None
    except Exception:  # noqa: BLE001 - a libclang binding gap must not break change detection
        pass
    return sig


class _FileSymbols:
    """Symbols declared/defined in one file of one parse, with comment-free token signatures."""

    def __init__(self, tu: ci.TranslationUnit, path: Path):
        self.syms: dict[str, SymInfo] = {}
        self.extents: list[tuple[int, int]] = []
        self._target = str(path)
        for top in tu.cursor.get_children():
            f = top.location.file
            if f is None or f.name != self._target:
                continue
            self._walk(top)

    def _tokens(self, c: ci.Cursor, exclude: list[tuple[int, int]] = ()) -> list[str]:
        out = []
        for t in c.get_tokens():
            if t.kind == ci.TokenKind.COMMENT:
                continue
            off = t.extent.start.offset
            if any(a <= off < b for a, b in exclude):
                continue
            out.append(t.spelling)
        return out

    def _walk(self, c: ci.Cursor) -> None:
        f = c.location.file
        if f is None or f.name != self._target:
            return
        k = c.kind
        if k in SYMBOL_KINDS and (k != K.VAR_DECL or is_global_var(c)) and c.get_usr():
            self._add(c)
        if k in CLASS_KINDS or k in (K.NAMESPACE, K.LINKAGE_SPEC, K.UNEXPOSED_DECL):
            for ch in c.get_children():
                self._walk(ch)

    def _add(self, c: ci.Cursor) -> None:
        k = c.kind
        exclude: list[tuple[int, int]] = []
        fields: list[tuple[str, str]] = []
        virtuals: list[str] = []
        bases: list[str] = []
        decl_tokens: list[str] = []
        children = list(c.get_children())
        if k in CLASS_KINDS:
            for ch in children:
                if ch.kind == K.FIELD_DECL:
                    fields.append((ch.spelling, ch.type.spelling))
                elif ch.kind == K.CXX_BASE_SPECIFIER:
                    bases.append(ch.type.spelling)
                elif ch.kind in FUNC_KINDS:
                    if ch.kind in (K.CXX_METHOD, K.DESTRUCTOR) and ch.is_virtual_method():
                        pure = ch.kind == K.CXX_METHOD and ch.is_pure_virtual_method()
                        virtuals.append(ch.displayname + (" = 0" if pure else ""))
                    body = next((g for g in ch.get_children() if g.kind == K.COMPOUND_STMT), None)
                    if body is not None:  # inline body: tracked on the method itself
                        exclude.append((body.extent.start.offset, body.extent.end.offset))
                elif ch.kind in CLASS_KINDS and ch.is_definition():
                    exclude.append((ch.extent.start.offset, ch.extent.end.offset))
        tokens = self._tokens(c, exclude)
        calls: list[tuple[str, str, str, str, int, int]] = []
        call_sigs: dict[str, dict[str, Any]] = {}
        is_inline = False
        noexcept = ""
        if k in FUNC_KINDS:
            body = next((g for g in children if g.kind == K.COMPOUND_STMT), None)
            if body is not None:
                decl_tokens = self._tokens(c, [(body.extent.start.offset, body.extent.end.offset)])
                in_class = c.lexical_parent is not None and c.lexical_parent.kind in CLASS_KINDS
                is_inline = in_class or "inline" in decl_tokens or "constexpr" in decl_tokens or (
                    Path(self._target).suffix.lower() in CPP_HEADER_EXT)
            else:
                decl_tokens = tokens
            try:
                noexcept = str(c.exception_specification_kind).split(".")[-1]
            except Exception:
                noexcept = ""
            if body is not None:
                calls, call_sigs = self._calls(body)
        usr = c.get_usr()
        info = SymInfo(
            usr=usr, name=qualified_name(c) if k != K.MACRO_DEFINITION else c.spelling,
            kind=symbol_kind(c), display=c.displayname, start=c.extent.start.line, end=c.extent.end.line,
            tokens=tokens, decl_tokens=decl_tokens, fields=fields, virtuals=virtuals, bases=bases,
            is_template=k in (K.FUNCTION_TEMPLATE, K.CLASS_TEMPLATE, K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION),
            is_virtual=k in (K.CXX_METHOD, K.DESTRUCTOR) and bool(c.is_virtual_method()),
            is_inline=is_inline, is_def=bool(c.is_definition()) or k == K.MACRO_DEFINITION, noexcept=noexcept,
            calls=calls, call_sigs=call_sigs,
        )
        prev = self.syms.get(usr)
        if prev is None or (info.is_def and not prev.is_def):
            self.syms[usr] = info
        elif prev is not None and not info.is_def and prev.is_def:
            # keep the definition but remember the declaration's signature too
            prev.decl_tokens = prev.decl_tokens or info.decl_tokens
        self.extents.append((info.start, info.end))

    def _calls(self, body: ci.Cursor) -> tuple[list[tuple[str, str, str, str, int, int]], dict[str, dict[str, Any]]]:
        out = []
        sigs: dict[str, dict[str, Any]] = {}
        stack: list[tuple[ci.Cursor, ci.Cursor | None]] = [(body, None)]  # (cursor, nearest non-transparent parent)
        while stack:
            cur, parent = stack.pop()
            if cur.kind == K.CALL_EXPR:
                ref = cur.referenced
                ctor = self._factory_ctor(cur, ref)
                if ctor is not None:
                    out.append(ctor)
                elif ref is not None and ref.kind in FUNC_KINDS and ref.location.file is not None and ref.get_usr():
                    out.append((ref.get_usr(), qualified_name(ref), symbol_kind(ref), ref.location.file.name,
                                ref.location.line, cur.location.line))
                    sig = sigs.get(ref.get_usr())
                    if sig is None:
                        sig = sigs[ref.get_usr()] = callee_sig(ref)
                    if sig.get("result") and parent is not None and (
                            parent.kind == K.COMPOUND_STMT or (parent.kind == K.CSTYLE_CAST_EXPR
                                                              and parent.type.kind == ci.TypeKind.VOID)):
                        sig["discarded"].append(cur.location.line)
            elif cur.kind == K.CXX_NEW_EXPR:
                ctor = self._ctor_of(cur.type.get_pointee(), cur.location.line)
                if ctor is not None:
                    out.append(ctor)
            nxt = parent if cur.kind in TRANSPARENT_EXPR else cur
            stack.extend((ch, nxt) for ch in cur.get_children())
        return out, sigs

    _FACTORIES = ("make_unique", "make_shared", "allocate_shared", "construct_at", "emplace", "emplace_back",
                  "emplace_front")

    def _factory_ctor(self, call: ci.Cursor, ref: ci.Cursor | None):
        """`std::make_unique<T>(args)` & co. construct a T: the callee that receives the arguments is T's ctor."""
        if ref is None or ref.spelling not in self._FACTORIES:
            return None
        t = call.type
        if ref.spelling in ("make_unique", "make_shared", "allocate_shared"):
            if t.get_num_template_arguments() > 0:
                return self._ctor_of(t.get_template_argument_type(0), call.location.line)
        elif ref.spelling == "construct_at":
            return self._ctor_of(t.get_pointee(), call.location.line)
        return None

    @staticmethod
    def _ctor_of(t: ci.Type, line: int):
        decl = t.get_canonical().get_declaration() if t is not None else None
        if decl is None or decl.kind not in CLASS_KINDS or decl.location.file is None or not decl.get_usr():
            return None
        ctor = next((c for c in decl.get_children() if c.kind == K.CONSTRUCTOR), None)
        if ctor is not None and ctor.get_usr():
            return (ctor.get_usr(), qualified_name(ctor), "method", ctor.location.file.name, ctor.location.line, line)
        return (decl.get_usr(), qualified_name(decl), "class", decl.location.file.name, decl.location.line, line)

    def covering(self, line: int) -> list[SymInfo]:
        return [s for s in self.syms.values() if s.start <= line <= s.end]


def _covered(extents: list[tuple[int, int]], line: int) -> bool:
    return any(a <= line <= b for a, b in extents)


def _residual(lines: list[str], changed: set[int], extents: list[tuple[int, int]]) -> list[str]:
    out = []
    for ln in sorted(changed):
        if 1 <= ln <= len(lines) and not _covered(extents, ln):
            s = strip_comments(lines[ln - 1]).strip()
            if s:
                out.append(s)
    return out


def _args_for_file(abs_path: Path, rel: str, cdb: CompileDatabase, tu_files: dict[str, set[str]],
                   repo: Path) -> tuple[str, ...] | None:
    args = cdb.args_for(abs_path)
    if args is not None:
        return args
    for tu_rel, deps in sorted(tu_files.items()):
        if rel in deps:
            a = cdb.args_for((repo / tu_rel).resolve())
            if a is not None:
                return a
    # a header that is new in this change is not yet included anywhere: borrow flags from a TU in
    # the same directory so it can still be parsed for its symbols
    if abs_path.suffix.lower() in CPP_HEADER_EXT:
        for e in cdb.entries:
            if e.file.parent == abs_path.parent:
                return e.args
    return None


def detect_changes(repo: Path, diffs: list[FileDiff], old_text: Any, new_text: Any, cdb: CompileDatabase,
                   tu_files: dict[str, set[str]], fallback_args: tuple[str, ...] | None = None) -> ChangeSet:
    """``old_text(rel)`` / ``new_text(rel)`` return file content on each side (None if absent)."""
    repo = repo.resolve()
    extractor = TUExtractor(repo)
    cs = ChangeSet()
    for fd in diffs:
        rel = fd.path
        cs.changed_files.append(rel)
        suffix = Path(rel).suffix.lower()
        name = Path(rel).name
        if suffix not in CPP_EXT:
            if name == "CMakeLists.txt" or suffix == ".cmake":
                cs.changes.append(SymbolChange(
                    node_id=f"file:{rel}", rel_path=rel, change_kind="file", name=rel, kind="file", line=1,
                    added_lines=[ln for ln in fd.added_text if strip_comments(ln).strip()],
                    removed_lines=[ln for ln in fd.removed_text if strip_comments(ln).strip()]))
            else:
                cs.non_cpp_files.append(rel)
            continue
        abs_new = (repo / (fd.new_path or rel)).resolve()
        abs_old = (repo / (fd.old_path or rel)).resolve()
        args = _args_for_file(abs_new, fd.new_path or rel, cdb, tu_files, repo) or (
            _args_for_file(abs_old, fd.old_path or rel, cdb, tu_files, repo)) or fallback_args
        if args is None:
            cs.out_of_scope.append({"path": rel, "reason": "file is not compiled by any target in the "
                                    "compile database (not part of the analysed module)"})
            continue
        old_src = old_text(fd.old_path) if fd.old_path else None
        new_src = new_text(fd.new_path) if fd.new_path else None
        old_syms = _parse_symbols(extractor, abs_old, args, old_src) if old_src is not None else None
        new_syms = _parse_symbols(extractor, abs_new, args, new_src) if new_src is not None else None
        old_lines = old_src.splitlines() if old_src is not None else []
        new_lines = new_src.splitlines() if new_src is not None else []
        new_conds = conditional_stack(new_lines)
        old_conds = conditional_stack(old_lines)
        is_header = suffix in CPP_HEADER_EXT

        candidates: dict[str, tuple[SymInfo | None, SymInfo | None]] = {}
        if new_syms:
            for ln in fd.new_lines:
                for s in new_syms.covering(ln):
                    candidates[s.usr] = (old_syms.syms.get(s.usr) if old_syms else None, s)
        if old_syms:
            for ln in fd.old_lines:
                for s in old_syms.covering(ln):
                    candidates.setdefault(s.usr, (s, new_syms.syms.get(s.usr) if new_syms else None))
        for usr, (o, n) in sorted(candidates.items(), key=lambda kv: (kv[1][1] or kv[1][0]).start):
            if o is not None and n is not None and o.tokens == n.tokens and o.decl_tokens == n.decl_tokens:
                continue  # comment/format-only edit inside this symbol
            kind = "modified" if o and n else "added" if n else "removed"
            ref = n or o
            added = [new_lines[ln - 1] for ln in sorted(fd.new_lines)
                     if n and n.start <= ln <= n.end and ln <= len(new_lines)]
            removed = [old_lines[ln - 1] for ln in sorted(fd.old_lines)
                       if o and o.start <= ln <= o.end and ln <= len(old_lines)]
            conds = sorted({c for ln in fd.new_lines if n and n.start <= ln <= n.end for c in new_conds.get(ln, [])}
                           | {c for ln in fd.old_lines if o and o.start <= ln <= o.end for c in old_conds.get(ln, [])})
            cs.changes.append(SymbolChange(
                node_id=usr, rel_path=fd.new_path or rel, change_kind=kind, name=ref.name, kind=ref.kind,
                line=ref.start, old=o, new=n, added_lines=added, removed_lines=removed, conditions=conds,
                is_header=is_header, added_line_numbers=sorted(ln for ln in fd.new_lines if n and n.start <= ln <= n.end)))

        res_new = _residual(new_lines, fd.new_lines, new_syms.extents if new_syms else [])
        res_old = _residual(old_lines, fd.old_lines, old_syms.extents if old_syms else [])
        include_only = all(ln.lstrip().startswith("#include") or ln.lstrip().startswith("#pragma once")
                           for ln in res_new + res_old)
        if sorted(res_new) != sorted(res_old) and include_only and not is_header:
            cs.notes.append(f"{fd.new_path or rel}: only #include directives changed (no semantic root; dependencies "
                            "are re-indexed)")
        elif sorted(res_new) != sorted(res_old):
            # changed lines the parser never saw (inactive #if branch, missing flags): attribute them to the
            # enclosing function found by a text scan, so impact can still be traced by name
            cov_new, cov_old = (new_syms.extents if new_syms else []), (old_syms.extents if old_syms else [])
            tf_new, tf_old = textual_functions(new_lines), textual_functions(old_lines)
            by_fn: dict[str, dict] = {}
            rest_new = {ln for ln in fd.new_lines if not _covered(cov_new, ln)}
            rest_old = {ln for ln in fd.old_lines if not _covered(cov_old, ln)}
            for side, lines_, cand, rest in (("+", new_lines, tf_new, rest_new), ("-", old_lines, tf_old, rest_old)):
                for ln in sorted(rest):
                    fn = next((f for f in cand if f[1] <= ln <= f[2]), None)
                    text = strip_comments(lines_[ln - 1]).strip() if 0 < ln <= len(lines_) else ""
                    if fn is None or not text:
                        continue
                    e = by_fn.setdefault(fn[0], {"start": fn[1], "add": [], "rem": [], "lines": set(), "old": set()})
                    (e["add"] if side == "+" else e["rem"]).append(text)
                    (e["lines"] if side == "+" else e["old"]).add(ln)
                    if side == "+":
                        e["start"] = fn[1]
            for name, e in sorted(by_fn.items()):
                if sorted(e["add"]) == sorted(e["rem"]):
                    continue
                conds = sorted({c for ln in e["lines"] for c in new_conds.get(ln, [])}
                               | {c for ln in e["old"] for c in old_conds.get(ln, [])})
                cs.changes.append(SymbolChange(
                    node_id=f"text:{fd.new_path or rel}:{name}", rel_path=fd.new_path or rel, change_kind="modified",
                    name=name, kind="method" if "::" in name else "function", line=e["start"],
                    added_lines=e["add"], removed_lines=e["rem"], conditions=conds, is_header=is_header,
                    added_line_numbers=sorted(e["lines"]), textual=True))
                rest_new -= e["lines"]
                rest_old -= e["old"]
            res_new = _residual(new_lines, rest_new, cov_new)
            res_old = _residual(old_lines, rest_old, cov_old)
            if sorted(res_new) == sorted(res_old):
                continue
            conds = sorted({c for ln in fd.new_lines if not _covered(new_syms.extents if new_syms else [], ln)
                            for c in new_conds.get(ln, [])}
                           | {c for ln in fd.old_lines if not _covered(old_syms.extents if old_syms else [], ln)
                              for c in old_conds.get(ln, [])})
            first = min(fd.new_lines or fd.old_lines or {1})
            cs.changes.append(SymbolChange(
                node_id=f"file:{fd.new_path or rel}", rel_path=fd.new_path or rel,
                change_kind="file" if fd.new_path else "removed", name=fd.new_path or rel, kind="file",
                line=first, added_lines=res_new, removed_lines=res_old, conditions=conds, is_header=is_header))
    return cs


_FN_HEAD = re.compile(r"^[A-Za-z_][\w:<>,\s\*&~]*?\b((?:[A-Za-z_]\w*::)*~?[A-Za-z_]\w*)\s*\([^;]*$")
_NOT_FN = {"if", "for", "while", "switch", "return", "sizeof", "catch", "do", "else"}


def textual_functions(lines: list[str]) -> list[tuple[str, int, int]]:
    """Function definitions found by a brace-aware text scan: (name, first line, last line).

    Used only for code the parser did not see. Namespaces / extern "C" / classes are transparent scopes.
    """
    out: list[tuple[str, int, int]] = []
    stack: list[tuple[str, str, int]] = []  # (kind, name, start)
    pending: tuple[str, int] | None = None
    for i, raw in enumerate(lines, 1):
        line = strip_comments(raw)
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        in_fn = any(k == "fn" for k, _n, _s in stack)
        if not in_fn:
            m = _FN_HEAD.match(s)
            if m and m.group(1).split("::")[-1] not in _NOT_FN:
                pending = (m.group(1), i)
            elif s.endswith(";"):
                pending = None
        for ch in line:
            if ch == "{":
                if in_fn:
                    stack.append(("blk", "", i))
                elif pending is not None:
                    stack.append(("fn", pending[0], pending[1]))
                    in_fn = True
                    pending = None
                else:
                    stack.append(("scope", "", i))
            elif ch == "}" and stack:
                kind, name, start = stack.pop()
                if kind == "fn":
                    out.append((name, start, i))
    return out


def _parse_symbols(extractor: TUExtractor, path: Path, args: tuple[str, ...], content: str) -> _FileSymbols:
    tu = extractor.parse(path, args, unsaved=[(str(path), content)])
    return _FileSymbols(tu, path)


def explicit_changes(repo: Path, usrs: list[str], symbols: dict[str, dict[str, Any]], cdb: CompileDatabase,
                     tu_files: dict[str, set[str]]) -> list[SymbolChange]:
    """Roots for explicit-symbol mode: exactly the named symbols, classified on their current tokens."""
    repo = repo.resolve()
    extractor = TUExtractor(repo)
    parsed: dict[str, _FileSymbols | None] = {}
    out = []
    for usr in usrs:
        s = symbols[usr]
        rel = s["file"]
        if rel not in parsed:
            abs_p = (repo / rel).resolve()
            args = _args_for_file(abs_p, rel, cdb, tu_files, repo)
            parsed[rel] = (_parse_symbols(extractor, abs_p, args, abs_p.read_text(encoding="utf-8", errors="replace"))
                           if args is not None else None)
        fs = parsed[rel]
        info = fs.syms.get(usr) if fs else None
        out.append(SymbolChange(
            node_id=usr, rel_path=rel, change_kind="explicit", name=s["name"], kind=s["kind"], line=s["line"],
            old=None, new=info, is_header=Path(rel).suffix.lower() in CPP_HEADER_EXT))
    return out
