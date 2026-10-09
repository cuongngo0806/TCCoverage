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


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # usage errors -> exit 2 (argparse default, made explicit)
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="tcadvisor", description="Change Impact & Test Case Advisor for C++/CMake")
    p.add_argument("--version", action="version", version=f"tcadvisor {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="analyse a change and write the test-case report")
    mode = a.add_mutually_exclusive_group(required=True)
    mode.add_argument("--commit-range", metavar="REV..REV")
    mode.add_argument("--working-tree", action="store_true", help="uncommitted (staged+unstaged+untracked) changes")
    mode.add_argument("--symbols", metavar="NAME[,NAME...]", help="explicit functions/methods/classes")
    mode.add_argument("--symbols-file", metavar="PATH", help="JSON list of symbols")
    a.add_argument("--repo", required=True, type=Path)
    a.add_argument("--build-dir", required=True, type=Path,
                   help="CMake build dir with compile_commands.json and .cmake/api/v1/reply")
    a.add_argument("--max-hop-depth", type=int, default=2)
    a.add_argument("--split-threshold", type=int, default=50)
    a.add_argument("--cache-dir", type=Path)
    a.add_argument("--output-dir", type=Path, default=Path("tcadvisor-report"))
    a.add_argument("--format", choices=["md", "json", "html", "both", "all"], default="all",
                   help="'both' = md+json (contract), 'all' = md+json+html (default)")
    a.add_argument("--targets", help="comma-separated CMake targets to restrict the scope to (pilot scope)")
    llm = a.add_mutually_exclusive_group()
    llm.add_argument("--llm", dest="llm", action="store_true")
    llm.add_argument("--no-llm", dest="llm", action="store_false")
    a.set_defaults(llm=False)
    a.add_argument("--llm-endpoint", default="http://localhost:11434")
    a.add_argument("--llm-model", default="qwen2.5-coder:7b")
    a.add_argument("--llm-external-approved", action="store_true")
    a.add_argument("--graph", choices=["auto", "codegraph", "gitnexus", "clang"], default="clang",
                   help="impact source: codegraph (MIT), gitnexus (PolyForm-Noncommercial, opt-in), clang (built-in "
                        "libclang graph); auto = codegraph if installed else clang")
    a.add_argument("--graph-bin", help="path to the codegraph/gitnexus executable")
    a.add_argument("--index", choices=["auto", "full", "lite"], default="auto",
                   help="libclang index of every TU (full) or include scan only (lite); auto = lite with a graph provider")
    a.add_argument("--fallback-max-tus", type=int, default=200,
                   help="max TUs to parse with libclang when the graph provider cannot resolve a root (else flag)")
    a.add_argument("--no-history", dest="history", action="store_false",
                   help="do not use the files' bug-fix history (git log) as a ranking signal")
    a.add_argument("--jobs", type=int, help="parallel libclang workers for the full index (default: CPU count)")
    a.add_argument("--allow-stale-compile-db", action="store_true")
    a.add_argument("--no-run-cache", action="store_true", help="always recompute the result (index cache still used)")
    a.add_argument("--print", choices=["summary", "brief", "json"], default="summary", help="what to print on stdout")
    a.add_argument("-q", "--quiet", action="store_true")

    c = sub.add_parser("cache", help="cache maintenance")
    csub = c.add_subparsers(dest="cache_cmd", required=True)
    cc = csub.add_parser("clear", help="delete the cached index for a repository")
    cc.add_argument("--repo", required=True, type=Path)
    cc.add_argument("--cache-dir", type=Path)

    v = sub.add_parser("verify-pack", help="write token-lean verification packets for AI verifiers")
    v.add_argument("report", type=Path)
    v.add_argument("--out", type=Path, help="default: <report dir>/verify")
    v.add_argument("--priorities", default="P1,P2")
    v.add_argument("--max-cases", type=int, default=60)
    v.add_argument("--batch", type=int, default=8, help="packets per verifier call")

    vf = sub.add_parser("verify", help="AI-verify an existing report with the Claude Code CLI (headless)")
    vf.add_argument("report", type=Path)
    vf.add_argument("--ai-external-approved", action="store_true",
                    help="confirm sending packed code windows to the model provider (required)")
    vf.add_argument("--claude-bin")
    vf.add_argument("--verify-model", default="haiku")
    vf.add_argument("--synth-model", default="sonnet")
    vf.add_argument("--parallel", type=int, default=4)
    vf.add_argument("--priorities", default="P1,P2")
    vf.add_argument("--max-cases", type=int, default=60)
    vf.add_argument("--budget-usd", type=float, help="per-call spending cap passed to claude --max-budget-usd")

    an = sub.add_parser("annotate", help="merge AI verdicts into report.json and re-render")
    an.add_argument("report", type=Path)
    an.add_argument("verdicts", type=Path)

    r = sub.add_parser("render", help="re-render md/html/brief from an existing report.json")
    r.add_argument("report", type=Path)
    r.add_argument("--output-dir", type=Path)
    return p


def _analyze(ns: argparse.Namespace) -> int:
    from tcadvisor.ingest.symbols import parse_symbol_args
    from tcadvisor.llm.enrich import check_endpoint
    from tcadvisor.pipeline import Options, run
    from tcadvisor.report.render import summary_line, to_brief, write_outputs

    if ns.max_hop_depth < 1 or ns.split_threshold < 1:
        raise UsageError("--max-hop-depth and --split-threshold must be >= 1")
    if ns.llm:
        check_endpoint(ns.llm_endpoint, ns.llm_external_approved)
    symbols = parse_symbol_args(ns.symbols, ns.symbols_file) if (ns.symbols or ns.symbols_file) else None
    say = (lambda m: None) if ns.quiet else (lambda m: print(f"[tcadvisor] {m}", file=sys.stderr))
    opts = Options(
        repo=ns.repo, build_dir=ns.build_dir, commit_range=ns.commit_range, working_tree=ns.working_tree,
        symbols=symbols, max_hop_depth=ns.max_hop_depth, split_threshold=ns.split_threshold, cache_dir=ns.cache_dir,
        output_dir=ns.output_dir, targets=[t.strip() for t in ns.targets.split(",")] if ns.targets else None,
        llm=ns.llm, llm_endpoint=ns.llm_endpoint, llm_model=ns.llm_model, allow_stale=ns.allow_stale_compile_db,
        use_run_cache=not ns.no_run_cache, progress=say, graph=ns.graph, graph_bin=ns.graph_bin,
        index=ns.index, jobs=ns.jobs, fallback_max_tus=ns.fallback_max_tus, history=ns.history)
    report = run(opts)
    files = write_outputs(report, ns.output_dir, ns.format)
    if ns.print == "json":
        print(json.dumps(report, indent=2))
    elif ns.print == "brief":
        print(to_brief(report), end="")
    else:
        print(summary_line(report))
        for f in files:
            print(f"  wrote {f}")
    return 0


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
            m = write_packets(ns.report, ns.out or ns.report.parent / "verify",
                              {p.strip() for p in ns.priorities.split(",")}, ns.max_cases, ns.batch)
            print(json.dumps(m, indent=1))
            return 0
        if ns.command == "verify":
            from tcadvisor.report.render import write_outputs
            from tcadvisor.verify.runner import verify
            res = verify(ns.report, approved=ns.ai_external_approved, claude=ns.claude_bin,
                         verify_model=ns.verify_model, synth_model=ns.synth_model, parallel=ns.parallel,
                         priorities={p.strip() for p in ns.priorities.split(",")}, max_cases=ns.max_cases,
                         budget_usd=ns.budget_usd, progress=lambda m: print(f"[tcadvisor] {m}", file=sys.stderr))
            write_outputs(json.loads(ns.report.read_text(encoding="utf-8")), ns.report.parent, "all")
            u = res["usage"]
            if res["errors"] and not res["verified"]:
                print("error: AI verification failed: " + "; ".join(res["errors"]), file=sys.stderr)
                return 3
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
            write_outputs(rep, ns.report.parent, "all")
            av = rep["ai_verification"]
            print(f"annotated {av['verified_cases']} case(s); {len(av['additional_checks'])} additional check(s)")
            return 0
        if ns.command == "render":
            from tcadvisor.report.render import write_outputs
            rep = json.loads(ns.report.read_text(encoding="utf-8"))
            for f in write_outputs(rep, ns.output_dir or ns.report.parent, "all"):
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
