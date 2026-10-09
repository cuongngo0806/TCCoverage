"""GitNexus (abhigyanpatwari/GitNexus). LICENSE: PolyForm-Noncommercial-1.0.0 — opt-in only.

Runs `gitnexus analyze --index-only` (never writes AGENTS.md/CLAUDE.md/skills into the analysed repo),
`gitnexus impact` for the blast radius and `gitnexus cypher` to recover edges + line numbers.
"""
from __future__ import annotations

from tcadvisor.graph.providers.base import Provider, ProviderEdge, ProviderResult, Root, norm_kind
from tcadvisor.models import SymbolRef, UncertaintyFlag

RELATION = {"CALLS": "call", "EXTENDS": "inherit_override", "IMPLEMENTS": "inherit_override",
            "OVERRIDES": "inherit_override", "IMPORTS": "include", "INCLUDES": "include", "USES": "uses_type",
            "REFERENCES": "uses_type", "HAS_METHOD": "contains", "HAS_PROPERTY": "contains",
            "INSTANTIATES": "instantiate", "ACCESSES": "uses_type"}
BOUNDARY_CATEGORY = {"receiverTyping": "dynamic_runtime_dependency", "dispatchBoundary": "di_config_routing",
                     "callableValueReferences": "dynamic_runtime_dependency",
                     "externalBoundary": "dynamic_runtime_dependency"}
SEP = "¦"  # GitNexus ids may contain '|', which breaks its markdown tables


class GitNexusProvider(Provider):
    name = "gitnexus"
    env_var = "TCADVISOR_GITNEXUS"
    binary = "gitnexus"

    def prepare(self) -> list[str]:
        self.run("analyze", ".", "--index-only", "--skip-fts", timeout=3600)
        self.exclude_index_dir(".gitnexus/")
        return ["gitnexus index refreshed (--index-only). NOTE: GitNexus is PolyForm-Noncommercial licensed"]

    def cypher(self, q: str) -> list[list[str]]:
        md = self.run_json("cypher", q).get("markdown", "")
        rows = [r.strip().strip("|").split("|") for r in md.splitlines()[2:] if r.strip()]
        return [[c.strip().replace(SEP, "|") for c in r] for r in rows]

    def impact(self, roots: list[Root]) -> ProviderResult:
        res = ProviderResult()
        for root in roots:
            if root.kind == "file":
                continue
            try:
                data = self.run_json("impact", root.spelling, "-f", root.file, "--depth", str(self.depth))
                if data.get("status") == "ambiguous":
                    cands = sorted(data.get("candidates", []),
                                   key=lambda c: (c.get("filePath") != root.file, abs(int(c.get("line") or 0) - root.line)))
                    if not cands:
                        raise RuntimeError("no candidates")
                    data = self.run_json("impact", "-u", cands[0]["uid"], "--depth", str(self.depth))
            except Exception as exc:  # noqa: BLE001
                res.notes.append(f"gitnexus impact failed for `{root.name}`: {exc}")
                continue
            self._add(res, data, root)
        return res

    def _add(self, res: ProviderResult, data: dict, root: Root) -> None:
        rid = (data.get("target") or {}).get("id")
        if not rid:
            res.notes.append(f"gitnexus: no node for `{root.name}`")
            return
        nodes = {rid: {}}
        for _depth, items in (data.get("byDepth") or {}).items():
            for it in items:
                nodes[it["id"]] = it
                flows = [p.get("label", "") for p in it.get("processes") or []]
                if flows:
                    res.flows[it["id"]] = flows
        for b in data.get("boundaries") or []:
            cats = [BOUNDARY_CATEGORY[k] for k, v in (data.get("causes") or {}).items() if v and k in BOUNDARY_CATEGORY]
            res.flags.append(UncertaintyFlag(cats[0] if cats else "dynamic_runtime_dependency",
                                             f"GitNexus: {b}", SymbolRef(root.name, root.kind if root.kind in (
                                                 "function", "method", "class", "struct") else "function",
                                                 root.file, root.line)))
        ids = [i for i in nodes if i != rid]
        if not ids:
            return
        quoted = ", ".join("'" + i.replace("'", "\\'") + "'" for i in nodes)
        lines = {}
        for r in self.cypher(f"MATCH (n) WHERE n.id IN [{quoted}] RETURN replace(n.id,'|','{SEP}'), n.name, "
                             f"n.filePath, n.startLine"):
            if len(r) >= 4:
                lines[r[0]] = (r[1], r[2], int(r[3]) if r[3].isdigit() else 1)
        for i in ids:
            name, fp, ln = lines.get(i, (nodes[i].get("name", i), nodes[i].get("filePath", ""), 1))
            res.refs[i] = SymbolRef(name, norm_kind(i.split(":", 1)[0]), fp, max(1, ln))
        for r in self.cypher(f"MATCH (a)-[r:CodeRelation]->(b) WHERE a.id IN [{quoted}] AND b.id IN [{quoted}] "
                             f"RETURN replace(a.id,'|','{SEP}'), replace(b.id,'|','{SEP}'), r.type, r.confidence"):
            if len(r) < 4:
                continue
            a, b, typ = r[0], r[1], r[2]
            rel = RELATION.get(typ)
            if rel is None:
                continue
            dependent, dependency = (b, a) if rel == "contains" else (a, b)
            conf = float(r[3]) if r[3].replace(".", "", 1).isdigit() else None
            ref = res.refs.get(dependent)
            res.edges.append(ProviderEdge(root.node_id if dependent == rid else dependent,
                                          root.node_id if dependency == rid else dependency, rel,
                                          ref.file_path if ref else root.file, ref.line if ref else root.line, conf))
