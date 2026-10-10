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
from tcadvisor.classify.cases import assign_keys, build_cases
from tcadvisor.classify.rules import classify
from tcadvisor.evidence import uncertainty
from tcadvisor.evidence.gate import gate
from tcadvisor.graph.impact import Graph, build_graph, traverse
from tcadvisor.index.clang_index import build_index
from tcadvisor.index.cmake_targets import load_target_model
from tcadvisor.index.compile_db import CompileDatabase
from tcadvisor.ingest import git as G
from tcadvisor.ingest.changes import ChangeSet, explicit_changes, detect_changes, is_test_path
from tcadvisor.ingest.symbols import resolve_symbols
from tcadvisor.classify.external import ExternalCall, external_risk, is_standard, load_contracts
from tcadvisor.classify.lessons import load_lessons
from tcadvisor.report.results import carry_over, read_results
from tcadvisor.models import ChangeInput, ImpactNode, PrerequisiteError, RiskClassification, SymbolRef, UncertaintyFlag, \
    UsageError


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
    graph: str = "clang"  # auto|codegraph|gitnexus|clang (spec 002)
    index: str = "auto"  # auto|full|lite: lite (include scan only) is the default with a graph provider
    fallback_max_tus: int = 200
    history: bool = True  # rank by bug-fix history of files (git log, local)
    jobs: int | None = None
    graph_bin: str | None = None
    contracts: Path | None = None  # spec 005: third-party API contracts (default <repo>/.tcadvisor/...)
    lessons: Path | None = None  # spec 006: sinks + team lessons (default <repo>/.tcadvisor/lessons.json)
    previous_report: Path | None = None  # spec 006: filled report.html whose test results are carried over
    flow_max_tus: int = 60  # spec 006: TUs parsed for data-path facts
    patterns: bool = True  # spec 006: data paths, trigger sources, lesson patterns
    attachment_warn_mb: int = 50
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
    previous = read_results(opts.previous_report) if opts.previous_report else None
    cache = CacheStore(opts.cache_dir or default_cache_dir(repo))
    try:
        report = _run(opts, repo, cache, started, t0)
    finally:
        cache.close()
    # tester results (spec 006): applied after the run cache, never part of the analysis itself (FR-613)
    report.setdefault("metrics", {})["attachment_warn_mb"] = opts.attachment_warn_mb
    if previous is not None:
        report["test_results"] = carry_over(previous, report, opts.attachment_warn_mb)
    return report


def _run(opts: Options, repo: Path, cache: CacheStore, started: datetime, t0: float) -> dict[str, Any]:
    say = opts.progress or (lambda _m: None)
    from tcadvisor.graph.providers.base import get_provider
    provider = get_provider(opts.graph, repo, opts.max_hop_depth, opts.graph_bin)
    early_notes: list[str] = []
    try:
        cdb = CompileDatabase.load(opts.build_dir.resolve(), repo, allow_stale=opts.allow_stale)
    except PrerequisiteError as exc:
        if provider is None:
            raise
        cdb = CompileDatabase(opts.build_dir, [], "none")
        early_notes.append(f"reduced accuracy: {exc} Change classification uses fallback compiler flags; "
                           f"impact comes from {provider.name}")
    try:
        tmodel = load_target_model(opts.build_dir.resolve())
    except PrerequisiteError as exc:
        if provider is None:
            raise
        tmodel = None
        early_notes.append(f"no CMake target mapping: {exc}")

    ci_ = ChangeInput(mode="explicit_symbols" if opts.symbols else "git_diff", target_repo_path=str(repo),
                      commit_range=opts.commit_range, working_tree=opts.working_tree, symbols=opts.symbols)
    ctx = _Ctx()
    ctx.notes.extend(early_notes)
    diffs: list[G.FileDiff] = []
    if opts.commit_range:
        if ".." not in opts.commit_range:
            raise UsageError("--commit-range must look like <rev>..<rev>")
        a, b = opts.commit_range.split("..", 1)
        ctx.old_rev, ctx.new_rev = G.resolve_rev(repo, a or "HEAD"), G.resolve_rev(repo, b or "HEAD")
        diffs = G.diff_range(repo, ctx.old_rev, ctx.new_rev)
        head = G.head_or_none(repo)
        dirty = bool(G.git(repo, "status", "--porcelain", "--untracked-files=no").strip())
        if provider is not None and (head != ctx.new_rev or dirty):
            # the provider indexes the working tree: results depend on it, so never serve them from the run cache
            opts.use_run_cache = False
            ctx.notes.append(f"{provider.name} indexes the working tree, which is not identical to {ctx.new_rev[:10]}; "
                             "check out the range end for exact provider impact")
        if head != ctx.new_rev:
            ctx.notes.append(f"range end {ctx.new_rev[:10]} is not the checked-out HEAD; the dependency index reflects "
                             "the working tree, so unchanged-file line numbers may differ")
    elif opts.working_tree:
        ctx.old_rev = G.head_or_none(repo)
        diffs = G.diff_working_tree(repo, ctx.old_rev)
        ctx.fingerprint = hashlib.sha256(G.working_tree_fingerprint(repo, ctx.old_rev).encode()).hexdigest()

    lite = opts.index == "lite" or (opts.index == "auto" and provider is not None)
    if lite:
        from tcadvisor.index.include_scan import scan
        say("scanning includes (lite index: impact comes from the graph provider)")
        facts, index_stats = scan(repo, cdb)
    else:
        say("building dependency index")
        facts, index_stats = build_index(repo, cdb, cache, progress=say, jobs=opts.jobs)
    index_state = hashlib.sha256(json.dumps(
        sorted((k, sorted(v)) for k, v in facts.tu_files.items())).encode()
        + "".join(sorted(f"{s['file']}:{s['line']}:{u}" for u, s in facts.symbols.items())).encode()).hexdigest()

    contracts = load_contracts(repo, opts.contracts)
    lessons = load_lessons(repo, opts.lessons)
    run_key = hashlib.sha256(json.dumps({
        "v": __version__, "code": _code_digest(), "mode": ci_.mode, "old": ctx.old_rev, "new": ctx.new_rev, "wt": ctx.fingerprint,
        "symbols": opts.symbols, "hop": opts.max_hop_depth, "split": opts.split_threshold,
        "targets": sorted(opts.targets or []), "cdb": cdb.digest, "index": index_state,
        "llm": opts.llm, "llm_model": opts.llm_model if opts.llm else None,
        "graph": provider.name if provider else "clang", "contracts": contracts,
        "lessons": lessons.to_key(), "patterns": opts.patterns, "flow_tus": opts.flow_max_tus}).encode()).hexdigest()
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
        cs = detect_changes(repo, diffs, old_text, new_text, cdb, facts.tu_files,
                            fallback_args=_fallback_args(repo) if provider is not None else None)
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

    flows: dict[str, list[str]] = {}
    if provider is not None:
        from tcadvisor.graph.providers.base import Root, build_overlay
        from tcadvisor.graph.providers.base import ProviderResult, copy_subgraph
        say(f"impact via {provider.name}")
        proots = [Root(ch.node_id, roots[ch.node_id].qualified_name, roots[ch.node_id].qualified_name.split("::")[-1],
                       roots[ch.node_id].kind, roots[ch.node_id].file_path, roots[ch.node_id].line) for ch in changes
                  # a removed symbol no longer exists in the provider's index; its former callers changed in the
                  # same commit (they are roots themselves), so there is nothing to look up
                  if ch.change_kind != "removed" and not ch.is_test_code]
        try:
            ctx.notes.extend(provider.prepare())
            pres = provider.impact(proots)
        except Exception as exc:  # noqa: BLE001 - a broken provider must not hide impact
            pres = ProviderResult(missed=[r.node_id for r in proots if r.kind != "file"],
                                  notes=[f"{provider.name} failed ({type(exc).__name__}: {str(exc)[:300]}); "
                                         "falling back to the compile-database graph"])
        overlay = build_overlay(graph, facts, pres)
        for fid, deps in graph.dependents.items():  # header include propagation still comes from the compile db
            if fid.startswith("file:"):
                overlay.dependents[fid].extend(d for d in deps if d.relation == "include")
        provider_flags = list(pres.flags)
        fallback = graph
        if pres.missed and lite and cdb.entries:
            # the lite index has no call graph: build the full libclang index only now that it is needed
            # ... restricted to the TUs that include a missed root's file (from the lite include graph)
            missed_files = {roots[r].file_path for r in pres.missed}
            # a definition in foo.cpp is used through its declaring header (foo.h): include same-stem headers
            stems = {Path(f).stem for f in missed_files}
            missed_files |= {inc for src, inc, _l in facts.includes if src in missed_files and Path(inc).stem in stems}
            sub = [e for e in cdb.entries if missed_files & facts.tu_files.get(
                e.file.relative_to(repo).as_posix() if e.file.is_relative_to(repo) else "", set())]
            if len(sub) > opts.fallback_max_tus:
                # bounded cost (constitution V): flag instead of re-indexing most of the code base
                ctx.notes.append(f"libclang fallback skipped: {len(sub)} TUs include the unresolved roots "
                                 f"(> --fallback-max-tus {opts.fallback_max_tus}); they are flagged for manual review")
                sub = []
            if sub:
                say(f"{len(pres.missed)} root(s) unresolved by {provider.name}: libclang fallback over {len(sub)} TU(s)")
                ctx.notes.append(f"{len(pres.missed)} root(s) unresolved by {provider.name}; their dependents come from "
                                 f"a libclang index of the {len(sub)} translation unit(s) that include them")
                full_facts, _st = build_index(repo, CompileDatabase(cdb.build_dir, sub, cdb.digest), cache,
                                              progress=say, jobs=opts.jobs)
                fallback = build_graph(full_facts, tmodel, repo)
        for rid in pres.missed:  # provider could not resolve this root: use the libclang graph, else flag it
            if not copy_subgraph(fallback, overlay, rid, opts.max_hop_depth):
                provider_flags.append(UncertaintyFlag(
                    "dynamic_runtime_dependency",
                    f"{provider.name} could not resolve `{roots[rid].qualified_name}` and no compile-database graph is "
                    "available; its dependents are unknown — review manually", roots[rid]))
        graph = overlay
        ctx.notes.extend(dict.fromkeys(pres.notes))
        flows = pres.flows
    else:
        provider_flags = []
    external_flags, root_external = _add_changed_calls(repo, changes, roots, graph, ctx.notes, contracts)
    flags, flag_only = uncertainty.detect(changes, roots, graph, cdb)
    flags.extend(provider_flags)
    flags.extend(external_flags)

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
        rel_limits = {ch.node_id: ch.propagation() for ch in changes if ch.node_id in sub_roots}
        for nid, n in traverse(graph, sub_roots, sub_groups, opts.max_hop_depth, file_roots, rel_limits).items():
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
        unknown = scope - set(tmodel.targets if tmodel else ())
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

    from tcadvisor.graph.providers.base import gtest_label
    tests = {nid: lbl for nid, n in nodes.items() if n.hop_distance > 0 and (lbl := gtest_label(repo, n.symbol))}
    history = G.fix_history(repo, ctx.new_rev or ctx.old_rev) if opts.history else {}
    pattern_cases: list = []
    guarded = []
    flow_known: set[str] = set()
    if opts.patterns:
        from tcadvisor.classify.cases import sibling_source_cases
        from tcadvisor.graph.sources import find_guarded_targets, unresolved_source_flags
        guarded = find_guarded_targets(repo, graph, changes, roots)
        pattern_cases += sibling_source_cases(guarded, graph, roots)
        flags.extend(unresolved_source_flags(graph, guarded, roots))
        guarded = [t for t in guarded if any(not x.covered_by_change for x in t.sources) or t.target_id in
                   graph.facts.address_taken]
        from tcadvisor.classify.patterns import detect as detect_patterns
        pattern_cases += detect_patterns(repo, ctx.new_rev if opts.commit_range else None, changes, roots, graph,
                                         lambda f: graph.file_targets.get(f, set()))
        flow_known, flow_flags = _data_paths(opts, repo, cdb, facts, cache, graph, changes, roots, lessons,
                                             pattern_cases, ctx.notes)
        flags.extend(flow_flags)
    cases = build_cases(nodes, root_risks, root_kind, flag_only, targets_of, tests,
                        {ch.node_id: len(ch.added_lines) + len(ch.removed_lines) for ch in changes}, history,
                        root_external, pattern_cases)
    if opts.patterns:
        from tcadvisor.classify.patterns import apply_lessons
        apply_lessons(cases, lessons, changes, nodes)
    known = ({s["name"] for s in facts.symbols.values()} | {r.qualified_name for r in roots.values()}
             | {r.qualified_name for r in graph.refs.values()} | (flow_known if opts.patterns else set())
             | {c.evidence[0].qualified_name for c in pattern_cases})  # text-found code, file checked by the gate
    cases = gate(cases, repo, known)
    assign_keys(cases, nodes, repo)

    # -- affected targets (FR-005) ---------------------------------------------------------------
    direct_targets = sorted({t for n in nodes.values() for t in n.targets})
    affected = [{"name": t, "relation": "compiles_affected_file"} for t in direct_targets]
    for t in direct_targets:
        for d in sorted(tmodel.dependents_of(t) if tmodel else ()):
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
        "changed_symbols": [{**ch_dict(ch, roots[ch.node_id]), "risks": [r.to_dict() for r in root_risks[ch.node_id] + root_external.get(ch.node_id, [])]}
                            for ch in changes if ch.node_id in roots],
        "graph_provider": provider.name if provider else "clang",
        "impact_nodes": [{**n.to_dict(), **({"flows": flows[nid]} if nid in flows else {}),
                          **({"test": tests[nid]} if nid in tests else {})}
                         for nid, n in sorted(nodes.items(), key=lambda kv: (kv[1].hop_distance, kv[1].symbol.file_path,
                                                                             kv[1].symbol.line))],
        "existing_tests": [{"test": lbl, "file_path": nodes[nid].symbol.file_path, "line": nodes[nid].symbol.line,
                            "hop_distance": nodes[nid].hop_distance} for nid, lbl in sorted(tests.items(), key=lambda kv: kv[1])],
        "affected_targets": affected,
        "test_case_candidates": [c.to_dict() for c in cases],
        "trigger_sources": [{"target": t.target.to_dict(), "guard": list(dict.fromkeys(t.guard_lines)),
                             "covered_by": [roots[r].qualified_name for r in t.covered if r in roots],
                             "sources": [{"symbol": x.symbol.to_dict(), "kind": x.kind, "call_line": x.call_line,
                                          "registered_at": list(x.registered_at) if x.registered_at else None,
                                          "covered_by_change": x.covered_by_change, "guard": x.guard}
                                         for x in t.sources]} for t in guarded],
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


def _data_paths(opts: Options, repo: Path, cdb: CompileDatabase, facts, cache, graph: Graph, changes: list,
                roots: dict[str, SymbolRef], lessons, out_cases: list, notes: list[str]
                ) -> tuple[set[str], list[UncertaintyFlag]]:
    """Spec 006 US1: follow changed data to the code that sends it out (bounded, cached flow facts)."""
    from tcadvisor.classify.cases import data_path_cases
    from tcadvisor.graph.dataflow import FlowIndex, trace
    if not cdb.entries:
        notes.append("data paths not traced: no compile database")
        return set(), []
    by_file = {}
    for e in cdb.entries:
        try:
            by_file.setdefault(e.file.resolve().relative_to(repo).as_posix(), e)
        except ValueError:
            continue

    def tu_of_header(rel: str) -> str | None:
        return next((tu for tu, inc in sorted(facts.tu_files.items()) if rel in inc and tu in by_file), None)
    index = FlowIndex(repo, by_file, tu_of_header, cache, opts.flow_max_tus)
    starts = [(ch.node_id, roots[ch.node_id], set(ch.added_line_numbers)) for ch in changes
              if ch.node_id in roots and ch.kind in ("function", "method") and ch.new is not None
              and not ch.is_test_code and not ch.is_log_only and ch.added_line_numbers]
    paths, breaks = trace(index, starts, graph.callers, opts.max_hop_depth + 1, lessons.sinks,
                          lambda name, decl: not is_standard(name, decl))
    out_cases += data_path_cases(paths, index, graph)
    flags: list[UncertaintyFlag] = []
    by_root: dict[str, list] = {}
    for b in breaks:
        by_root.setdefault(b.root, []).append(b)
    for rid, bs in by_root.items():
        uniq = list(dict.fromkeys(f"{b.reason} in {b.where}" for b in bs))
        flags.append(UncertaintyFlag(
            "dynamic_runtime_dependency",
            f"data produced by the changed `{roots[rid].qualified_name}` leaves the traced paths: "
            + "; ".join(uniq[:5]) + (f" and {len(uniq) - 5} more" if len(uniq) > 5 else "")
            + " — review who reads it and whether they send it out", roots[rid]))
    if index.exhausted:
        notes.append(f"data paths traced over {len(index.loaded)} translation unit(s) (--flow-max-tus); "
                     "longer paths are flagged, not traced")
    return {f["name"] for f in index.functions.values()}, flags


def _add_changed_calls(repo: Path, changes: list, roots: dict[str, SymbolRef], graph: Graph,
                       notes: list[str], contracts: dict[str, list[str]] | None = None, per_root: int = 8
                       ) -> tuple[list[UncertaintyFlag], dict[str, list[RiskClassification]]]:
    """Downstream impact: a function called *differently* on a changed line (new call / new arguments) may
    now receive inputs it was never tested with (pilot: RocksDB #14227 changed what CompactionJob handed to
    BlobFileBuilder; the fix landed in BlobFileBuilder). Edges are terminal: the callee's other callers are
    not affected.

    Callees declared outside the repository (third-party libraries) have no body to trace: they are
    returned as uncertainty flags on the calling root (constitution IV) instead of being dropped, plus one
    boundary case per root built from their declarations (spec 005). Standard-library calls and third-party
    calls inside logging statements are only counted in the run notes."""
    from tcadvisor.graph.impact import Dep
    flags: list[UncertaintyFlag] = []
    risks: dict[str, list[RiskClassification]] = {}
    std_calls = log_calls = 0
    for ch in changes:
        if ch.node_id not in roots:
            continue
        n = 0
        external: dict[str, ExternalCall] = {}
        for usr, qn, kind, decl_file, decl_line, call_line in ch.changed_calls():
            if usr in roots:
                continue
            ref = graph.symbol_ref(usr)
            if ref is None:
                rel = None
                if decl_file:
                    try:
                        rel = Path(decl_file).resolve().relative_to(repo).as_posix()
                    except ValueError:
                        pass
                if rel is None:  # declared outside the repository
                    if is_standard(qn, decl_file):
                        std_calls += 1
                    elif call_line in ch.log_lines:  # e.g. `LOG << syscall(SYS_gettid)`: only log output changes
                        log_calls += 1
                    elif qn not in external:
                        where = "/".join(Path(decl_file).parts[-2:]) if decl_file else "declaration not found"
                        external[qn] = ExternalCall(qn, where, ch.rel_path, call_line, ch.new.call_sigs.get(usr, {}))
                    continue
            if n >= per_root:
                continue
            if ref is None:
                rel, decl_line = _definition_site(repo, rel, qn, decl_line)
                ref = SymbolRef(qn, kind if kind in ("function", "method") else "function", rel, max(1, decl_line))
                graph.refs[usr] = ref
            if is_test_path(ref.file_path):
                continue
            graph.dependents[ch.node_id].append(Dep(usr, "called_by_change", ch.rel_path, call_line))
            n += 1
        if external:
            risk = external_risk(ch.name, list(external.values()), contracts)
            if risk is not None:
                risks[ch.node_id] = [risk]
            shown = [f"`{c.name}` ({c.header}) at {c.call_file}:{c.call_line}" for c in list(external.values())[:10]]
            more = f" and {len(external) - len(shown)} more" if len(external) > len(shown) else ""
            flags.append(UncertaintyFlag(
                "dynamic_runtime_dependency",
                f"`{ch.name}` calls code outside the repository on changed lines: {', '.join(shown)}{more}; its "
                "behaviour is not in the static graph — check the call site for error/null returns, exceptions, "
                "ownership of passed/returned pointers and callbacks", roots[ch.node_id]))
    if std_calls:
        notes.append(f"{std_calls} standard-library call(s) on changed lines are not traced into the library")
    if log_calls:
        notes.append(f"{log_calls} third-party call(s) inside logging statements on changed lines are not analysed")
    return flags, risks


def _definition_site(repo: Path, rel: str, qn: str, line: int) -> tuple[str, int]:
    """Header declaration -> out-of-line definition in the same-stem source file, when there is one."""
    p = Path(rel)
    if p.suffix.lower() not in (".h", ".hh", ".hpp", ".hxx"):
        return rel, line
    parts = qn.split("::")
    needle = "::".join(parts[-2:]) + "(" if len(parts) >= 2 else parts[-1] + "("
    for ext in (".cc", ".cpp", ".cxx", ".c"):
        cand = p.with_suffix(ext)
        for base in (cand, Path(str(cand).replace("/include/", "/src/"))):
            f = repo / base
            if f.is_file():
                for i, text in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if needle in text.replace(" ", ""):
                        return base.as_posix(), i
    return rel, line


def _code_digest() -> str:
    """Analyzer source hash: a run cached by an older analyzer build is never served as a hit."""
    h = hashlib.sha256()
    for p in sorted(Path(__file__).parent.rglob("*.py")):
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _fallback_args(repo: Path) -> tuple[str, ...]:
    """Flags used to tokenise changed files when there is no compile database (graph-provider mode)."""
    inc = [repo, repo / "include", repo / "src"]
    return ("-x", "c++", "-std=c++17", *[f"-I{p}" for p in inc if p.is_dir()])


def ch_dict(ch, ref: SymbolRef) -> dict[str, Any]:
    return {"id": ch.node_id, "symbol": ref.to_dict(), "change_kind": ch.change_kind,
            "conditions": ch.conditions, "changed_lines": len(ch.added_lines) + len(ch.removed_lines)}


__all__ = ["Options", "run", "default_cache_dir", "Graph"]
