"""``tcadvisor`` CLI (contracts/cli-contract.md). Exit codes: 0 ok, 1 prerequisite, 2 usage, 3 internal."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path

from tcadvisor import __version__
from tcadvisor.models import PrerequisiteError, UsageError
from tcadvisor.config import AI_VERIFY, BUILD_SYSTEMS, FORMATS, GRAPHS, INDEX_MODES, LANGUAGES, resolve, resolve_sources


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # usage errors -> exit 2 (argparse default, made explicit)
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="tcadvisor", description="Change Impact & Test Case Advisor for C/C++ (CMake or autotools)")
    p.add_argument("--version", action="version", version=f"tcadvisor {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="analyse a change and write the test-case report")
    mode = a.add_mutually_exclusive_group(required=True)
    mode.add_argument("--commit-range", metavar="REV..REV")
    mode.add_argument("--working-tree", action="store_true", help="uncommitted (staged+unstaged+untracked) changes")
    mode.add_argument("--symbols", metavar="NAME[,NAME...]", help="explicit functions/methods/classes")
    mode.add_argument("--symbols-file", metavar="PATH", help="JSON list of symbols")
    a.add_argument("--repo", type=Path, default=Path("."), help="analysed git repository root (default: .)")
    a.add_argument("--build-dir", type=Path,
                   help="build dir with compile_commands.json (CMake: and .cmake/api/v1/reply) (default: build_dir in "
                        "<repo>/.tcadvisor/config.json, else <repo>/build)")
    a.add_argument("--build-system", choices=list(BUILD_SYSTEMS),
                   help="build model: cmake (File API), autotools (configure.ac + Makefile.am) or auto (default: "
                        "config build_system / build.system, else detected from the repository)")
    a.add_argument("--variants", metavar="NAME[,NAME...]",
                   help="use only these variants of the confirmed build profile for this run")
    a.add_argument("--no-variant-filter", dest="variant_filter", action="store_false", default=True,
                   help="ignore the build profile: nothing is moved to 'not built in the confirmed variants'")
    a.add_argument("--max-hop-depth", type=int, help="caller levels to follow (default: config, else 2)")
    a.add_argument("--split-threshold", type=int, help="changed symbols above which the run is split (default: config, else 50)")
    a.add_argument("--contracts", type=Path, help="third-party API contracts JSON (default: "
                   "<repo>/.tcadvisor/external-contracts.json when present)")
    a.add_argument("--lessons", type=Path, help="emitting points + team lessons JSON (default: "
                   "<repo>/.tcadvisor/lessons.json when present)")
    a.add_argument("--previous-report", type=Path, help="filled report.html of an earlier run: test results "
                   "and evidence are carried over by case key")
    a.add_argument("--flow-max-tus", type=int, help="max TUs parsed for data-path tracing (default: config, else 4)")
    a.add_argument("--no-patterns", dest="patterns", action="store_const", const=False, default=None,
                   help="no data paths, trigger sources or lesson patterns")
    a.add_argument("--attachment-warn-mb", type=int,
                   help="report warns when embedded evidence exceeds this size")
    a.add_argument("--cache-dir", type=Path)
    a.add_argument("--output-dir", type=Path, help="report root: every run writes a new folder <time>-<change> inside "
                   "it and updates <root>/latest (default: output_dir in <repo>/.tcadvisor/config.json, else "
                   "<repo>/.tcadvisor/reports)")
    a.add_argument("--exact-output-dir", action="store_true",
                   help="write straight into --output-dir, no run folder (scripts / benchmarks)")
    a.add_argument("--format", choices=list(FORMATS),
                   help="'both' = md+json (contract), 'all' = md+json+html (default)")
    a.add_argument("--targets", help="comma-separated build targets (CMake targets or autotools products) to restrict "
                   "the scope to (default: config)")
    a.add_argument("--include-tests", action=argparse.BooleanOptionalAction, default=None,
                   help="also analyse unit-test / mock code (changed tests, tests calling the change, re-run lists); "
                        "default: include_tests in <repo>/.tcadvisor/config.json, else off")
    a.add_argument("--ai-verify", choices=list(AI_VERIFY),
                   help="AI-verify the cases after the analysis: off, chat (the AI chat front-end does it) or claude "
                        "(this command runs the headless Claude Code CLI); default: ai_verify in the config, else off")
    llm = a.add_mutually_exclusive_group()
    llm.add_argument("--llm", dest="llm", action="store_true")
    llm.add_argument("--no-llm", dest="llm", action="store_false")
    a.set_defaults(llm=False)
    a.add_argument("--llm-endpoint", default="http://localhost:11434")
    a.add_argument("--llm-model", default="qwen2.5-coder:7b")
    a.add_argument("--llm-external-approved", action="store_true")
    a.add_argument("--graph", choices=list(GRAPHS),
                   help="impact source: codegraph (MIT, default), gitnexus (PolyForm-Noncommercial, opt-in) or clang "
                        "(built-in libclang graph); default from <repo>/.tcadvisor/config.json, else codegraph. The "
                        "chosen source is never replaced: if it is missing or fails, the run stops")
    a.add_argument("--language", choices=list(LANGUAGES),
                   help="report language: vi (default) or en; default from <repo>/.tcadvisor/config.json, else vi")
    a.add_argument("--graph-bin", help="path to the codegraph/gitnexus executable (default: config graph_bin, else PATH)")
    a.add_argument("--index", choices=list(INDEX_MODES),
                   help="libclang index of every TU (full) or include scan only (lite); auto = lite with a graph provider")
    a.add_argument("--no-history", dest="history", action="store_const", const=False, default=None,
                   help="do not use the files' bug-fix history (git log) as a ranking signal")
    a.add_argument("--target-patterns", type=Path, metavar="JSON",
                   help='extra regexes that mark a case "test on target", e.g. {"hardware access": "\\bmy_hal_\\w+"}')
    a.add_argument("--jobs", type=int, help="parallel libclang workers for the full index (default: CPU count)")
    a.add_argument("--allow-stale-compile-db", action="store_const", const=True, default=None)
    a.add_argument("--no-run-cache", action="store_true", help="always recompute the result (index cache still used)")
    a.add_argument("--print", choices=["summary", "brief", "json"], default="summary", help="what to print on stdout")
    a.add_argument("-q", "--quiet", action="store_true")

    c = sub.add_parser("cache", help="cache maintenance")
    csub = c.add_subparsers(dest="cache_cmd", required=True)
    cc = csub.add_parser("clear", help="delete the cached index for a repository")
    cc.add_argument("--repo", required=True, type=Path)
    cc.add_argument("--cache-dir", type=Path)

    v = sub.add_parser("verify-pack", help="write token-lean verification packets for AI verifiers")
    v.add_argument("report", type=Path, nargs="?",
                   help="report.json (default: report.json in the output dir of --repo, see `tcadvisor config`)")
    v.add_argument("--repo", type=Path, default=Path("."), help="repository whose report to pack (default: .)")
    v.add_argument("--out", type=Path, help="default: <report dir>/verify")
    v.add_argument("--priorities", help="default: config verify_priorities, else P1,P2,P3")
    v.add_argument("--max-cases", type=int, help="default: config verify_max_cases, else 120")
    v.add_argument("--batch", type=int, default=8, help="packets per verifier call")
    v.add_argument("--scope", choices=["all", "review"], default="all",
                   help="review = only cases that may be closed by reading code (cheapest way to shrink the "
                        "list of cases to test on the target); all = those first, then target cases")

    vf = sub.add_parser("verify", help="AI-verify an existing report with the Claude Code CLI (headless)")
    vf.add_argument("report", type=Path)
    vf.add_argument("--ai-external-approved", action="store_true",
                    help="confirm sending packed code windows to the model provider (required)")
    vf.add_argument("--repo", type=Path, help="repository whose config applies (default: the report's repository)")
    vf.add_argument("--claude-bin", help="default: config claude_bin, else claude")
    vf.add_argument("--verify-model", help="default: config verify_model, else haiku")
    vf.add_argument("--synth-model", help="default: config synth_model, else sonnet")
    vf.add_argument("--parallel", type=int, help="default: config verify_parallel, else 4")
    vf.add_argument("--priorities", help="default: config verify_priorities, else P1,P2,P3")
    vf.add_argument("--max-cases", type=int, help="default: config verify_max_cases, else 120")
    vf.add_argument("--scope", choices=["all", "review"], default="all",
                    help="review = only AI-review cases that may be closed by reading code")
    vf.add_argument("--budget-usd", type=float, help="per-call spending cap passed to claude --max-budget-usd "
                    "(default: config budget_usd, else none)")

    an = sub.add_parser("annotate", help="merge AI verdicts into report.json and re-render")
    an.add_argument("report", type=Path)
    an.add_argument("verdicts", type=Path)

    r = sub.add_parser("render", help="re-render md/html/brief from an existing report.json")
    r.add_argument("report", type=Path)
    r.add_argument("--output-dir", type=Path)
    r.add_argument("--language", choices=list(LANGUAGES), help="re-render in this language (default: the report's)")
    ini = sub.add_parser("init", help="set up a repository: write .tcadvisor/config.json and the AI front-ends (the "
                                      "tc-coverage skill for Claude Code and GitHub Copilot)")
    ini.add_argument("--repo", type=Path, default=Path("."))
    ini.add_argument("--ai", default="claude,copilot",
                     help="AI front-ends to install: claude (.claude/skills + .claude/agents), copilot (.github/skills "
                          "+ .github/prompts), both (default) or none")
    ini.add_argument("--copilot", action="store_true", help=argparse.SUPPRESS)  # before --ai: copilot is included
    ini.add_argument("--include-tests", action=argparse.BooleanOptionalAction, default=None,
                     help="analyse unit-test / mock code too (default: off)")
    ini.add_argument("--ai-verify", choices=list(AI_VERIFY),
                     help="AI filter after each analysis (default: chat when an AI front-end is installed, else off)")
    ini.add_argument("--force", action="store_true", help="overwrite existing files")
    ini.add_argument("--graph", choices=list(GRAPHS))
    ini.add_argument("--language", choices=list(LANGUAGES))
    ini.add_argument("--build-dir", help="build dir relative to the repository root")
    ini.add_argument("--output-dir", help="report root, relative to the repository root (default .tcadvisor/reports)")
    ini.add_argument("--targets", help="comma-separated build targets / products")
    ini.add_argument("--max-hop-depth", type=int)
    cd = sub.add_parser("compile-db", help="write compile_commands.json from a build log (Yocto log.do_compile or "
                                           "make V=1 output); the build itself is never run")
    cd.add_argument("--from-log", type=Path, required=True, metavar="LOG")
    cd.add_argument("--repo", type=Path, default=Path("."))
    cd.add_argument("--src", metavar="PATH", help="source dir of the build (Yocto ${S}) when it is not the workspace; "
                    "mapped onto --repo (default: detected from the log)")
    cd.add_argument("--map", action="append", default=[], metavar="OLD=NEW", help="extra path prefix mapping")
    cd.add_argument("--variant", help="record the result as this build-profile variant (name [A-Za-z0-9._-]+)")
    cd.add_argument("--out", type=Path, help="default: <repo>/.tcadvisor/build/<variant|default>/compile_commands.json")
    pf = sub.add_parser("profile", help="detect the build flow and its variants, confirm them and save the build "
                                        "profile used to leave out code that is not built")
    pf.add_argument("--repo", type=Path, default=Path("."))
    g = pf.add_mutually_exclusive_group()
    g.add_argument("--detect", action="store_true", help="print the detected proposal (with --json) and exit; no write")
    g.add_argument("--save", metavar="FILE|-", help="save a profile JSON ({system?, variants: [...]}), e.g. the "
                   "proposal of --detect --json after the user confirmed it")
    g.add_argument("--show", action="store_true", help="print the saved profile and its state")
    pf.add_argument("--json", action="store_true")
    cf = sub.add_parser("config", help="print every setting a run on the repository uses, with its source "
                                       "(flag aside): config file or built-in default")
    cf.add_argument("--repo", type=Path, default=Path("."))
    cf.add_argument("--json", action="store_true", help="effective values as JSON (for the AI front-ends)")
    rs = sub.add_parser("results", help="summarise the test results recorded in a filled report.html "
                                        "(exit 0 complete, 4 incomplete or any fail)")
    rs.add_argument("report", type=Path)
    rs.add_argument("--json", action="store_true")
    return p


def _analyze(ns: argparse.Namespace) -> int:
    from tcadvisor.ingest.symbols import parse_symbol_args
    from tcadvisor.llm.enrich import check_endpoint
    from tcadvisor.pipeline import Options, run
    from tcadvisor.report.render import summary_line, to_brief, write_outputs
    from tcadvisor.report.runs import change_label, latest_run, new_run_folder, update_latest

    cfg, src = resolve_sources(ns.repo, graph=ns.graph, language=ns.language, build_dir=ns.build_dir, output_dir=ns.output_dir,
                  targets=ns.targets, max_hop_depth=ns.max_hop_depth, include_tests=ns.include_tests,
                  ai_verify=ns.ai_verify, build_system=ns.build_system, graph_bin=ns.graph_bin,
                  contracts=ns.contracts, lessons=ns.lessons, target_patterns=ns.target_patterns, index=ns.index,
                  jobs=ns.jobs, patterns=ns.patterns, history=ns.history, flow_max_tus=ns.flow_max_tus,
                  split_threshold=ns.split_threshold, attachment_warn_mb=ns.attachment_warn_mb,
                  cache_dir=ns.cache_dir, allow_stale_compile_db=ns.allow_stale_compile_db, format=ns.format)
    if src["build_dir"] == "default":  # a compile database recorded by `tcadvisor compile-db` / the build profile
        from tcadvisor.config import variant_compile_db
        names = [v.strip() for v in ns.variants.split(",")] if ns.variants else None
        found = variant_compile_db(ns.repo, cfg, names)
        if found is not None:
            cfg["build_dir"] = found
    if cfg["max_hop_depth"] < 1 or cfg["split_threshold"] < 1:
        raise UsageError("--max-hop-depth and --split-threshold must be >= 1")
    if cfg["target_patterns"]:
        from tcadvisor.classify.environment import load_patterns
        load_patterns(cfg["target_patterns"])  # usage error before any indexing
    if ns.llm:
        check_endpoint(ns.llm_endpoint, ns.llm_external_approved)
    symbols = parse_symbol_args(ns.symbols, ns.symbols_file) if (ns.symbols or ns.symbols_file) else None
    say = (lambda m: None) if ns.quiet else (lambda m: print(f"[tcadvisor] {m}", file=sys.stderr))
    repo = ns.repo.resolve()
    root: Path = cfg["output_dir"]
    _exclude_report_root(repo, root)  # before the analysis: a working-tree diff must not see earlier reports
    previous, notes = ns.previous_report, []
    if previous is None and not ns.exact_output_dir:
        previous = _filled_report(latest_run(root))
        if previous is not None:
            notes.append(f"test results carried over from the latest run {previous.parent.name} (by case key); "
                         "pass --previous-report to choose another filled report")
    from tcadvisor.classify.variants import profile_for_run
    profile, profile_notes = profile_for_run(repo, cfg, ns.variants, ns.variant_filter, interactive=_interactive(ns))
    notes.extend(profile_notes)
    opts = Options(
        repo=ns.repo, build_dir=cfg["build_dir"], commit_range=ns.commit_range, working_tree=ns.working_tree,
        symbols=symbols, max_hop_depth=cfg["max_hop_depth"], split_threshold=cfg["split_threshold"],
        cache_dir=cfg["cache_dir"], output_dir=root,
        targets=[t.strip() for t in cfg["targets"].split(",") if t.strip()] if cfg["targets"] else None,
        llm=ns.llm, llm_endpoint=ns.llm_endpoint, llm_model=ns.llm_model, allow_stale=cfg["allow_stale_compile_db"],
        use_run_cache=not ns.no_run_cache, progress=say, graph=cfg["graph"], language=cfg["language"],
        graph_bin=cfg["graph_bin"], index=cfg["index"], jobs=cfg["jobs"], history=cfg["history"],
        contracts=cfg["contracts"], lessons=cfg["lessons"], previous_report=previous,
        flow_max_tus=cfg["flow_max_tus"], patterns=cfg["patterns"], attachment_warn_mb=cfg["attachment_warn_mb"],
        target_patterns=cfg["target_patterns"], include_tests=cfg["include_tests"], test_paths=cfg["test_paths"],
        build_system=cfg["build_system"], profile=profile)
    report = run(opts)
    report.setdefault("run_notes", []).extend(notes)
    if ns.exact_output_dir:
        out = root
    else:
        ci_ = report.get("change_input") or {}
        out = new_run_folder(root, change_label(ci_.get("commit_range"), bool(ci_.get("working_tree")),
                                                *_revs(report)))
        from datetime import datetime, timezone
        report["run"] = {"name": out.name, "path": str(out), "created_at": datetime.now(timezone.utc).isoformat(),
                         "change": ci_.get("commit_range") or ("working-tree" if ci_.get("working_tree") else "symbols")}
    files = write_outputs(report, out, cfg["format"])
    if not ns.exact_output_dir:
        update_latest(root, out)
    if cfg["ai_verify"] == "claude" and report["test_case_candidates"]:
        report = _ai_verify(out / "report.json", say, cfg)
    if ns.print == "json":
        print(json.dumps(report, indent=2))
        return 0
    if ns.print == "brief":
        print(to_brief(report), end="")
        print(f"REPORT {out}")  # where report.html / report.json are (for AI chat front-ends)
        if cfg["ai_verify"] == "chat" and report["test_case_candidates"] and not report.get("ai_verification"):
            # read by the tc-coverage skill / Copilot prompt: verify before answering (config ai_verify: chat)
            print("AI-VERIFY required: run verify-pack, verify every batch, then annotate (ai_verify is 'chat')")
    else:
        print(summary_line(report))
        for f in files:
            print(f"  wrote {f}")
    print(f"report: {out}")
    return 0


def _revs(report: dict) -> tuple[str | None, str | None]:
    ci_ = report.get("change_input") or {}
    rng = ci_.get("commit_range")
    if not rng:
        return None, None
    old, new = ci_.get("old_rev"), ci_.get("new_rev") or report.get("commit_hash")
    return old, new


def _interactive(ns: argparse.Namespace) -> bool:
    return ns.print != "json" and sys.stdin.isatty() and sys.stdout.isatty()


def _exclude_report_root(repo: Path, root: Path) -> None:
    """Report root inside the analysed repository: keep it out of git status / working-tree diffs (info/exclude)."""
    from tcadvisor.ingest.git import git_exclude
    try:
        rel = root.resolve().relative_to(repo)
    except ValueError:
        return
    if str(rel) not in ("", "."):
        git_exclude(repo, rel.as_posix().rstrip("/") + "/")


def _filled_report(run_dir: Path | None) -> Path | None:
    """`report.html` of a run that holds tester results (the default --previous-report)."""
    if run_dir is None or not (run_dir / "report.html").is_file():
        return None
    from tcadvisor.report.results import read_results
    try:
        block = read_results(run_dir / "report.html")
    except Exception:  # noqa: BLE001 - an older report without a results block
        return None
    return run_dir / "report.html" if block and (block.get("results") or block.get("orphaned_results")) else None


def _ai_settings(cfg: dict) -> dict:
    return {"claude": cfg["claude_bin"], "verify_model": cfg["verify_model"], "synth_model": cfg["synth_model"],
            "parallel": cfg["verify_parallel"], "priorities": set(cfg["verify_priorities"].split(",")),
            "max_cases": cfg["verify_max_cases"], "budget_usd": cfg["budget_usd"]}


def _ai_verify(report_path: Path, say, cfg: dict) -> dict:
    """config ai_verify = claude: AI-verify right after the analysis (the setting is the approval)."""
    from tcadvisor.report.render import write_outputs
    from tcadvisor.verify.runner import verify
    try:
        res = verify(report_path, approved=True, progress=say, **_ai_settings(cfg))
    except UsageError as exc:  # e.g. no `claude` on PATH: the analysis stands, unfiltered
        print(f"warning: AI verification skipped: {exc}", file=sys.stderr)
        return json.loads(report_path.read_text(encoding="utf-8"))
    if res["errors"]:
        print("warning: AI verification: " + "; ".join(res["errors"]), file=sys.stderr)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    write_outputs(report, report_path.parent, "all", same_analysis=True)
    return report


def _compile_db(ns: argparse.Namespace) -> int:
    from tcadvisor.config import _VARIANT_NAME, update_file
    from tcadvisor.index.build_log import log_sha256, write_compile_db
    from tcadvisor.ingest.git import git_exclude
    repo = ns.repo.resolve()
    if not (repo / ".git").exists():
        raise UsageError(f"--repo '{repo}' is not a git repository root")
    if ns.variant and not _VARIANT_NAME.match(ns.variant):
        raise UsageError("--variant must match [A-Za-z0-9._-]+")
    maps = {}
    for m in ns.map:
        old, sep, new = m.partition("=")
        if not sep or not old or not new:
            raise UsageError(f"--map expects OLD=NEW, not {m!r}")
        maps[old.rstrip("/")] = new
    out = (ns.out or repo / ".tcadvisor" / "build" / (ns.variant or "default") / "compile_commands.json").resolve()
    git_exclude(repo, ".tcadvisor/build/")
    res = write_compile_db(ns.from_log, repo, out, ns.src, maps)
    print(f"wrote {out}: {len(res.entries)} compile command(s)")
    for old, new in res.prefix_map.items():
        print(f"  path map {old} -> {new}")
    if res.unmapped:
        print(f"warning: {len(res.unmapped)} source(s) not found in the workspace (pass --src / --map): "
              + ", ".join(res.unmapped[:5]), file=sys.stderr)
    if ns.variant:
        rel = out.relative_to(repo).as_posix() if out.is_relative_to(repo) else str(out)
        log = ns.from_log.resolve()
        bdir = next((str(d) for e in res.entries for d in (Path(e["directory"]), *Path(e["directory"]).parents)
                     if (d / "config.status").is_file()), None)  # configure's output: switch values (profile)

        def record(data: dict) -> None:
            prof = data.get("build") or {"system": "autotools", "confirmed": False, "variants": []}
            entry = next((v for v in prof["variants"] if v["name"] == ns.variant), None)
            if entry is None:
                entry = {"name": ns.variant}
                prof["variants"].append(entry)
            entry.update({"compile_db": rel, "build_log": str(log), "log_sha256": log_sha256(log)})
            if bdir:
                entry["build_dir"] = bdir
            data["build"] = prof
        update_file(repo, record)
        print(f"recorded as build-profile variant '{ns.variant}' (confirm the profile with `tcadvisor profile`)")
    return 0


def _profile(ns: argparse.Namespace) -> int:
    from tcadvisor.config import load_config
    from tcadvisor.index.variants import confirm_interactively, detect, profile_state, save_profile
    repo = ns.repo.resolve()
    if not (repo / ".git").exists():
        raise UsageError(f"--repo '{repo}' is not a git repository root")
    cfg = load_config(repo)
    if ns.detect:
        p = detect(repo, cfg)
        if ns.json:
            print(json.dumps(p, indent=2, ensure_ascii=False))
        else:
            print(f"build system: {p['system']}; switches: {', '.join(s['name'] for s in p['switches']) or 'none'}")
            for v in p["variants"]:
                print(f"variant {v['name']}: " + ", ".join(f"{k}={x}" for k, x in sorted(v["values"].items())
                                                          if x is not None) + (f"; unset: {', '.join(p['unset'][v['name']])}"
                                                                               if p["unset"].get(v["name"]) else ""))
        return 0
    if ns.save:
        text = sys.stdin.read() if ns.save == "-" else Path(ns.save).read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise UsageError(f"--save: not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise UsageError("--save: expected an object {system?, variants: [...]}")
        if "fingerprint" not in data:
            data["fingerprint"] = detect(repo, cfg).get("fingerprint")
        prof = save_profile(repo, data, cfg)
        print(f"saved build profile: {', '.join(v['name'] for v in prof['variants'])}")
        return 0
    if ns.show:
        prof = cfg.get("build")
        state = profile_state(repo, prof)
        if ns.json:
            print(json.dumps({"state": state, "profile": prof}, indent=2, ensure_ascii=False))
        else:
            print(f"build profile: {state}")
            for v in (prof or {}).get("variants", []):
                print(f"  {v['name']}: " + ", ".join(f"{k}={x}" for k, x in sorted((v.get("values") or {}).items())))
        return 0
    if not sys.stdin.isatty():
        raise UsageError("tcadvisor profile needs a terminal; use --detect --json and --save FILE|- instead")
    return 0 if confirm_interactively(repo, cfg) is not None else 1


def _report_repo(report: Path, repo: Path | None) -> Path:
    """The repository whose config applies to an existing report (its recorded root when it still exists)."""
    if repo is not None:
        return repo
    try:
        rec = json.loads(report.read_text(encoding="utf-8")).get("change_input", {}).get("target_repo_path")
    except (OSError, ValueError):
        rec = None
    return Path(rec) if rec and (Path(rec) / ".git").exists() else Path(".")


def _results(ns: argparse.Namespace) -> int:
    from tcadvisor.report.results import VERDICT_LABEL, read_cases, read_results, summary, validate_record
    block = read_results(ns.report)
    cases = read_cases(ns.report)
    s = summary(block, [c["key"] for c in cases])
    open_items = []
    for c in cases:
        rec = block["results"].get(c["key"]) or {}
        why = validate_record(rec, block["attachments"])
        if rec.get("verdict") is None:
            why = ["not tested"]
        elif rec.get("needs_recheck"):
            why = ["needs re-check"] + why
        elif rec.get("verdict") == "fail":
            why = ["failed"] + why
        if why:
            open_items.append({"id": c["id"], "key": c["key"], "verdict": rec.get("verdict"),
                               "description": c["description"], "issues": why})
    if ns.json:
        print(json.dumps({"summary": s, "open": open_items}, indent=2))
    else:
        recheck = f" / {s['needs_recheck']} re-check" if s["needs_recheck"] else ""
        print(f"test results: {s['pass']} pass / {s['fail']} fail / {s['not_testable']} n/t / "
              f"{s['cannot_occur']} n/o / {s['untested']} untested{recheck}; {s['invalid']} incomplete record(s); "
              f"{s['attachment_bytes']} bytes of evidence; {'COMPLETE' if s['complete'] else 'INCOMPLETE'}")
        for o in open_items:
            print(f"{o['id']} [{VERDICT_LABEL.get(o['verdict'], '—')}] {o['description']} :: {'; '.join(o['issues'])}")
    return 0 if s["complete"] and s["fail"] == 0 else 4


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    try:
        if ns.command == "analyze":
            return _analyze(ns)
        if ns.command == "cache":
            from tcadvisor.pipeline import default_cache_dir
            d = ns.cache_dir or default_cache_dir(ns.repo)
            if d.exists():
                shutil.rmtree(d)
                print(f"cleared {d}")
            else:
                print(f"no cache at {d}")
            return 0
        if ns.command == "verify-pack":
            from tcadvisor.verify.pack import write_packets
            from tcadvisor.report.runs import report_file
            vcfg = resolve(ns.repo)
            report = ns.report or report_file(vcfg["output_dir"])
            if not report.is_file():
                raise UsageError(f"no report at {report}: run `tcadvisor analyze` first")
            m = write_packets(report, ns.out or report.parent / "verify",
                              {p.strip() for p in (ns.priorities or vcfg["verify_priorities"]).split(",")},
                              ns.max_cases or vcfg["verify_max_cases"], ns.batch, ns.scope)
            print(json.dumps(m, indent=1))
            return 0
        if ns.command == "verify":
            from tcadvisor.report.render import plan_line, write_outputs
            from tcadvisor.verify.runner import verify
            vcfg = resolve(_report_repo(ns.report, ns.repo), claude_bin=ns.claude_bin, verify_model=ns.verify_model,
                           synth_model=ns.synth_model, verify_parallel=ns.parallel,
                           verify_priorities=ns.priorities, verify_max_cases=ns.max_cases, budget_usd=ns.budget_usd)
            vcfg["verify_priorities"] = ",".join(p.strip() for p in vcfg["verify_priorities"].split(",") if p.strip())
            res = verify(ns.report, approved=ns.ai_external_approved, scope=ns.scope,
                         progress=lambda m: print(f"[tcadvisor] {m}", file=sys.stderr), **_ai_settings(vcfg))
            write_outputs(json.loads(ns.report.read_text(encoding="utf-8")), ns.report.parent, "all",
                          same_analysis=True)
            u = res["usage"]
            if res["errors"] and not res["verified"]:
                print("error: AI verification failed: " + "; ".join(res["errors"]), file=sys.stderr)
                return 3
            rep = json.loads(ns.report.read_text(encoding="utf-8"))
            print(plan_line(rep))
            print(f"verified {res['verified']} case(s) with {u['calls']} model call(s); tokens in/out "
                  f"{u['input_tokens']}/{u['output_tokens']}; cost ${u['cost_usd']:.4f}"
                  + (f"; errors: {'; '.join(res['errors'])}" if res["errors"] else ""))
            return 0
        if ns.command == "annotate":
            from tcadvisor.report.render import write_outputs
            from tcadvisor.verify.annotate import annotate_file
            for w in annotate_file(ns.report, ns.verdicts):
                print(f"warning: {w}", file=sys.stderr)
            rep = json.loads(ns.report.read_text(encoding="utf-8"))
            write_outputs(rep, ns.report.parent, "all", same_analysis=True)
            av = rep["ai_verification"]
            print(f"annotated {av['verified_cases']} case(s); {len(av['additional_checks'])} additional check(s)")
            from tcadvisor.report.render import plan_line
            print(plan_line(rep))
            return 0
        if ns.command == "results":
            return _results(ns)
        if ns.command == "compile-db":
            return _compile_db(ns)
        if ns.command == "profile":
            return _profile(ns)
        if ns.command == "config":
            from tcadvisor.config import effective, effective_table
            if ns.json:
                print(json.dumps(effective(ns.repo), indent=2, ensure_ascii=False))
                return 0
            rows = effective_table(ns.repo)
            w = max(len(k) for k, _, _ in rows)
            for k, v, src in rows:
                print(f"{k:<{w}}  {json.dumps(v, ensure_ascii=False):<40}  {src}")
            return 0
        if ns.command == "init":
            from tcadvisor.integrations.init import AIS, init, next_steps
            ais = tuple(a.strip() for a in ns.ai.split(",") if a.strip() and a.strip() != "none")
            if ns.ai.strip() in ("all", "both"):
                ais = AIS
            if any(a not in AIS for a in ais):
                raise UsageError(f"--ai: choose from {', '.join(AIS)} or none, not {ns.ai!r}")
            for path, status in init(ns.repo, {"graph": ns.graph, "language": ns.language, "build_dir": ns.build_dir,
                                               "output_dir": ns.output_dir, "targets": ns.targets,
                                               "max_hop_depth": ns.max_hop_depth, "include_tests": ns.include_tests,
                                               "ai_verify": ns.ai_verify}, ais, ns.force):
                print(f"{status}: {path}")
            from tcadvisor.config import load_config
            for step in next_steps(load_config(ns.repo.resolve())):
                print(f"next: {step}")
            return 0
        if ns.command == "render":
            from tcadvisor.report.render import write_outputs
            rep = json.loads(ns.report.read_text(encoding="utf-8"))
            if ns.language:
                rep["report_language"] = ns.language
            for f in write_outputs(rep, ns.output_dir or ns.report.parent, "all", same_analysis=True):
                print(f"wrote {f}")
            return 0
    except PrerequisiteError as exc:
        print(f"error: prerequisite failure: {exc}", file=sys.stderr)
        return 1
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - contract: internal errors are logged, exit 3
        traceback.print_exc()
        return 3
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
