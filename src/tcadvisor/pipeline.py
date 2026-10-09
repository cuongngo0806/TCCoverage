"""One Analysis Run, in the constitution's fixed order:

deterministic parse/graph -> diff-to-node impact filtering -> (optional) LLM text -> evidence-gated output.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tcadvisor import __version__
from tcadvisor.cache.store import CacheStore
from tcadvisor.classify.cases import build_cases
from tcadvisor.classify.rules import classify
from tcadvisor.evidence import uncertainty
from tcadvisor.evidence.gate import gate
from tcadvisor.graph.impact import Graph, build_graph, traverse
from tcadvisor.index.clang_index import build_index
from tcadvisor.index.cmake_targets import load_target_model
from tcadvisor.index.compile_db import CompileDatabase
from tcadvisor.ingest import git as G
from tcadvisor.ingest.changes import ChangeSet, explicit_changes, detect_changes
from tcadvisor.ingest.symbols import resolve_symbols
from tcadvisor.models import ChangeInput, ImpactNode, SymbolRef, UsageError


@dataclass
class Options:
    repo: Path
    build_dir: Path
    commit_range: str | None = None
    working_tree: bool = False
    symbols: list[str] | None = None
    max_hop_depth: int = 2
    split_threshold: int = 50
    cache_dir: Path | None = None
    output_dir: Path = Path("tcadvisor-report")
    targets: list[str] | None = None
    llm: bool = False
    llm_endpoint: str = "http://localhost:11434"
    llm_model: str = "qwen2.5-coder:7b"
    allow_stale: bool = False
    use_run_cache: bool = True
    progress: Callable[[str], None] | None = None


@dataclass
class _Ctx:
    old_rev: str | None = None
    new_rev: str | None = None
    fingerprint: str = ""
    notes: list[str] = field(default_factory=list)


def default_cache_dir(repo: Path) -> Path:
    return repo.resolve().parent / ".tcadvisor-cache" / repo.resolve().name


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def run(opts: Options) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    repo = opts.repo.resolve()
    if not (repo / ".git").exists():
        raise UsageError(f"--repo '{repo}' is not a git repository root")
    for label, p in (("--output-dir", opts.output_dir), ("--cache-dir", opts.cache_dir)):
        if p is not None and _is_within(p, repo):
            raise UsageError(f"{label} '{p}' resolves inside the analysed repository; the advisor never writes "
                             "into the analysed repo (Principle VIII)")
    cache = CacheStore(opts.cache_dir or default_cache_dir(repo))
    try:
        return _run(opts, repo, cache, started, t0)
    finally:
        cache.close()


def _run(opts: Options, repo: Path, cache: CacheStore, started: datetime, t0: float) -> dict[str, Any]:
    say = opts.progress or (lambda _m: None)
    cdb = CompileDatabase.load(opts.build_dir.resolve(), repo, allow_stale=opts.allow_stale)
    tmodel = load_target_model(opts.build_dir.resolve())

    ci_ = ChangeInput(mode="explicit_symbols" if opts.symbols else "git_diff", target_repo_path=str(repo),
                      commit_range=opts.commit_range, working_tree=opts.working_tree, symbols=opts.symbols)
    ctx = _Ctx()
    diffs: list[G.FileDiff] = []
    if opts.commit_range:
        if ".." not in opts.commit_range:
            raise UsageError("--commit-range must look like <rev>..<rev>")
        a, b = opts.commit_range.split("..", 1)
        ctx.old_rev, ctx.new_rev = G.resolve_rev(repo, a or "HEAD"), G.resolve_rev(repo, b or "HEAD")
        diffs = G.diff_range(repo, ctx.old_rev, ctx.new_rev)
        head = G.head_or_none(repo)
        if head != ctx.new_rev:
            ctx.notes.append(f"range end {ctx.new_rev[:10]} is not the checked-out HEAD; the dependency index reflects "
                             "the working tree, so unchanged-file line numbers may differ")
    elif opts.working_tree:
        ctx.old_rev = G.head_or_none(repo)
        diffs = G.diff_working_tree(repo, ctx.old_rev)
        ctx.fingerprint = hashlib.sha256(G.working_tree_fingerprint(repo, ctx.old_rev).encode()).hexdigest()

    say("building dependency index")
    facts, index_stats = build_index(repo, cdb, cache, progress=say)
    index_state = hashlib.sha256(json.dumps(
        sorted((k, sorted(v)) for k, v in facts.tu_files.items())).encode()
        + "".join(sorted(f"{s['file']}:{s['line']}:{u}" for u, s in facts.symbols.items())).encode()).hexdigest()

    run_key = hashlib.sha256(json.dumps({
        "v": __version__, "mode": ci_.mode, "old": ctx.old_rev, "new": ctx.new_rev, "wt": ctx.fingerprint,
        "symbols": opts.symbols, "hop": opts.max_hop_depth, "split": opts.split_threshold,
        "targets": sorted(opts.targets or []), "cdb": cdb.digest, "index": index_state,
        "llm": opts.llm, "llm_model": opts.llm_model if opts.llm else None}).encode()).hexdigest()
    if opts.use_run_cache:
        cached = cache.get_run(run_key)
        if cached is not None:
            cached.update(run_id=str(uuid.uuid4()), started_at=started.isoformat(),
                          completed_at=datetime.now(timezone.utc).isoformat(), cache_hit=True)
            cached.setdefault("metrics", {})["duration_seconds"] = round(time.monotonic() - t0, 3)
            cached["metrics"]["index"] = index_stats
            return cached

    graph = build_graph(facts, tmodel, repo)
    # -- change -> roots ------------------------------------------------------------------------
    if opts.symbols:
        resolved = resolve_symbols(opts.symbols, facts)
        usrs = sorted({u for us in resolved.values() for u in us})
        cs = ChangeSet(changes=explicit_changes(repo, usrs, facts.symbols, cdb, facts.tu_files))
        ci_dict_symbols = [graph.symbol_ref(u).to_dict() for u in usrs if graph.symbol_ref(u)]
    else:
        def old_text(rel: str) -> str | None:
            return G.show(repo, ctx.old_rev, rel) if ctx.old_rev else None

        def new_text(rel: str) -> str | None:
            if opts.commit_range:
                return G.show(repo, ctx.new_rev, rel)
            p = repo / rel
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None

        say(f"analysing {len(diffs)} changed file(s)")
        cs = detect_changes(repo, diffs, old_text, new_text, cdb, facts.tu_files)
        ci_dict_symbols = None
    ctx.notes.extend(cs.notes)

    configs = cdb.configurations()
    roots: dict[str, SymbolRef] = {}
    root_risks = {}
    root_kind = {}
    changes = []
    for ch in cs.changes:
        ref = graph.symbol_ref(ch.node_id) if not ch.node_id.startswith("file:") else None
        if ref is None or ch.change_kind == "removed":
            if not (repo / ch.rel_path).is_file():
                ctx.notes.append(f"`{ch.name}` was removed together with its file {ch.rel_path}; only its remaining "
                                 "dependents (if any) are reported")
                continue
            kind = ch.kind if ch.kind in ("function", "method", "class", "struct", "enum", "macro", "variable",
                                          "file") else "function"
            ref = SymbolRef(ch.name if kind != "file" else ch.rel_path, kind, ch.rel_path, max(1, ch.line))
        roots[ch.node_id] = ref
        root_risks[ch.node_id] = classify(ch, configs)
        root_kind[ch.node_id] = ch.change_kind
        changes.append(ch)

    flags, flag_only = uncertainty.detect(changes, roots, graph, cdb)

    # -- traversal (split per CMake target above the threshold, FR-010a) ---------------------------
    groups: dict[str, list[str]] = {"*": list(roots)}
    split_into: list[str] | None = None
    if len(set(cs.changed_files)) > opts.split_threshold:
        groups = {}
        for rid, ref in roots.items():
            ts = sorted(graph.file_targets.get(ref.file_path, ())) or ["(no target)"]
            groups.setdefault(ts[0], []).append(rid)
        split_into = sorted(groups)
        ctx.notes.append(f"{len(set(cs.changed_files))} files changed (> {opts.split_threshold}); analysed as "
                         f"{len(groups)} per-target units")
    nodes: dict[str, ImpactNode] = {}
    for _unit, rids in sorted(groups.items()):
        sub_roots = {r: roots[r] for r in rids}
        sub_groups = {r: {x.risk_group for x in root_risks[r]} for r in rids}
        file_roots = {}
        for r in rids:
            ref = roots[r]
            if (not r.startswith("file:") and ref.file_path.lower().endswith((".h", ".hh", ".hpp", ".hxx", ".inl"))
                    and sub_groups[r] & {"abi_layout", "build_config"}):
                file_roots.setdefault(f"file:{ref.file_path}", r)
        for nid, n in traverse(graph, sub_roots, sub_groups, opts.max_hop_depth, file_roots).items():
            cur = nodes.get(nid)
            if cur is None:
                nodes[nid] = n
            else:
                cur.hop_distance = min(cur.hop_distance, n.hop_distance)
                cur.root_ids |= n.root_ids
                cur.risk_groups |= n.risk_groups
                cur.edges.extend(e for e in n.edges if e not in cur.edges)

    # -- scope (--targets) ------------------------------------------------------------------------
    out_of_scope = list(cs.out_of_scope)
    if opts.targets:
        scope = set(opts.targets)
        unknown = scope - set(tmodel.targets)
        if unknown:
            raise UsageError(f"unknown CMake target(s): {', '.join(sorted(unknown))}")
        for nid in list(nodes):
            n = nodes[nid]
            if n.targets and not (set(n.targets) & scope):
                out_of_scope.append({"path": n.symbol.file_path, "symbol": n.symbol.qualified_name,
                                     "reason": f"belongs only to target(s) {', '.join(n.targets)} outside the "
                                               f"--targets scope"})
                del nodes[nid]
                roots.pop(nid, None)
    for f in cs.non_cpp_files:
        out_of_scope.append({"path": f, "reason": "not a C/C++ or CMake file; not analysed"})

    def targets_of(node: ImpactNode) -> list[str]:
        return list(node.targets)

    cases = build_cases(nodes, root_risks, root_kind, flag_only, targets_of)
    known = {s["name"] for s in facts.symbols.values()} | {r.qualified_name for r in roots.values()}
    cases = gate(cases, repo, known)

    # -- affected targets (FR-005) ---------------------------------------------------------------
    direct_targets = sorted({t for n in nodes.values() for t in n.targets})
    affected = [{"name": t, "relation": "compiles_affected_file"} for t in direct_targets]
    for t in direct_targets:
        for d in sorted(tmodel.dependents_of(t)):
            if d not in direct_targets and all(a["name"] != d for a in affected):
                affected.append({"name": d, "relation": "link_to_target", "via": t})
    target_scope = sorted(opts.targets) if opts.targets else direct_targets

    # -- optional LLM text ------------------------------------------------------------------------
    llm_degraded, llm_usage = False, None
    if opts.llm:
        from tcadvisor.llm.enrich import enrich
        say("LLM enrichment")
        llm_degraded, llm_usage, err = enrich(cases, opts.llm_endpoint, opts.llm_model, opts.output_dir)
        if err:
            ctx.notes.append(f"degraded (LLM unavailable): {err}; deterministic descriptions used")

    ci_dict = ci_.to_dict()
    ci_dict["symbols"] = ci_dict_symbols
    report = {
        "tool": {"name": "tcadvisor", "version": __version__},
        "run_id": str(uuid.uuid4()),
        "change_input": ci_dict,
        "commit_hash": ctx.new_rev if opts.commit_range else ctx.old_rev if opts.working_tree else None,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "cache_hit": False,
        "split_into_modules": split_into,
        "llm_enabled": opts.llm,
        "llm_degraded": llm_degraded,
        "llm_token_usage": llm_usage,
        "target_scope": target_scope,
        "no_detected_impact": not cases and not flags,
        "changed_files": sorted(set(cs.changed_files)),
        "changed_symbols": [{**ch_dict(ch, roots[ch.node_id]), "risks": [r.to_dict() for r in root_risks[ch.node_id]]}
                            for ch in changes if ch.node_id in roots],
        "impact_nodes": [n.to_dict() for n in sorted(nodes.values(), key=lambda n: (n.hop_distance, n.symbol.file_path,
                                                                                   n.symbol.line))],
        "affected_targets": affected,
        "test_case_candidates": [c.to_dict() for c in cases],
        "uncertainty_flags": [f.to_dict() for f in flags],
        "out_of_scope": out_of_scope,
        "run_notes": ctx.notes,
        "metrics": {"duration_seconds": round(time.monotonic() - t0, 3), "index": index_stats,
                    "configurations": configs, "max_hop_depth": opts.max_hop_depth,
                    "parse_errors": sum(facts.parse_errors.values())},
    }
    if facts.parse_errors:
        report["run_notes"].append(f"libclang reported {sum(facts.parse_errors.values())} error diagnostic(s) in "
                                   f"{len(facts.parse_errors)} translation unit(s); results for code that failed to "
                                   "parse may be incomplete")
    if opts.use_run_cache and not llm_degraded:
        cache.put_run(run_key, report["commit_hash"], report)
    return report


def ch_dict(ch, ref: SymbolRef) -> dict[str, Any]:
    return {"id": ch.node_id, "symbol": ref.to_dict(), "change_kind": ch.change_kind,
            "conditions": ch.conditions}


__all__ = ["Options", "run", "default_cache_dir", "Graph"]
