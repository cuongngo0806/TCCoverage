"""Test-case candidates with deterministic priority (FR-004, FR-004a) and stable ids."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

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
    "called_by_change": "is now called differently by",
}
MAX_SOURCES = 8  # spec 006 edge case: more sibling sources are summarised in one case
# include-only (file) nodes only carry compile-level risks
FILE_GROUPS = {"abi_layout", "build_config"}


# Sub-reasons whose only consequence is "recompile" / log output: they rank like logic (pilot: on vsomeip,
# `header_change` alone produced 787 P1 cases and buried the code later fixed for real regressions).
LOW_SUBS = {"header_change", "inline_change", "logging", "test_code"}


# lesson-pattern cases that only ask to confirm something already present (spec 006)
PATTERN_LOW_SUBS = {"sibling_source_guarded", "sibling_source_more", "data_path_forwarder",
                    "data_path_emitter_checked"}
SEVERITY = {"thread_safety": 3, "ownership_lifetime": 3, "exception_safety": 3, "abi_layout": 2, "logic": 2,
            "build_config": 1}
# For *impacted* symbols, a changed signature is checked by the compiler at every call site.
IMPACT_LOW_SUBS = {"signature_change"}


def priority(hop: int, group: str, sub: str | None = None) -> str:
    if sub in ("logging", "test_code"):
        return "P3"
    direct = hop <= 1
    high = group in HIGH_SEVERITY and sub not in LOW_SUBS and not (hop > 0 and sub in IMPACT_LOW_SUBS)
    if direct and high:
        return "P1"
    if direct or high:
        return "P2"
    return "P3"


def build_cases(nodes: dict[str, ImpactNode], root_risks: dict[str, list[RiskClassification]],
                root_kind: dict[str, str], flag_only: set[str], targets_of,
                tests: dict[str, str] | None = None, root_weight: dict[str, int] | None = None,
                file_history: dict[str, int] | None = None,
                root_external: dict[str, list[RiskClassification]] | None = None,
                extra: list[TestCaseCandidate] | None = None) -> list[TestCaseCandidate]:
    """``root_external``: third-party boundary risks (spec 005) — cases on the changed symbol only, never
    propagated to its callers."""
    weight = root_weight or {}
    external = root_external or {}
    history = file_history or {}
    cases: list[TestCaseCandidate] = []
    for nid, node in nodes.items():
        if node.hop_distance == 0:
            if nid in flag_only:
                continue
            for r in root_risks.get(nid, []) + external.get(nid, []):
                desc = (f"Verify the {GROUP_TITLE[r.risk_group]} of `{node.symbol.qualified_name}` "
                        f"({root_kind.get(nid, 'modified')}"
                        + (f", {r.sub_reason.replace('_', ' ')}" if r.sub_reason else "") + ")")
                if r.sub_reason == "external_call":
                    desc = (f"Verify how `{node.symbol.qualified_name}` handles failures and unusual behaviour of "
                            f"the third-party API it now calls ({GROUP_TITLE[r.risk_group]} first)")
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
                priority=priority(hop, grp, next((x for x in subs if x not in LOW_SUBS | IMPACT_LOW_SUBS),
                                                 subs[0] if subs else None)),
                risk_group=grp, related_cmake_targets=targets_of(node),
                node_id=nid, sub_reason=subs[0] if subs else None, hop_distance=hop, hints=hints))
    cases.extend(extra or [])  # lesson-pattern cases (spec 006), built elsewhere, ranked with the rest
    # Relevance order (tuned on 55 real regressions in vsomeip + RocksDB, dev/holdout split — see
    # specs/004-ranking): closest to the change first; substantive risks before recompile-only / log / test
    # ones; bigger changes first (log2 of changed lines of the root, or of all roots reaching an impacted
    # symbol); then how bug-prone the file was (fix commits in the last 12 months); then risk-group severity
    # and fan-in; third-party API boundary cases (spec 005) last among hop-0 cases. Deterministic, no model.
    # The P1/P2/P3 label keeps the FR-004a meaning (hop distance x severity); the list order adds change size.
    def key(c: TestCaseCandidate):
        if c.hop_distance == 0:
            lines, fan_in = weight.get(c.node_id, 0), 1
        else:
            rs = nodes[c.node_id].root_ids if c.node_id in nodes else set()
            lines, fan_in = sum(weight.get(r, 0) for r in rs), len(rs)
        low = c.sub_reason in LOW_SUBS or (c.hop_distance > 0 and c.sub_reason in IMPACT_LOW_SUBS) or \
            c.sub_reason in PATTERN_LOW_SUBS
        ev = c.evidence[0]
        hist = history.get(ev.file_path, 0) if isinstance(ev, SymbolRef) else 0
        c.bug_history = hist
        return (c.hop_distance, c.sub_reason == "external_call", low, -int(math.log2(1 + lines)), -int(math.log2(1 + hist)), -SEVERITY[c.risk_group],
                -fan_in,
                RISK_GROUPS.index(c.risk_group), ev.file_path if isinstance(ev, SymbolRef) else "",
                ev.line if isinstance(ev, SymbolRef) else 0, c.description)

    cases.sort(key=key)
    for i, c in enumerate(cases, 1):
        c.id = f"TC-{i:04d}"
    return cases


def _root_label(nodes: dict[str, ImpactNode], rid: str) -> str:
    n = nodes.get(rid)
    return f"`{n.symbol.qualified_name}`" if n else f"`{rid}`"


def assign_keys(cases: list[TestCaseCandidate], nodes: dict[str, ImpactNode], repo: Path) -> None:
    """Stable identity + code fingerprint per case (spec 006 FR-612, research R6).

    ``key`` hashes what the case is about (evidence symbol, file, risk group, reason, the changed symbols that
    reach it, the pattern counterpart) — not its list position, so test results recorded on a case survive
    re-ranking. ``code_fingerprint`` hashes the comment-free text of the evidence function: when it differs
    from the one stored with a carried-over result, that result needs a re-check.
    """
    from tcadvisor.ingest.changes import strip_comments, textual_functions
    files: dict[str, tuple[list[str], list[tuple[str, int, int]]]] = {}

    def text_of(ref: SymbolRef) -> str:
        if ref.file_path not in files:
            try:
                lines = (repo / ref.file_path).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                lines = []
            files[ref.file_path] = (lines, textual_functions(lines) if ref.kind != "file" else [])
        lines, fns = files[ref.file_path]
        span = [f for f in fns if f[1] <= ref.line <= f[2]]
        if ref.kind != "file" and span:
            _n, a, b = min(span, key=lambda f: f[2] - f[1])
            lines = lines[a - 1:b]
        return "".join(strip_comments("\n".join(lines)).split())

    seen: dict[str, int] = {}
    for c in cases:
        ev = next(e for e in c.evidence if isinstance(e, SymbolRef))
        node = nodes.get(c.node_id)
        roots = sorted(nodes[r].symbol.qualified_name if r in nodes else r
                       for r in (node.root_ids if node is not None and c.hop_distance > 0 else {c.node_id}))
        counterpart = "|".join(f"{s.role}:{s.symbol.qualified_name}" for s in (c.path or []))
        raw = "\x1f".join([ev.qualified_name, ev.file_path, c.risk_group, c.sub_reason or "", ",".join(roots),
                            c.pattern or "", counterpart])
        key = hashlib.sha1(raw.encode()).hexdigest()[:12]
        n = seen.get(key, 0) + 1
        seen[key] = n
        c.key = key if n == 1 else f"{key}-{n}"
        c.code_fingerprint = hashlib.sha1(text_of(ev).encode()).hexdigest()[:12]


def sibling_source_cases(guarded, graph, roots: dict[str, SymbolRef]) -> list[TestCaseCandidate]:
    """Spec 006 US2: one case per other trigger source of a function that the change protected in one source."""
    from tcadvisor.models import PathStep
    out: list[TestCaseCandidate] = []
    for t in guarded:
        covered = [roots[r] for r in t.covered if r in roots]
        cov_names = ", ".join(f"`{c.qualified_name}`" for c in covered)
        guard = "; ".join(dict.fromkeys(t.guard_lines))[:160]
        others = [s for s in t.sources if not s.covered_by_change]
        for i, s in enumerate(others):
            targets = sorted(graph.file_targets.get(s.symbol.file_path, ())) or ["(no CMake target owns this file)"]
            edge = ImpactEdge("call", s.symbol, t.target, s.symbol.file_path, s.call_line)
            path = [PathStep(s.symbol, "source", s.call_line,
                             detail=(f"callback registered at {s.registered_at[0]}:{s.registered_at[1]}"
                                     if s.registered_at else "calls the target")),
                    PathStep(t.target, "target", t.target.line)]
            via = (f" (a callback registered at {s.registered_at[0]}:{s.registered_at[1]})" if s.registered_at else "")
            if i >= MAX_SOURCES:
                rest = others[MAX_SOURCES:]
                out.append(TestCaseCandidate(
                    id="", description=f"`{t.target.qualified_name}` has {len(rest)} more trigger source(s) not "
                                       f"protected like {cov_names}: "
                                       + ", ".join(f"`{x.symbol.qualified_name}`" for x in rest[:12])
                                       + (" …" if len(rest) > 12 else ""),
                    activation_condition=f"Guard added in {cov_names}: {guard}",
                    evidence=[t.target], priority="P3", risk_group="logic",
                    related_cmake_targets=targets, node_id=t.covered[0], sub_reason="sibling_source_more",
                    hop_distance=1, pattern="sibling_source",
                    hints=[f"Check each listed source reaches `{t.target.qualified_name}` only in states the new guard "
                           "allows"]))
                break
            present = s.guard == "present"
            sub = "sibling_source_guarded" if present else "sibling_source"
            if present:
                desc = (f"Confirm the existing check in `{s.symbol.qualified_name}`{via} is equivalent to the guard "
                        f"added in {cov_names} before calling `{t.target.qualified_name}`")
            else:
                desc = (f"`{t.target.qualified_name}` is also triggered from `{s.symbol.qualified_name}`{via}: check "
                        f"that the situation now guarded in {cov_names} cannot reach it this way")
            hints = [f"Drive `{s.symbol.qualified_name}` into the state the new guard rejects "
                     f"({', '.join(sorted(t.guard_ids)[:6])}) and check `{t.target.qualified_name}` is not reached "
                     "or handles it",
                     f"Compare with {cov_names}: same condition, same error handling / logging, same return value"]
            if s.registered_at:
                hints.append(f"The callback can fire at any time after registration at {s.registered_at[0]}:"
                             f"{s.registered_at[1]}: trigger it while the guarded condition holds")
            if s.guard == "unknown":
                hints.append("The call is not visible in the source text (macro / indirection): confirm the path "
                             "manually")
            out.append(TestCaseCandidate(
                id="", description=desc, activation_condition=f"Guard added in {cov_names}: {guard}",
                evidence=[s.symbol, edge], priority="P3" if present else priority(1, "logic", sub),
                risk_group="logic", related_cmake_targets=targets, node_id=t.covered[0], sub_reason=sub,
                hop_distance=1, pattern="sibling_source", path=path, hints=hints))
    return out


def data_path_cases(paths, index, graph) -> list[TestCaseCandidate]:
    """Spec 006 US1: a case on each function that emits data originating in a changed function (and, lower,
    on the functions that only pass it on). One case per (emitter, producer) and per (forwarder, producer)."""
    from tcadvisor.models import PathStep
    out: list[TestCaseCandidate] = []
    done: set[tuple[str, str, str]] = set()

    def ref(st) -> SymbolRef:
        f = index.functions.get(st.usr, {})
        return SymbolRef(st.name, "function", st.file, max(1, f.get("line", st.line)))

    for p in sorted(paths, key=lambda p: (len(p.steps), bool(p.checked), p.steps[-1].file, p.emitter_line)):
        prod, em = p.steps[0], p.steps[-1]
        chain = " → ".join(f"`{s.name}`" for s in p.steps)
        steps = [PathStep(ref(s), s.role, s.line, bool(s.checked_at),
                          s.detail or (f"checks it at line {s.checked_at}" if s.checked_at else "")) for s in p.steps]
        hop = len(p.steps) - 1
        targets = sorted(graph.file_targets.get(em.file, ())) or ["(no CMake target owns this file)"]
        checked = [s for s in p.checked]
        if (em.usr, prod.usr, "e") not in done:
            done.add((em.usr, prod.usr, "e"))
            sub = "data_path_emitter_checked" if checked else "data_path_emitter"
            where = ", ".join(f"`{s.name}` line {s.checked_at}" for s in checked)
            desc = (f"`{em.name}` sends data that originates in the changed `{prod.name}` ({chain}) through "
                    f"`{p.emitter_call}`: " + (f"confirm the check in {where} covers the values `{prod.name}` can "
                                               "now produce" if checked else
                                               "check it validates the data itself instead of trusting the producer"))
            hints = [f"Feed `{em.name}` with every value `{prod.name}` can now produce (boundary, invalid, empty, "
                     f"maximum length) and check what goes out through `{p.emitter_call}`",
                     f"`{em.name}` owns what it sends: malformed input must be rejected or corrected, not forwarded",
                     "Compare the outgoing data with the interface specification of the receiver (format, ranges, "
                     "mandatory fields)"]
            if checked:
                hints.insert(1, f"Existing check: {where} — confirm it rejects the new values, not only the old ones")
            out.append(TestCaseCandidate(
                id="", description=desc,
                activation_condition=f"Data path from the changed `{prod.name}` (line {prod.line}): {chain}",
                evidence=[ref(em), ref(prod)], priority=priority(hop, "logic", sub), risk_group="logic",
                related_cmake_targets=targets, node_id=p.root, sub_reason=sub, hop_distance=max(1, hop),
                pattern="data_path_emitter", path=steps, hints=hints))
        for s in p.steps[1:-1]:
            if (s.usr, prod.usr, "f") in done or s.usr == em.usr:
                continue
            done.add((s.usr, prod.usr, "f"))
            ftargets = sorted(graph.file_targets.get(s.file, ())) or ["(no CMake target owns this file)"]
            out.append(TestCaseCandidate(
                id="", description=(f"`{s.name}` passes data from the changed `{prod.name}` on to `{em.name}` "
                                    + ("after checking it" if s.checked_at else "without checking it")),
                activation_condition=f"Data path: {chain}", evidence=[ref(s), ref(prod)],
                priority=priority(max(1, p.steps.index(s)), "logic", "data_path_forwarder"), risk_group="logic",
                related_cmake_targets=ftargets, node_id=p.root, sub_reason="data_path_forwarder",
                hop_distance=max(1, p.steps.index(s)), pattern="data_path_forwarder", path=steps,
                hints=[f"Pass the values `{prod.name}` can now produce through `{s.name}` and check nothing it does "
                       "(copy, conversion, truncation) changes their meaning"]))
    return out
