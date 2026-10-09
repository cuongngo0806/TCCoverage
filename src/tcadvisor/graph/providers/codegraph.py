"""codegraph (@colbymchenry/codegraph, MIT): tree-sitter graph in `<repo>/.codegraph/`, CLI `impact -j`."""
from __future__ import annotations

import re

from tcadvisor.graph.providers.base import (Provider, ProviderEdge, ProviderResult, Root, norm_kind,
                                            strip_anon)
from tcadvisor.models import SymbolRef

RELATION = {"calls": "call", "extends": "inherit_override", "implements": "inherit_override",
            "references": "uses_type", "instantiates": "instantiate", "imports": "include", "includes": "include",
            "contains": "contains", "overrides": "inherit_override", "uses": "uses_type"}


class CodegraphProvider(Provider):
    name = "codegraph"
    env_var = "TCADVISOR_CODEGRAPH"
    binary = "codegraph"

    def prepare(self) -> list[str]:
        fresh = not (self.repo / ".codegraph").exists()
        self.run("init", "-y", ".") if fresh else self.run("sync", ".")
        self.exclude_index_dir(".codegraph/")
        return [f"codegraph index {'built' if fresh else 'synced'} in {self.repo / '.codegraph'}"]

    def impact(self, roots: list[Root]) -> ProviderResult:
        res = ProviderResult()
        for root in roots:
            if root.kind == "file":
                continue  # file-level roots use include edges (from the compile database index, if any)
            try:
                data = self.run_json("impact", root.spelling, "-f", root.file, "-d", str(self.depth), "-j")
            except Exception as exc:  # noqa: BLE001
                res.notes.append(f"codegraph impact failed for `{root.name}`: {exc}")
                res.missed.append(root.node_id)
                continue
            defs = data.get("definitions") or []
            chosen = _choose(defs, root)
            if not chosen:
                res.notes.append(f"codegraph has no definition matching `{root.name}` ({root.file}:{root.line})")
                res.missed.append(root.node_id)
                continue
            if len(chosen) > 1:
                res.notes.append(f"codegraph: `{root.name}` matched {len(chosen)} definitions; their impact is merged")
            try:
                for d in chosen:
                    self._add(res, d, root)
            except (KeyError, TypeError, ValueError) as exc:
                res.notes.append(f"codegraph returned unexpected data for `{root.name}`: {exc}")
                res.missed.append(root.node_id)
        return res

    def _add(self, res: ProviderResult, d: dict, root: Root) -> None:
        rid = d["definition"]["id"]
        alias = {rid: root.node_id}
        nodes = {a["id"]: a for a in d.get("affected", [])}
        nodes[rid] = d["definition"]
        # qualify member names via `contains` edges (class -> member)
        owner = {e["target"]: e["source"] for e in d.get("edges", []) if e["kind"] == "contains"}
        for nid, n in nodes.items():
            if nid in alias:
                continue
            name = n.get("qualifiedName") or n.get("name") or nid
            if not n.get("qualifiedName") and nid in owner and owner[nid] in nodes:
                name = f"{nodes[owner[nid]].get('qualifiedName') or nodes[owner[nid]].get('name')}::{name}"
            res.refs[nid] = SymbolRef(name, norm_kind(n.get("kind")), n.get("filePath", ""), max(1, int(n.get("startLine") or 1)))
        for e in d.get("edges", []):
            kind = e.get("kind", "")
            meta = e.get("metadata") or {}
            rel = RELATION.get(kind, "uses_type")
            if meta.get("synthesizedBy") == "cpp-override":
                rel = "inherit_override"
            if kind == "contains":
                dependent, dependency = e["target"], e["source"]
            else:
                dependent, dependency = e["source"], e["target"]
            dep_node = nodes.get(dependent, {})
            if kind == "extends" and not self._real_base(dep_node, meta.get("refName") or ""):
                # observed on leveldb: a data member `Cache* cache_;` reported as `extends`. Base specifiers sit
                # in the class head (`class X : public Base {`); anything else is a member/type reference.
                rel = "uses_type"
            res.edges.append(ProviderEdge(
                alias.get(dependent, dependent), alias.get(dependency, dependency), rel,
                dep_node.get("filePath", ""), int(e.get("line") or dep_node.get("startLine") or 1),
                meta.get("confidence"), e.get("provenance") == "heuristic"))


    def _real_base(self, node: dict, base: str) -> bool:
        try:
            lines = (self.repo / node.get("filePath", "")).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return True
        start = max(0, int(node.get("startLine") or 1) - 1)
        head = " ".join(lines[start:start + 6]).split("{", 1)[0]
        short = base.split("::")[-1]
        return bool(short) and re.search(r":[^;]*\b" + re.escape(short) + r"\b", head) is not None


def _choose(defs: list[dict], root: Root) -> list[dict]:
    if not defs:
        return []
    near = [d for d in defs if d["definition"].get("filePath") == root.file
            and abs(int(d["definition"].get("startLine") or 0) - root.line) <= 3]
    if near:
        return near[:1]
    qn = strip_anon(root.name)
    exact = [d for d in defs if strip_anon(d["definition"].get("qualifiedName") or "") == qn]
    if exact:
        return exact
    same_file = [d for d in defs if d["definition"].get("filePath") == root.file]
    return same_file or (defs if len(defs) == 1 else [])
