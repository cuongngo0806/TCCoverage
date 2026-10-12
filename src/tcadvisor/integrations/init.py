"""`tcadvisor init`: set up a repository for the tool (explicit, user-invoked; never touches application code).

Writes `<repo>/.tcadvisor/config.json` (the settings shared by the CLI and the AI chat front-ends) and the AI
front-ends themselves, so one command makes `/tc-coverage` work in the repository:

* `claude`  — Claude Code: the `tc-coverage` skill in `.claude/skills/` and its subagents in `.claude/agents/`;
* `copilot` — GitHub Copilot (agent mode): the same skill in `.github/skills/` and the `/tc-coverage`,
  `/tc-verify` prompt files in `.github/prompts/`.

The skill is one file for every assistant (`integrations/skills/tc-coverage/SKILL.md`). Existing files are kept
unless `--force`; an existing config keeps its values and only gains the keys it lacks (spec 012: the config lists
every supported key with its default, and `python` = the interpreter that ran `init`). The report root
`.tcadvisor/reports/` and generated compile databases `.tcadvisor/build/` go to `.git/info/exclude`.
"""
from __future__ import annotations

import json
import shutil
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from tcadvisor.config import DEFAULTS, config_path, load_config, read_file

AIS = ("claude", "copilot")
COPILOT_PROMPTS = ("tc-coverage.prompt.md", "tc-verify.prompt.md")
CLAUDE_AGENTS = ("tc-case-verifier.md", "tc-coverage-analyst.md", "tc-verify-synthesizer.md")
SKILL = "tc-coverage"


def _write(path: Path, text: str, force: bool) -> str:
    if path.exists() and not force:
        return "kept (exists; --force to overwrite)"
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    path.write_text(text, encoding="utf-8")
    return "overwritten" if existed else "created"


def files_for(ai: str) -> list[tuple[str, str]]:
    """(path relative to the repository, packaged source text) of one AI front-end."""
    pkg = resources.files("tcadvisor.integrations")
    skill = pkg.joinpath(f"skills/{SKILL}/SKILL.md").read_text(encoding="utf-8")
    if ai == "claude":
        return [(f".claude/skills/{SKILL}/SKILL.md", skill)] + [
            (f".claude/agents/{n}", pkg.joinpath(f"claude/agents/{n}").read_text(encoding="utf-8"))
            for n in CLAUDE_AGENTS]
    return [(f".github/skills/{SKILL}/SKILL.md", skill)] + [
        (f".github/prompts/{n}", pkg.joinpath(f"copilot/{n}").read_text(encoding="utf-8")) for n in COPILOT_PROMPTS]


def init(repo: Path, settings: dict[str, Any], ais: tuple[str, ...] = AIS, force: bool = False
         ) -> list[tuple[Path, str]]:
    repo = repo.resolve()
    if not (repo / ".git").exists():
        from tcadvisor.models import UsageError
        raise UsageError(f"--repo '{repo}' is not a git repository root")
    given = {k: v for k, v in settings.items() if v is not None}
    cfg = {**DEFAULTS, "ai_verify": "chat" if ais else "off", "python": sys.executable, **given}
    path = config_path(repo)
    if path.is_file() and not force:
        existing = read_file(repo)  # validates; its values win, missing keys are added
        merged = {**cfg, **existing}
        status = "kept (exists; --force to overwrite)" if merged == existing else "updated (missing keys added)"
        if merged != existing:
            path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        out = [(path, status)]
    else:
        out = [(path, _write(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", True))]
    load_config(repo)  # validate what is on disk now
    from tcadvisor.ingest.git import git_exclude
    for entry in (".tcadvisor/reports/", ".tcadvisor/build/"):
        git_exclude(repo, entry)
    for ai in ais:
        for rel, text in files_for(ai):
            out.append((repo / rel, _write(repo / rel, text, force)))
    return out


def next_steps(cfg: dict[str, Any]) -> list[str]:
    """What is still missing for a first run (printed after `tcadvisor init`)."""
    steps = []
    if cfg.get("graph", "codegraph") == "codegraph" and not shutil.which("codegraph"):
        steps.append("install the impact source: npm i -g @colbymchenry/codegraph")
    steps.append("optional, better accuracy: configure the build with -DCMAKE_EXPORT_COMPILE_COMMANDS=ON and an empty "
                 "<build>/.cmake/api/v1/query/codemodel-v2 file")
    steps.append("then ask your assistant: /tc-coverage working-tree (Claude Code or Copilot agent mode), or run "
                 "tcadvisor analyze --working-tree")
    return steps
