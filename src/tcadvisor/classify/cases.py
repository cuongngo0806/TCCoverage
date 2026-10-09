"""Test-case candidates with deterministic priority (FR-004, FR-004a) and stable ids."""
from __future__ import annotations

from tcadvisor.models import HIGH_SEVERITY, RISK_GROUPS, ImpactEdge, ImpactNode, RiskClassification, \
    SymbolRef, TestCaseCandidate

GROUP_TITLE = {
    "logic": "functional behaviour",
    "abi_layout": "binary / layout compatibility",
    "ownership_lifetime": "object ownership and lifetime",
    "thread_safety": "thread safety",
    "exception_safety": "exception safety",
    "build_config": "behaviour across build configurations",
}
REL_PHRASE = {
    "call": "calls",
    "inherit_override": "inherits from / overrides",
    "uses_type": "uses",
    "instantiate": "instantiates",
    "macro_expand": "expands macro",
    "include": "includes",
    "link_to_target": "links",
    "contains": "is a member of",
}
# include-only (file) nodes only carry compile-level risks
FILE_GROUPS = {"abi_layout", "build_config"}


# Sub-reasons whose only consequence is "recompile" / log output: they rank like logic (pilot: on vsomeip,
# `header_change` alone produced 787 P1 cases and buried the code later fixed for real regressions).
LOW_SUBS = {"header_change", "inline_change", "logging", "test_code"}


def priority(hop: int, group: str, sub: str | None = None) -> str:
    if sub in ("logging", "test_code"):
        return "P3"
    direct = hop <= 1
    high = group in HIGH_SEVERITY and sub not in LOW_SUBS
    if direct and high:
        return "P1"
    if direct or high:
        return "P2"
    return "P3"


def build_cases(nodes: dict[str, ImpactNode], root_risks: dict[str, list[RiskClassification]],
                root_kind: dict[str, str], flag_only: set[str], targets_of,
                tests: dict[str, str] | None = None) -> list[TestCaseCandidate]:
    cases: list[TestCaseCandidate] = []
    for nid, node in nodes.items():
        if node.hop_distance == 0:
            if nid in flag_only:
                continue
            for r in root_risks.get(nid, []):
                desc = (f"Verify the {GROUP_TITLE[r.risk_group]} of `{node.symbol.qualified_name}` "
                        f"({root_kind.get(nid, 'modified')}"
                        + (f", {r.sub_reason.replace('_', ' ')}" if r.sub_reason else "") + ")")
                cases.append(TestCaseCandidate(
                    id="", description=desc, activation_condition=f"Changed directly: {r.detail}",
                    evidence=[node.symbol], risk_group=r.risk_group,
                    priority=priority(0, r.risk_group, r.sub_reason),
                    related_cmake_targets=targets_of(node), node_id=nid, sub_reason=r.sub_reason,
                    hop_distance=0, hints=list(r.hints)))
            continue
        roots = sorted(node.root_ids - flag_only)
        if not roots:
            continue
        groups = sorted({r.risk_group for rid in roots for r in root_risks.get(rid, [])}, key=RISK_GROUPS.index)
        if node.symbol.kind == "file":
            groups = [g for g in groups if g in FILE_GROUPS] or (["abi_layout"] if groups else [])
        for grp in groups:
            g_roots = [rid for rid in roots if any(r.risk_group == grp for r in root_risks.get(rid, []))] or roots
            hop = min(node.root_hops.get(rid, node.hop_distance) for rid in g_roots)
            near = sorted(rid for rid in g_roots if node.root_hops.get(rid, node.hop_distance) == hop)
            reasons = [r for rid in near for r in root_risks.get(rid, []) if r.risk_group == grp] or \
                [r for rid in near for r in root_risks.get(rid, [])]
            edges = [e for rid in near for e in node.root_edges.get(rid, [])]
            first: ImpactEdge | None = edges[0] if edges else (node.edges[0] if node.edges else None)
            via = (f"{REL_PHRASE.get(first.relation, first.relation)} `{first.to_symbol.qualified_name}`"
                   if first else "depends on the change")
            hints = list(dict.fromkeys(h for r in reasons for h in r.hints))[:6]
            subs = sorted({r.sub_reason for r in reasons if r.sub_reason})
            hop_word = "direct" if hop == 1 else f"indirect, {hop} hops"
            if tests and nid in tests:
                desc = (f"Re-run existing test `{tests[nid]}` and check it still covers the "
                        f"{GROUP_TITLE[grp]} of the change (it {via}; {hop_word})")
            elif node.symbol.kind == "file":
                path = node.symbol.file_path
                if path.lower().endswith((".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tpp")):
                    desc = f"Recompile and re-test all code including header `{path}` ({hop_word}; it {via})"
                else:
                    desc = f"Rebuild and smoke-test translation unit `{path}` ({hop_word}; it {via})"
            else:
                desc = (f"Re-verify the {GROUP_TITLE[grp]} of `{node.symbol.qualified_name}`, which {via} "
                        f"({hop_word})")
            if subs:
                desc += f" — {', '.join(s.replace('_', ' ') for s in subs)}"
            act = f"Reachable from changed {', '.join(_root_label(nodes, r) for r in near[:3])}" \
                  f"{' and others' if len(near) > 3 else ''}: {reasons[0].detail}"
            evidence: list[SymbolRef | ImpactEdge] = [node.symbol] + (edges or node.edges)[:3]
            cases.append(TestCaseCandidate(
                id="", description=desc, activation_condition=act, evidence=evidence,
                priority=priority(hop, grp, next((x for x in subs if x not in LOW_SUBS), subs[0] if subs else None)),
                risk_group=grp, related_cmake_targets=targets_of(node),
                node_id=nid, sub_reason=subs[0] if subs else None, hop_distance=hop, hints=hints))
    # within a priority: closest first, then the most concentrated risk (several strong risk groups on one
    # changed symbol, or one impacted symbol reached from many changed roots) — deterministic, no model
    def score(c: TestCaseCandidate) -> int:
        if c.hop_distance == 0:
            return len({r.risk_group for r in root_risks.get(c.node_id, []) if r.sub_reason not in LOW_SUBS})
        return len(nodes[c.node_id].root_ids) if c.node_id in nodes else 0

    cases.sort(key=lambda c: (c.priority, c.hop_distance, -score(c), RISK_GROUPS.index(c.risk_group),
                              c.evidence[0].file_path if isinstance(c.evidence[0], SymbolRef) else "",
                              c.evidence[0].line if isinstance(c.evidence[0], SymbolRef) else 0,
                              c.description))
    for i, c in enumerate(cases, 1):
        c.id = f"TC-{i:04d}"
    return cases


def _root_label(nodes: dict[str, ImpactNode], rid: str) -> str:
    n = nodes.get(rid)
    return f"`{n.symbol.qualified_name}`" if n else f"`{rid}`"
