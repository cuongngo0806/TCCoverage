#!/usr/bin/env python3
"""Cross-platform (Linux/macOS/Windows) equivalent of the speckit PowerShell helper scripts, used by the
Claude Code skills in .claude/skills/speckit-*. Prints the same JSON keys as the .ps1 scripts.

  python3 .specify/scripts/python/speckit.py check-prerequisites --json [--require-spec] [--require-tasks]
                                             [--include-tasks] [--paths-only] [--template NAME]
  python3 .specify/scripts/python/speckit.py setup-plan --json
  python3 .specify/scripts/python/speckit.py setup-tasks --json
  python3 .specify/scripts/python/speckit.py resolve-template NAME --json
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def branch() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                              text=True).stdout.strip()
    except OSError:
        return ""


def feature_dir() -> Path:
    if os.environ.get("SPECIFY_FEATURE"):
        return ROOT / "specs" / os.environ["SPECIFY_FEATURE"]
    fj = ROOT / ".specify" / "feature.json"
    if fj.is_file():
        d = json.loads(fj.read_text()).get("feature_directory")
        if d:
            return (ROOT / d) if not os.path.isabs(d) else Path(d)
    specs = sorted(p for p in (ROOT / "specs").glob("*") if p.is_dir())
    b = branch()
    m = re.match(r"^(\d{3})-", b.split("/")[-1])
    if m:
        for p in specs:
            if p.name.startswith(m.group(1) + "-"):
                return p
    if not specs:
        sys.exit("ERROR: no feature directory under specs/ (run /speckit-specify first)")
    return specs[-1]


def template(name: str) -> Path | None:
    for base in (ROOT / ".specify" / "templates" / "overrides", ROOT / ".specify" / "templates"):
        p = base / f"{name}.md"
        if p.is_file():
            return p
    return None


def paths() -> dict:
    fd = feature_dir()
    return {"REPO_ROOT": str(ROOT), "BRANCH": branch(), "FEATURE_DIR": str(fd), "FEATURE_SPEC": str(fd / "spec.md"),
            "IMPL_PLAN": str(fd / "plan.md"), "TASKS": str(fd / "tasks.md")}


def docs(fd: Path, include_tasks: bool) -> list:
    out = [n for n in ("research.md", "data-model.md", "quickstart.md") if (fd / n).is_file()]
    if (fd / "contracts").is_dir() and any((fd / "contracts").iterdir()):
        out.append("contracts/")
    if include_tasks and (fd / "tasks.md").is_file():
        out.append("tasks.md")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("name", nargs="?")
    for f in ("--json", "--require-spec", "--require-tasks", "--include-tasks", "--paths-only"):
        ap.add_argument(f, action="store_true")
    ap.add_argument("--template")
    a = ap.parse_args()
    p = paths()
    fd = Path(p["FEATURE_DIR"])
    if a.cmd == "check-prerequisites":
        if a.paths_only:
            print(json.dumps(p))
            return
        if not fd.is_dir():
            sys.exit(f"ERROR: feature directory not found: {fd}")
        if a.require_spec and not (fd / "spec.md").is_file():
            sys.exit("ERROR: spec.md not found; run /speckit-specify first")
        if not (fd / "plan.md").is_file():
            sys.exit("ERROR: plan.md not found; run /speckit-plan first")
        if a.require_tasks and not (fd / "tasks.md").is_file():
            sys.exit("ERROR: tasks.md not found; run /speckit-tasks first")
        res = {"FEATURE_DIR": str(fd), "AVAILABLE_DOCS": docs(fd, a.include_tasks)}
        if a.template:
            t = template(a.template)
            res["TEMPLATE"] = str(t) if t else None
            res["TEMPLATE_CONTENT"] = t.read_text() if t else None
        print(json.dumps(res))
    elif a.cmd == "setup-plan":
        fd.mkdir(parents=True, exist_ok=True)
        plan = fd / "plan.md"
        if not plan.exists() and template("plan-template"):
            shutil.copy(template("plan-template"), plan)
        print(json.dumps({k: p[k] for k in ("FEATURE_SPEC", "IMPL_PLAN", "FEATURE_DIR", "BRANCH")}))
    elif a.cmd == "setup-tasks":
        t = template("tasks-template")
        print(json.dumps({"FEATURE_DIR": str(fd), "AVAILABLE_DOCS": docs(fd, False),
                          "TASKS_TEMPLATE": str(t) if t else None,
                          "TASKS_TEMPLATE_CONTENT": t.read_text() if t else None}))
    elif a.cmd == "resolve-template":
        t = template(a.name or "")
        if not t:
            sys.exit(f"ERROR: template {a.name} not found")
        print(json.dumps({"TEMPLATE_NAME": a.name, "TEMPLATE": str(t), "TEMPLATE_CONTENT": t.read_text()}))
    else:
        sys.exit(f"unknown command {a.cmd}")


if __name__ == "__main__":
    main()
