"""`tcadvisor init`: set up a repository for the tool (explicit, user-invoked; never touches application code).

Writes `<repo>/.tcadvisor/config.json` (the settings shared by the CLI, the VS Code extension and AI chat) and, with
`--copilot`, the GitHub Copilot prompt files `/tc-coverage` and `/tc-verify` under `<repo>/.github/prompts/`.
Existing files are kept unless `--force`.
"""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from tcadvisor.config import config_path, load_config

COPILOT_PROMPTS = ("tc-coverage.prompt.md", "tc-verify.prompt.md")


def _write(path: Path, text: str, force: bool) -> str:
    if path.exists() and not force:
        return "kept (exists; --force to overwrite)"
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    path.write_text(text, encoding="utf-8")
    return "overwritten" if existed else "created"


def init(repo: Path, settings: dict[str, Any], copilot: bool = False, force: bool = False) -> list[tuple[Path, str]]:
    repo = repo.resolve()
    if not (repo / ".git").exists():
        from tcadvisor.models import UsageError
        raise UsageError(f"--repo '{repo}' is not a git repository root")
    cfg = {"graph": "codegraph", "language": "vi", "build_dir": "build",
           **{k: v for k, v in settings.items() if v is not None}}
    path = config_path(repo)
    out = [(path, _write(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", force))]
    load_config(repo)  # validate what is on disk now
    if copilot:
        src = resources.files("tcadvisor.integrations").joinpath("copilot")
        for name in COPILOT_PROMPTS:
            target = repo / ".github" / "prompts" / name
            out.append((target, _write(target, src.joinpath(name).read_text(encoding="utf-8"), force)))
    return out
