"""Explicit uncertainty flags (FR-007, Principle IV). Blind spots are reported, never dropped."""
from __future__ import annotations

import re

from tcadvisor.graph.impact import Graph
from tcadvisor.index.compile_db import CompileDatabase
from tcadvisor.ingest.changes import SymbolChange
from tcadvisor.models import SymbolRef, UncertaintyFlag

_IDENT = re.compile(r"[A-Za-z_]\w*")
_PP_WORDS = {"if", "ifdef", "ifndef", "elif", "else", "defined", "endif"}
_DYNAMIC_TOKENS = {"dlopen", "dlsym", "GetProcAddress", "LoadLibrary", "function", "bind", "QMetaObject",
                   "invokeMethod", "connect", "signal", "slot", "emit"}


def detect(changes: list[SymbolChange], roots: dict[str, SymbolRef], g: Graph, cdb: CompileDatabase
           ) -> tuple[list[UncertaintyFlag], set[str]]:
    """Return (flags, root ids that must be flagged *instead of* producing cases)."""
    flags: list[UncertaintyFlag] = []
    flag_only: set[str] = set()
    all_defines = [e.defines for e in cdb.entries]
    configs = cdb.configurations()

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
            names = {w for c in ch.conditions for w in _IDENT.findall(c)} - _PP_WORDS
            single_config = [n for n in sorted(names)
                             if all(n in d for d in all_defines) or not any(n in d for d in all_defines)]
            if ch.kind == "file" or single_config:
                which = ", ".join(f"`{n}`" for n in (single_config or sorted(names))) or "the condition"
                state = ("is undefined in every compile command, so this branch was never parsed"
                         if single_config and not any(single_config[0] in d for d in all_defines)
                         else "has the same value in every compile command, so the other branch was never parsed")
                flags.append(UncertaintyFlag(
                    "build_config_incomplete_macro",
                    f"change in {ch.rel_path}:{ch.line} is guarded by `{' && '.join(ch.conditions)}`; {which} {state} "
                    f"(configurations in compile_commands.json: {', '.join(configs)})", ref))
        elif ch.kind != "file":
            words = tokens & {"NDEBUG", "_DEBUG", "DEBUG"}
            if words and len(configs) < 2:
                flags.append(UncertaintyFlag(
                    "build_config_incomplete_macro",
                    f"`{ch.name}` depends on {', '.join(sorted(words))} but compile_commands.json only contains the "
                    f"{', '.join(configs)} configuration", ref))
    return flags, flag_only
