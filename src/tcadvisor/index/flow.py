"""Per-function def-use facts for data-path tracing (spec 006 US1, research R1).

For every function defined in the repository part of a translation unit, one forward pass over its body
records where values come from and where they go — enough to answer "does a value produced by the changed
function reach that send call?" without alias analysis:

- ``defs``: ``[line, target, sources]`` for local initialisation, assignment (``=``, ``+=`` …) and ``return``;
  targets are ``local:x``, ``param:p`` (write through an out-parameter), ``member:f``, ``global:g``, ``return``;
- ``calls``: ``[line, callee_usr, callee_name, callee_def_file, external_decl_file, arg_sources, outs, base]``
  where ``outs`` are ``[k, target]`` for arguments bound to non-const reference / pointer parameters and
  ``base`` the object a method is called on (it absorbs the arguments: ``msg.set(x)``, ``q.push_back(x)``);
- ``conds``: ``[line, sources]`` for if / while / switch / ?: / for conditions.

Sources are ``param:p``, ``local:x``, ``member:f``, ``global:g``, ``call:<usr>`` (result of a call) and
``outarg:<usr>:<k>``. Deterministic, libclang only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import clang.cindex as ci

from tcadvisor.index.clang_index import (FUNC_KINDS, TRANSPARENT_EXPR, K, TUExtractor, file_sha, is_global_var,
                                         qualified_name)

FLOW_VERSION = 1
_ASSIGN = {"=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="}
_SKIP = {K.TYPE_REF, K.NAMESPACE_REF, K.TEMPLATE_REF, K.LAMBDA_EXPR}


def _children(c: ci.Cursor) -> list[ci.Cursor]:
    return [x for x in c.get_children() if x.kind not in _SKIP]


def _strip(c: ci.Cursor) -> ci.Cursor:
    while c.kind in TRANSPARENT_EXPR | {K.CSTYLE_CAST_EXPR, K.CXX_STATIC_CAST_EXPR, K.CXX_FUNCTIONAL_CAST_EXPR}:
        ch = _children(c)
        if not ch:
            break
        c = ch[-1]
    return c


def _op(c: ci.Cursor, lhs: ci.Cursor) -> str:
    end = lhs.extent.end.offset
    for t in c.get_tokens():
        if t.extent.start.offset >= end and t.kind == ci.TokenKind.PUNCTUATION:
            return t.spelling
    return ""


class _Fn:
    def __init__(self, ex: "FlowExtractor", fn: ci.Cursor):
        self.ex = ex
        self.params = [a.spelling or f"#{i}" for i, a in enumerate(fn.get_arguments())]
        self.param_out = [_is_out(a.type) for a in fn.get_arguments()]
        self.defs: list[list[Any]] = []
        self.calls: list[list[Any]] = []
        self.conds: list[list[Any]] = []

    def srcs(self, c: ci.Cursor) -> set[str]:
        k = c.kind
        if k == K.DECL_REF_EXPR:
            r = c.referenced
            if r is None:
                return set()
            if r.kind == K.PARM_DECL:
                return {f"param:{r.spelling}"}
            if r.kind == K.VAR_DECL:
                return {f"global:{qualified_name(r)}"} if is_global_var(r) else {f"local:{r.spelling}"}
            return set()
        if k == K.MEMBER_REF_EXPR:
            ch = _children(c)
            r = c.referenced
            if not ch or _strip(ch[0]).kind == K.CXX_THIS_EXPR:
                return {f"member:{r.spelling}"} if r is not None and r.kind == K.FIELD_DECL else set()
            return set().union(*(self.srcs(x) for x in ch))
        if k == K.CALL_EXPR:
            out = set().union(*(self.srcs(x) for x in _children(c))) if _children(c) else set()
            r = c.referenced
            if r is not None and r.get_usr() and r.kind != K.CONSTRUCTOR:
                out.add(f"call:{r.get_usr()}")
            return out
        if k in (K.INTEGER_LITERAL, K.FLOATING_LITERAL, K.STRING_LITERAL, K.CHARACTER_LITERAL,
                 K.CXX_BOOL_LITERAL_EXPR, K.CXX_NULL_PTR_LITERAL_EXPR, K.LAMBDA_EXPR):
            return set()
        ch = _children(c)
        return set().union(*(self.srcs(x) for x in ch)) if ch else set()

    def target(self, c: ci.Cursor) -> str | None:
        c = _strip(c)
        if c.kind == K.DECL_REF_EXPR and c.referenced is not None:
            r = c.referenced
            if r.kind == K.PARM_DECL:
                return f"param:{r.spelling}"
            if r.kind == K.VAR_DECL:
                return f"global:{qualified_name(r)}" if is_global_var(r) else f"local:{r.spelling}"
            return None
        if c.kind == K.MEMBER_REF_EXPR:
            ch = _children(c)
            if not ch or _strip(ch[0]).kind == K.CXX_THIS_EXPR:
                return f"member:{c.referenced.spelling}" if c.referenced is not None else None
            return self.target(ch[0])
        if c.kind in (K.UNARY_OPERATOR, K.ARRAY_SUBSCRIPT_EXPR):
            ch = _children(c)
            return self.target(ch[0]) if ch else None
        return None

    def walk(self, c: ci.Cursor) -> None:
        k = c.kind
        line = c.location.line
        if k == K.LAMBDA_EXPR:
            return
        if k == K.VAR_DECL:
            init = [x for x in _children(c)]
            if init:
                self.defs.append([line, f"local:{c.spelling}", sorted(set().union(*(self.srcs(x) for x in init)))])
        elif k in (K.BINARY_OPERATOR, K.COMPOUND_ASSIGNMENT_OPERATOR):
            ch = _children(c)
            if len(ch) == 2:
                op = _op(c, ch[0]) if k == K.BINARY_OPERATOR else "+="
                if op in _ASSIGN:
                    tgt = self.target(ch[0])
                    if tgt:
                        s = self.srcs(ch[1]) | (self.srcs(ch[0]) if op != "=" else set())
                        self.defs.append([line, tgt, sorted(s)])
        elif k == K.RETURN_STMT:
            ch = _children(c)
            if ch:
                self.defs.append([line, "return", sorted(set().union(*(self.srcs(x) for x in ch)))])
        elif k in (K.IF_STMT, K.WHILE_STMT, K.SWITCH_STMT, K.CONDITIONAL_OPERATOR, K.DO_STMT):
            ch = _children(c)
            cond = (ch[-1] if k == K.DO_STMT else ch[0]) if ch else None
            if cond is not None:
                self.conds.append([cond.location.line, sorted(self.srcs(cond))])
        elif k == K.CALL_EXPR:
            self.call(c)
        for x in c.get_children():
            if x.kind != K.LAMBDA_EXPR:
                self.walk(x)

    def call(self, c: ci.Cursor) -> None:
        r = c.referenced
        if r is None or r.kind not in FUNC_KINDS or not r.get_usr():
            return
        args = list(c.get_arguments())
        arg_srcs = [sorted(self.srcs(a)) for a in args]
        params = list(r.get_arguments())
        outs = []
        for i, a in enumerate(args):
            if i < len(params) and _is_out(params[i].type):
                t = self.target(a)
                if t:
                    outs.append([i, t])
        base = None
        ch = _children(c)
        if ch and _strip(ch[0]).kind == K.MEMBER_REF_EXPR:
            mch = _children(_strip(ch[0]))
            if mch:
                base = self.target(mch[0])
        d = r.get_definition() or r
        def_file = self.ex.rel(d.location.file.name) if d.location.file else None
        decl_file = r.location.file.name if r.location.file else ""
        external = "" if (def_file or self.ex.rel(decl_file)) else decl_file
        self.calls.append([c.location.line, r.get_usr(), qualified_name(r), def_file or "", external, arg_srcs, outs,
                           base])


def _is_out(t: ci.Type) -> bool:
    t = t.get_canonical()
    if t.kind in (ci.TypeKind.LVALUEREFERENCE, ci.TypeKind.POINTER):
        p = t.get_pointee()
        return not p.is_const_qualified() and p.kind not in (ci.TypeKind.FUNCTIONPROTO, ci.TypeKind.FUNCTIONNOPROTO)
    return False


class FlowExtractor(TUExtractor):
    def extract_flow(self, path: Path, args: tuple[str, ...]) -> dict[str, Any]:
        tu = self.parse(path, args)
        functions: dict[str, dict[str, Any]] = {}
        deps: dict[str, str] = {}
        main_rel = self.rel(str(path))
        if main_rel:
            deps[main_rel] = file_sha(path)
        for inc in tu.get_includes():
            rel = self.rel(inc.include.name) if inc.include else None
            if rel:
                deps[rel] = file_sha(self.repo / rel)

        def visit(c: ci.Cursor) -> None:
            for x in c.get_children():
                f = x.location.file
                rel = self.rel(f.name) if f else None
                if rel is None:
                    continue
                if x.kind in FUNC_KINDS and x.is_definition():
                    body = next((g for g in x.get_children() if g.kind == K.COMPOUND_STMT), None)
                    if body is not None and x.get_usr() and x.get_usr() not in functions:
                        fn = _Fn(self, x)
                        fn.walk(body)
                        functions[x.get_usr()] = {
                            "name": qualified_name(x), "file": rel, "line": x.extent.start.line,
                            "end": x.extent.end.line, "params": fn.params, "param_out": fn.param_out,
                            "defs": fn.defs, "calls": fn.calls, "conds": fn.conds}
                elif x.kind in (K.NAMESPACE, K.CLASS_DECL, K.STRUCT_DECL, K.CLASS_TEMPLATE, K.LINKAGE_SPEC,
                                K.UNEXPOSED_DECL):
                    visit(x)
        visit(tu.cursor)
        errors = sum(1 for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error)
        return {"deps": deps, "functions": functions, "errors": errors}
