"""Test scenarios (spec 013): the cases of a report part grouped into runnable tests.

A *flow* scenario is one call path ``entry → … → changed symbol``: a test entering at the outermost caller walks
every function on it, so it covers every case whose node lies on the path. Paths are picked by greedy set cover
(most newly covered cases, then best priority, then fewest steps, then names). A *group* scenario gathers the cases
reached through one non-call relation (class member ``contains``, ``include``, ``inherit_override``, …) of the same
changed dependency: they share one risk, so one representative test (plus the rebuild) covers it.

Pure, deterministic function of the cases and the impact graph (no LLM): every case lands in exactly one scenario,
the case list itself is unchanged (it stays the evidence-backed contract).
"""
from __future__ import annotations

from typing import Any

from tcadvisor.classify.environment import action
from tcadvisor.classify.rules import HINTS

GENERIC_CHECKS = frozenset(h for hs in HINTS.values() for h in hs)
ACTION_ORDER = ("test_on_target", "review", "closed_by_review", "not_needed")
PRIO = {"P1": 1, "P2": 2, "P3": 3}
MAX_PATHS_PER_START = 64


def _sym_key(s: dict[str, Any]) -> tuple[str, str]:
    return s["qualified_name"], s.get("file_path", "")


def _case_link(c: dict[str, Any]) -> dict[str, Any] | None:
    """The edge that put a non-changed case on the list (its first relation evidence)."""
    return next((e for e in c.get("evidence") or [] if "relation" in e), None)


def _sym(s: dict[str, Any]) -> dict[str, Any]:
    return {k: s[k] for k in ("qualified_name", "kind", "file_path", "line") if k in s}


class _Graph:
    def __init__(self, nodes: list[dict[str, Any]]):
        self.nodes = {n["id"]: n for n in nodes}
        by_key: dict[tuple[str, str], list[str]] = {}
        by_name: dict[str, list[str]] = {}
        for n in nodes:
            by_key.setdefault(_sym_key(n["symbol"]), []).append(n["id"])
            by_name.setdefault(n["symbol"]["qualified_name"], []).append(n["id"])
        self.down: dict[str, list[tuple[str, int]]] = {}
        for n in nodes:
            out = []
            for e in n.get("edges") or []:
                if e.get("relation") != "call":
                    continue
                ids = by_key.get(_sym_key(e["to_symbol"])) or by_name.get(e["to_symbol"]["qualified_name"]) or []
                line = (e.get("source_location") or {}).get("line", 0)
                out += [(t, line) for t in ids if self.nodes[t]["hop_distance"] < n["hop_distance"]]
            self.down[n["id"]] = sorted(set(out), key=lambda x: (self.name(x[0]), x[0], x[1]))

    def name(self, nid: str) -> str:
        return self.nodes[nid]["symbol"]["qualified_name"]

    def paths(self, start: str) -> list[list[str]]:
        """Downward call paths from ``start`` to a node with no callee in the graph (hop strictly decreases)."""
        out: list[list[str]] = []
        stack = [[start]]
        while stack and len(out) < MAX_PATHS_PER_START:
            p = stack.pop()
            nxt = [t for t, _ in self.down.get(p[-1], []) if t not in p]
            if not nxt:
                out.append(p)
            stack += [p + [t] for t in reversed(dict.fromkeys(nxt))]
        return out


def _checks(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    """AI corner cases first, then concrete rule corner cases (changed end first); generic hints only if nothing
    else; exact-text de-dup."""
    order = sorted(cases, key=lambda c: (c.get("hop_distance", 0), PRIO.get(c["priority"], 9)))
    seen: set[str] = set()
    ai, rule, generic = [], [], []
    for c in order:
        for t in (c.get("verification") or {}).get("extra_corner_cases") or []:
            if t not in seen:
                seen.add(t)
                ai.append({"text": t, "source": "ai"})
    for c in order:
        for t in c.get("corner_cases") or []:
            if t not in seen:
                seen.add(t)
                (generic if t in GENERIC_CHECKS else rule).append({"text": t, "source": "rule"})
    return ai + rule + ([] if ai or rule else generic)


def _scenario(kind: str, cases: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    acts = [action(c) for c in cases]
    return {"kind": kind, "priority": min((c["priority"] for c in cases), key=lambda p: PRIO.get(p, 9)),
            "action": min(acts, key=ACTION_ORDER.index),
            **kw,
            "cases": [c["id"] for c in cases], "keys": [c.get("key", "") for c in cases],
            "sub_reasons": list(dict.fromkeys(c["sub_reason"] for c in cases if c.get("sub_reason"))),
            "risk_groups": list(dict.fromkeys(c["risk_group"] for c in cases)),
            "checks": _checks(cases)}


def build(cases: list[dict[str, Any]], nodes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Scenarios covering ``cases`` (each case exactly once), in plan order with ids ``S1``…"""
    g = _Graph(nodes or [])
    pos = {c["id"]: i for i, c in enumerate(cases)}
    flow: dict[str, list[dict[str, Any]]] = {}  # node id -> its flow cases
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    alone: list[dict[str, Any]] = []
    for c in cases:
        link = _case_link(c)
        nid = c.get("node_id") or ""
        if nid in g.nodes and (c.get("hop_distance", 0) == 0 or (link or {}).get("relation") == "call"):
            flow.setdefault(nid, []).append(c)
        elif link is not None:
            to = link["to_symbol"]
            groups.setdefault((to["qualified_name"], to.get("file_path", ""), link["relation"]), []).append(c)
        else:
            alone.append(c)

    out: list[dict[str, Any]] = []
    best = {nid: min(PRIO.get(c["priority"], 9) for c in cs) for nid, cs in flow.items()}
    candidates = [p for start in sorted(flow, key=lambda n: (g.name(n), n)) for p in g.paths(start)]
    left = set(flow)
    while left:
        def score(p: list[str]) -> tuple:
            new = [n for n in p if n in left]
            return (-len(new), min((best[n] for n in new), default=9), len(p), [g.name(n) for n in p], p)
        path = min(candidates, key=score, default=None)
        if path is None or not any(n in left for n in path):
            path = [min(left, key=lambda n: (best[n], g.name(n), n))]  # unreachable by any candidate (defensive)
        covered = [n for n in path if n in left]
        left -= set(covered)
        cs = [c for n in path if n in covered for c in sorted(flow[n], key=lambda c: pos[c["id"]])]  # entry first
        calls = [next((ln for t, ln in g.down.get(a, []) if t == b), 0) for a, b in zip(path, path[1:])] + [0]
        steps = [{"symbol": _sym(g.nodes[n]["symbol"]), "call_line": ln,
                  "cases": [c["id"] for c in flow.get(n, []) if n in covered],
                  "changed": g.nodes[n]["hop_distance"] == 0} for n, ln in zip(path, calls)]
        out.append(_scenario("flow", cs, entry=steps[0]["symbol"], steps=steps, relation="call", members=[]))

    for (_name, _file, rel), cs in groups.items():
        cs = sorted(cs, key=lambda c: pos[c["id"]])
        rep = min(cs, key=lambda c: (PRIO.get(c["priority"], 9), c.get("hop_distance", 0), pos[c["id"]]))
        link = _case_link(rep)
        members = list({_sym_key(m): m for m in (_sym(_case_link(c)["from_symbol"]) for c in cs)}.values())
        steps = [{"symbol": _sym(link["from_symbol"]), "call_line": link["source_location"]["line"],
                  "cases": [c["id"] for c in cs], "changed": False},
                 {"symbol": _sym(link["to_symbol"]), "call_line": 0, "cases": [],
                  "changed": rep.get("hop_distance", 0) == 1}]
        out.append(_scenario("group", cs, entry=steps[0]["symbol"], steps=steps, relation=rel, members=members))

    for c in alone:
        ev = (c.get("evidence") or [{}])[0]
        sym = _sym(ev) if "qualified_name" in ev else {"qualified_name": c["id"], "kind": "case",
                                                       "file_path": "", "line": 0}
        out.append(_scenario("flow", [c], entry=sym, relation="call", members=[],
                             steps=[{"symbol": sym, "call_line": 0, "cases": [c["id"]],
                                     "changed": c.get("hop_distance", 0) == 0}]))

    out.sort(key=lambda s: (ACTION_ORDER.index(s["action"]), PRIO.get(s["priority"], 9), -len(s["cases"]),
                            min(pos[i] for i in s["cases"])))
    return [{"id": f"S{i}", **s} for i, s in enumerate(out, 1)]


def case_scenario(scenarios: list[dict[str, Any]]) -> dict[str, str]:
    """case id -> scenario id."""
    return {cid: s["id"] for s in scenarios for cid in s["cases"]}


def localize_scenarios(scenarios: list[dict[str, Any]], T: Any) -> list[dict[str, Any]]:
    """Rule checks in the report language; AI checks are already in the user's language and stay as written."""
    if not T.active:
        return scenarios
    return [{**s, "checks": [{**k, "text": T(k["text"]) if k["source"] == "rule" else k["text"]}
                             for k in s["checks"]]} for s in scenarios]


def top_checks(s: dict[str, Any], n: int = 6) -> list[dict[str, str]]:
    """The ``n`` checks a renderer shows: AI corner cases (input + expected result) first, but at least two of the
    deterministic rule checks (what the change removed / altered) when there are any; the rest are counted."""
    ai = [k for k in s["checks"] if k["source"] == "ai"]
    rule = [k for k in s["checks"] if k["source"] != "ai"]
    keep_rule = min(len(rule), 2, n)
    picked = ai[:n - keep_rule] + rule[:keep_rule]
    picked += rule[keep_rule:keep_rule + n - len(picked)]
    return picked
