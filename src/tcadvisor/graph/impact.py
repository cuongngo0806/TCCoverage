"""Dependency graph + bounded impact traversal (FR-002) and file -> target mapping (FR-005)."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from tcadvisor.index.clang_index import IndexFacts
from tcadvisor.index.cmake_targets import TargetModel
from tcadvisor.models import ImpactEdge, ImpactNode, SymbolRef

KIND_OK = {"function", "method", "class", "struct", "enum", "macro", "variable", "file"}


@dataclass
class Dep:
    dependent: str  # node that is affected when ``dependency`` changes
    relation: str
    file: str
    line: int


@dataclass
class Graph:
    facts: IndexFacts
    dependents: dict[str, list[Dep]] = field(default_factory=lambda: defaultdict(list))
    by_name: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    override_group: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    file_targets: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    refs: dict[str, SymbolRef] = field(default_factory=dict)  # nodes contributed by an external graph provider

    def symbol_ref(self, node_id: str) -> SymbolRef | None:
        if node_id in self.refs:
            return self.refs[node_id]
        if node_id.startswith("file:"):
            rel = node_id[5:]
            return SymbolRef(rel, "file", rel, 1)
        s = self.facts.symbols.get(node_id)
        if s is None or not s.get("file"):
            return None
        kind = s["kind"] if s["kind"] in KIND_OK else "function"
        return SymbolRef(s["name"], kind, s["file"], max(1, int(s["line"])))

    def file_of(self, node_id: str) -> str | None:
        if node_id.startswith("file:"):
            return node_id[5:]
        s = self.facts.symbols.get(node_id)
        return s.get("file") if s else None

    def callers(self, node_id: str) -> list[Dep]:
        return [d for d in self.dependents.get(node_id, []) if d.relation == "call"]


def build_graph(facts: IndexFacts, targets: TargetModel | None, repo: Path) -> Graph:
    g = Graph(facts)
    syms = facts.symbols
    for usr, s in syms.items():
        g.by_name[s["name"]].append(usr)
    for rel, frm, to, file, line in sorted(facts.edges):
        if frm == to or to not in syms:
            continue
        g.dependents[to].append(Dep(frm, rel, file, line))
    # overrides: method M in class C overrides same-signature virtual method of a (transitive) base
    bases: dict[str, set[str]] = defaultdict(set)
    for rel, frm, to, _f, _l in facts.edges:
        if rel == "inherit_override" and frm in syms and syms[frm]["kind"] in ("class", "struct"):
            bases[frm].add(to)
    methods_by_class: dict[str, dict[str, str]] = defaultdict(dict)
    for usr, s in syms.items():
        if s["kind"] == "method" and s.get("parent"):
            methods_by_class[s["parent"]][s.get("display") or s["spelling"]] = usr

    def all_bases(c: str, seen: set[str]) -> set[str]:
        for b in bases.get(c, ()):
            if b not in seen:
                seen.add(b)
                all_bases(b, seen)
        return seen

    for cls, methods in methods_by_class.items():
        for b in all_bases(cls, set()):
            for disp, m in methods.items():
                bm = methods_by_class.get(b, {}).get(disp)
                if bm and (syms[bm].get("is_virtual") or syms[m].get("is_virtual")):
                    s = syms[m]
                    g.dependents[bm].append(Dep(m, "inherit_override", s["file"], s["line"]))
                    g.dependents[m].append(Dep(bm, "inherit_override", s["file"], s["line"]))
                    g.override_group[m].add(bm)
                    g.override_group[bm].add(m)
    # macro expansions: attribute to the innermost enclosing function/method/class, else the file
    ranges: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for usr, s in syms.items():
        if s["kind"] in ("function", "method", "class", "struct") and s.get("is_def") and s.get("file"):
            ranges[s["file"]].append((s["line"], s.get("end_line", s["line"]), usr))
    for macro, file, line in sorted(facts.macro_uses):
        enclosing = [r for r in ranges.get(file, ()) if r[0] <= line <= r[1]]
        user = min(enclosing, key=lambda r: r[1] - r[0])[2] if enclosing else f"file:{file}"
        if user != macro:
            g.dependents[macro].append(Dep(user, "macro_expand", file, line))
    for includer, included, line in sorted(facts.includes):
        g.dependents[f"file:{included}"].append(Dep(f"file:{includer}", "include", includer, line))
    # file -> targets (sources directly, headers through the TUs that include them)
    if targets is not None:
        for tu_rel, deps in facts.tu_files.items():
            ts = targets.targets_for((repo / tu_rel).resolve())
            g.file_targets[tu_rel] |= ts
            for d in deps:
                g.file_targets[d] |= ts
        for abs_path, ts in targets.file_to_targets.items():
            try:
                g.file_targets[abs_path.relative_to(repo.resolve()).as_posix()] |= ts
            except ValueError:
                pass
    return g


def traverse(g: Graph, roots: dict[str, SymbolRef], root_groups: dict[str, set[str]], max_hop: int,
             file_roots: dict[str, str], root_relations: dict[str, set[str] | None] | None = None
             ) -> dict[str, ImpactNode]:
    """Breadth-first walk over *dependents*, run per root so every node knows its hop distance to
    each root that reaches it (priority must not be inflated by an unrelated, closer root).

    ``file_roots`` maps a header ``file:`` node to the root that requires include-level propagation
    (ABI/layout or build-config changes in headers).
    """
    nodes: dict[str, ImpactNode] = {}

    def node(nid: str, ref: SymbolRef, hop: int) -> ImpactNode:
        n = nodes.get(nid)
        if n is None:
            n = nodes[nid] = ImpactNode(nid, ref, hop)
        n.hop_distance = min(n.hop_distance, hop)
        return n

    for rid, rref in roots.items():
        groups = set(root_groups.get(rid, ()))
        r = node(rid, rref, 0)
        r.hop_distance = 0
        r.root_ids.add(rid)
        r.risk_groups |= groups
        r.root_hops[rid] = 0
        seen = {rid: 0}
        q: deque[tuple[str, SymbolRef, int]] = deque([(rid, rref, 0)])
        for fid, frid in file_roots.items():
            if frid == rid and fid not in seen and fid not in roots:
                fref = g.symbol_ref(fid)
                seen[fid] = 1
                fn = node(fid, fref, 1)
                fn.add_reach(rid, 1, groups, ImpactEdge("include", fref, rref, fref.file_path, rref.line))
                q.append((fid, fref, 1))
        while q:
            cur, cref, hop = q.popleft()
            if hop >= max_hop:
                continue
            allowed = (root_relations or {}).get(rid) if hop == 0 else None
            for dep in g.dependents.get(cur, ()):  # deterministic order (edges were sorted)
                if allowed is not None and dep.relation not in allowed:
                    continue
                if dep.relation == "contains" and hop > 0:
                    continue  # members are affected by their *changed* class only, not by every class on the path
                if dep.dependent in roots:
                    continue  # another changed root: it is traversed from itself, at hop 0
                ref = g.symbol_ref(dep.dependent)
                if ref is None:
                    continue
                edge = ImpactEdge(dep.relation, ref, cref, dep.file, dep.line)
                prev = seen.get(dep.dependent)
                if prev is None:
                    seen[dep.dependent] = hop + 1
                    q.append((dep.dependent, ref, hop + 1))
                if prev is None or prev == hop + 1:
                    node(dep.dependent, ref, hop + 1).add_reach(rid, hop + 1, groups, edge)
    for n in nodes.values():
        f = n.symbol.file_path
        n.targets = sorted(g.file_targets.get(f, ()))
    return nodes
