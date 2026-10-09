"""Deterministic libclang indexer (research.md §1).

Per translation unit we extract *facts* (symbols, edges, includes, address-taken functions, macro
uses) restricted to files inside the analysed repository. Facts are cached per TU, keyed by the
content hash of the TU and every repo-local file it includes, so only TUs touched by a change are
re-parsed (FR-010, constitution "subgraph-only invalidation").
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import clang.cindex as ci

from tcadvisor.index.compile_db import CPP_HEADER_EXT, CompileDatabase, resource_dir_args

K = ci.CursorKind

FUNC_KINDS = {K.FUNCTION_DECL, K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.CONVERSION_FUNCTION,
              K.FUNCTION_TEMPLATE}
CLASS_KINDS = {K.CLASS_DECL, K.STRUCT_DECL, K.UNION_DECL, K.CLASS_TEMPLATE,
               K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION}
SYMBOL_KINDS = FUNC_KINDS | CLASS_KINDS | {K.ENUM_DECL, K.MACRO_DEFINITION, K.VAR_DECL}
SCOPE_KINDS = {K.NAMESPACE, K.CLASS_DECL, K.STRUCT_DECL, K.UNION_DECL, K.CLASS_TEMPLATE,
               K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION, K.ENUM_DECL}
TRANSPARENT_EXPR = {K.UNEXPOSED_EXPR, K.PAREN_EXPR}

PARSE_OPTS = (ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
              | ci.TranslationUnit.PARSE_INCOMPLETE
              | getattr(ci.TranslationUnit, "PARSE_KEEP_GOING", 0x200))

_index: ci.Index | None = None


def clang_index() -> ci.Index:
    global _index
    if _index is None:
        _index = ci.Index.create()
    return _index


def file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def symbol_kind(c: ci.Cursor) -> str:
    k = c.kind
    if k == K.MACRO_DEFINITION:
        return "macro"
    if k == K.ENUM_DECL:
        return "enum"
    if k == K.VAR_DECL:
        return "variable"
    if k in (K.STRUCT_DECL, K.UNION_DECL):
        return "struct"
    if k in CLASS_KINDS:
        return "class"
    if k in (K.CXX_METHOD, K.CONSTRUCTOR, K.DESTRUCTOR, K.CONVERSION_FUNCTION):
        return "method"
    if k == K.FUNCTION_TEMPLATE:
        sp = c.semantic_parent
        return "method" if sp is not None and sp.kind in CLASS_KINDS else "function"
    return "function"


def qualified_name(c: ci.Cursor) -> str:
    parts = [c.spelling or "(anonymous)"]
    p = c.semantic_parent
    while p is not None and p.kind in SCOPE_KINDS:
        parts.append(p.spelling or "(anonymous)")
        p = p.semantic_parent
    return "::".join(reversed(parts))


def template_of(c: ci.Cursor) -> ci.Cursor | None:
    try:
        t = ci.conf.lib.clang_getSpecializedCursorTemplate(c)
    except Exception:  # pragma: no cover - binding differences
        return None
    if t is None or t.kind.is_invalid():
        return None
    return t


def is_global_var(c: ci.Cursor) -> bool:
    sp = c.semantic_parent
    return sp is not None and sp.kind in (K.TRANSLATION_UNIT, K.NAMESPACE) or (
        sp is not None and sp.kind in CLASS_KINDS and c.storage_class == ci.StorageClass.STATIC)


@dataclass
class IndexFacts:
    """Merged facts of all translation units (the in-memory dependency index)."""

    repo: Path
    symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: set[tuple[str, str, str, str, int]] = field(default_factory=set)  # (rel, from, to, file, line)
    includes: set[tuple[str, str, int]] = field(default_factory=set)  # (includer, included, line)
    address_taken: dict[str, tuple[str, int]] = field(default_factory=dict)  # usr -> (file, line)
    macro_uses: set[tuple[str, str, int]] = field(default_factory=set)  # (macro usr, file, line)
    tu_files: dict[str, set[str]] = field(default_factory=dict)  # TU main rel -> repo files it includes
    parse_errors: dict[str, int] = field(default_factory=dict)

    def merge(self, tu_rel: str, facts: dict[str, Any]) -> None:
        for usr, s in facts["symbols"].items():
            old = self.symbols.get(usr)
            if old is None or (s["is_def"] and not old["is_def"]):
                merged = dict(s)
                if old is not None:
                    merged["decl_files"] = sorted(set(old.get("decl_files", [])) | {old["file"]})
                self.symbols[usr] = merged
            elif old is not None and s["file"] != old["file"]:
                old.setdefault("decl_files", [])
                if s["file"] not in old["decl_files"]:
                    old["decl_files"].append(s["file"])
        self.edges.update(tuple(e) for e in facts["edges"])
        self.includes.update(tuple(i) for i in facts["includes"])
        for usr, loc in facts["address_taken"].items():
            self.address_taken.setdefault(usr, tuple(loc))
        self.macro_uses.update(tuple(m) for m in facts["macro_uses"])
        self.tu_files[tu_rel] = set(facts["deps"].keys())
        if facts.get("errors"):
            self.parse_errors[tu_rel] = facts["errors"]


class TUExtractor:
    def __init__(self, repo: Path):
        self.repo = repo.resolve()
        self._rel_cache: dict[str, str | None] = {}

    def rel(self, filename: str | None) -> str | None:
        if not filename:
            return None
        r = self._rel_cache.get(filename, "?")
        if r != "?":
            return r
        try:
            p = Path(os.path.realpath(filename))
            r = p.relative_to(self.repo).as_posix()
            if r.startswith(".tcadvisor") or "/CMakeFiles/" in r:
                r = None
        except ValueError:
            r = None
        self._rel_cache[filename] = r
        return r

    def parse(self, path: Path, args: tuple[str, ...], unsaved: list[tuple[str, str]] | None = None) -> ci.TranslationUnit:
        full_args = list(args) + list(resource_dir_args())
        if path.suffix.lower() in CPP_HEADER_EXT and "-x" not in full_args:
            full_args = ["-x", "c++-header"] + full_args
        return clang_index().parse(str(path), args=full_args, unsaved_files=unsaved, options=PARSE_OPTS)

    def extract(self, path: Path, args: tuple[str, ...]) -> dict[str, Any]:
        tu = self.parse(path, args)
        symbols: dict[str, dict[str, Any]] = {}
        edges: set[tuple] = set()
        address_taken: dict[str, tuple[str, int]] = {}
        macro_uses: set[tuple] = set()
        main_rel = self.rel(str(path))

        def add_symbol(c: ci.Cursor, rel: str) -> str | None:
            usr = c.get_usr()
            if not usr or (not c.spelling and c.kind != K.MACRO_DEFINITION):
                return None
            is_def = bool(c.is_definition()) or c.kind == K.MACRO_DEFINITION
            cur = symbols.get(usr)
            if cur is None or (is_def and not cur["is_def"]):
                kind = c.kind
                tmpl = kind in (K.FUNCTION_TEMPLATE, K.CLASS_TEMPLATE, K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION)
                virtual = False
                if kind == K.CXX_METHOD:
                    virtual = bool(c.is_virtual_method())
                elif kind == K.DESTRUCTOR:
                    virtual = bool(getattr(c, "is_virtual_method", lambda: False)())
                symbols[usr] = {
                    "usr": usr,
                    "name": qualified_name(c),
                    "spelling": c.spelling,
                    "display": c.displayname,
                    "kind": symbol_kind(c),
                    "file": rel,
                    "line": c.extent.start.line,
                    "end_line": c.extent.end.line,
                    "is_def": is_def,
                    "is_template": tmpl,
                    "is_virtual": virtual,
                    "parent": c.semantic_parent.get_usr() if c.semantic_parent is not None
                    and c.semantic_parent.kind in CLASS_KINDS else None,
                }
            return usr

        def visit(c: ci.Cursor, ctx: str | None, ctx_file: str, stack: list[ci.Cursor]) -> None:
            kind = c.kind
            loc_file = c.location.file
            rel = self.rel(loc_file.name) if loc_file else ctx_file
            if rel is None:
                return
            line = c.location.line
            new_ctx = ctx
            if kind in SYMBOL_KINDS:
                if kind == K.VAR_DECL and not is_global_var(c):
                    pass
                else:
                    usr = add_symbol(c, rel)
                    if usr and kind != K.VAR_DECL:
                        new_ctx = usr
                    elif usr and kind == K.VAR_DECL and ctx is None:
                        new_ctx = usr
            elif kind == K.CXX_BASE_SPECIFIER and ctx:
                ref = c.referenced
                if ref is not None:
                    t = template_of(ref) or ref
                    if t.get_usr():
                        edges.add(("inherit_override", ctx, t.get_usr(), rel, line))
            elif kind == K.CALL_EXPR and ctx:
                ref = c.referenced
                if ref is not None and ref.kind in FUNC_KINDS and ref.get_usr():
                    t = template_of(ref)
                    if t is not None and t.get_usr() and t.get_usr() != ref.get_usr():
                        edges.add(("call", ctx, t.get_usr(), rel, line))
                        edges.add(("instantiate", ctx, t.get_usr(), rel, line))
                    else:
                        edges.add(("call", ctx, ref.get_usr(), rel, line))
                    if ref.kind == K.CONSTRUCTOR and ref.semantic_parent is not None:
                        edges.add(("uses_type", ctx, ref.semantic_parent.get_usr(), rel, line))
            elif kind in (K.DECL_REF_EXPR, K.MEMBER_REF_EXPR, K.OVERLOADED_DECL_REF) and ctx:
                ref = c.referenced
                if ref is not None and ref.get_usr():
                    if ref.kind in FUNC_KINDS:
                        # callee of the enclosing call expression, or address taken (callback / fn pointer)?
                        parent = next((p for p in reversed(stack) if p.kind not in TRANSPARENT_EXPR), None)
                        is_callee = (parent is not None and parent.kind == K.CALL_EXPR
                                     and parent.referenced is not None
                                     and parent.referenced.get_usr() == ref.get_usr())
                        if not is_callee:
                            t = template_of(ref) or ref
                            address_taken.setdefault(t.get_usr(), (rel, line))
                            edges.add(("call", ctx, t.get_usr(), rel, line))
                    elif ref.kind == K.FIELD_DECL and ref.semantic_parent is not None:
                        edges.add(("uses_type", ctx, ref.semantic_parent.get_usr(), rel, line))
                    elif ref.kind == K.VAR_DECL and is_global_var(ref):
                        edges.add(("uses_type", ctx, ref.get_usr(), rel, line))
                    elif ref.kind == K.ENUM_CONSTANT_DECL and ref.semantic_parent is not None:
                        edges.add(("uses_type", ctx, ref.semantic_parent.get_usr(), rel, line))
            elif kind == K.TYPE_REF and ctx:
                ref = c.referenced
                if ref is not None and ref.get_usr() and (ref.kind in CLASS_KINDS or ref.kind == K.ENUM_DECL):
                    t = template_of(ref)
                    if t is not None and t.get_usr():
                        edges.add(("instantiate", ctx, t.get_usr(), rel, line))
                    if ref.get_usr() != ctx:
                        edges.add(("uses_type", ctx, ref.get_usr(), rel, line))
            elif kind == K.TEMPLATE_REF and ctx:
                ref = c.referenced
                if ref is not None and ref.get_usr() and ref.get_usr() != ctx:
                    edges.add(("instantiate", ctx, ref.get_usr(), rel, line))
            elif kind == K.MACRO_INSTANTIATION:
                ref = c.referenced
                if ref is not None and ref.get_usr() and self.rel(ref.location.file.name if ref.location.file else None):
                    macro_uses.add((ref.get_usr(), rel, line))
                return
            stack.append(c)
            for ch in c.get_children():
                visit(ch, new_ctx, rel, stack)
            stack.pop()

        for top in tu.cursor.get_children():
            f = top.location.file
            if f is None or self.rel(f.name) is None:
                continue
            visit(top, None, self.rel(f.name) or "", [])

        includes = set()
        deps: dict[str, str] = {}
        if main_rel:
            deps[main_rel] = file_sha(path)
        for inc in tu.get_includes():
            src = self.rel(inc.source.name) if inc.source else None
            dst = self.rel(inc.include.name) if inc.include else None
            if dst:
                deps[dst] = file_sha(self.repo / dst)
            if src and dst:
                includes.add((src, dst, inc.location.line))
        errors = sum(1 for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error)
        return {
            "deps": deps,
            "symbols": symbols,
            "edges": sorted(edges),
            "includes": sorted(includes),
            "address_taken": address_taken,
            "macro_uses": sorted(macro_uses),
            "errors": errors,
        }


def build_index(repo: Path, cdb: CompileDatabase, cache: Any, progress: Callable[[str], None] | None = None
                ) -> tuple[IndexFacts, dict[str, int]]:
    """Index every repo-local TU in the compile database, reusing cached facts when still valid."""
    repo = repo.resolve()
    extractor = TUExtractor(repo)
    facts = IndexFacts(repo)
    stats = {"tus": 0, "reparsed": 0, "reused": 0}
    for entry in cdb.entries:
        rel = extractor.rel(str(entry.file))
        if rel is None:
            continue
        stats["tus"] += 1
        args_key = hashlib.sha256("\0".join(entry.args).encode()).hexdigest()
        cached = cache.get_tu(rel, args_key) if cache else None
        if cached is not None and all(file_sha(repo / d) == h for d, h in cached["deps"].items()):
            stats["reused"] += 1
            facts.merge(rel, cached)
            continue
        if progress:
            progress(f"indexing {rel}")
        tu_facts = extractor.extract(entry.file, entry.args)
        stats["reparsed"] += 1
        if cache:
            cache.put_tu(rel, args_key, tu_facts)
        facts.merge(rel, tu_facts)
    return facts, stats
