"""Project configuration `<repo>/.tcadvisor/config.json`, shared by the CLI and the AI chat front-ends (the
`tc-coverage` skill / prompts for Claude Code and GitHub Copilot that `tcadvisor init` installs), so every way of
running the tool on a workspace uses the same settings.

`include_tests` (default false): unit-test / mock code is left out (changed tests, test functions calling the change,
test files including it, re-run lists, test gaps); `test_paths` adds globs of such files. `ai_verify`: `off` (default),
`chat` (the skill / Copilot prompt AI-verifies every analysis before answering) or `claude` (`tcadvisor analyze` runs
the headless Claude Code verification itself; setting it approves sending the packed code windows to the model
provider). Cases an AI closes leave the main report for `report.ai-verified.*`.

Precedence: command-line flag > config file > built-in default. Unknown keys or invalid values are usage errors, so a
typo never silently selects another impact source, report language or build directory. Relative paths are relative
to the repository root.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tcadvisor.models import UsageError

GRAPHS = ("codegraph", "gitnexus", "clang")
LANGUAGES = ("vi", "en")
AI_VERIFY = ("off", "chat", "claude")
DEFAULTS: dict[str, Any] = {"graph": "codegraph", "language": "vi", "build_dir": "build", "output_dir": None,
                            "targets": None, "max_hop_depth": 2, "include_tests": False, "test_paths": [],
                            "ai_verify": "off"}
CHOICES = {"graph": GRAPHS, "language": LANGUAGES, "ai_verify": AI_VERIFY}


def config_path(repo: Path) -> Path:
    return repo / ".tcadvisor" / "config.json"


def default_output_dir(repo: Path) -> Path:
    """Outside the analysed repository (the advisor never writes into it): <repo>/../tcadvisor-report/<name>."""
    r = repo.resolve()
    return r.parent / "tcadvisor-report" / r.name


def _check(path: Path, key: str, value: Any) -> Any:
    if key == "ai_verify" and isinstance(value, bool):
        value = "chat" if value else "off"
    if key in CHOICES:
        if value not in CHOICES[key]:
            raise UsageError(f"{path}: '{key}' must be one of {', '.join(CHOICES[key])}, not {value!r}")
    elif key in ("build_dir", "output_dir"):
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"{path}: '{key}' must be a path (string)")
    elif key == "targets":
        if isinstance(value, list) and all(isinstance(t, str) for t in value):
            value = ",".join(value)
        if not isinstance(value, str):
            raise UsageError(f"{path}: 'targets' must be a list of CMake target names or a comma-separated string")
    elif key == "max_hop_depth":
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise UsageError(f"{path}: 'max_hop_depth' must be an integer >= 1")
    elif key == "include_tests":
        if not isinstance(value, bool):
            raise UsageError(f"{path}: 'include_tests' must be true or false")
    elif key == "test_paths":
        if not (isinstance(value, list) and all(isinstance(t, str) and t.strip() for t in value)):
            raise UsageError(f"{path}: 'test_paths' must be a list of globs, e.g. [\"src/**/sim/*\"]")
    else:
        raise UsageError(f"{path}: unknown setting '{key}' (allowed: {', '.join(DEFAULTS)})")
    return value


def load_config(repo: Path) -> dict[str, Any]:
    """The project's settings merged over the defaults (paths not yet resolved)."""
    path = config_path(repo)
    cfg = dict(DEFAULTS)
    if not path.is_file():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError(f"{path}: expected a JSON object like {json.dumps({k: v for k, v in DEFAULTS.items() if v})}")
    for key, value in data.items():
        cfg[key] = _check(path, key, value)
    return cfg


def resolve(repo: Path, **flags: Any) -> dict[str, Any]:
    """Settings for one run: a flag given on the command line wins over the config file. `build_dir` and
    `output_dir` come back as absolute paths (config paths are relative to the repository root)."""
    cfg = load_config(repo)
    root = repo.resolve()
    for key in ("build_dir", "output_dir"):  # config paths are relative to the repository root
        if cfg[key] is not None:
            cfg[key] = (root / cfg[key]).resolve()
    cfg.update({k: v for k, v in flags.items() if v is not None})  # flag paths are relative to the cwd
    cfg["build_dir"] = Path(cfg["build_dir"])
    cfg["output_dir"] = Path(cfg["output_dir"]) if cfg["output_dir"] is not None else default_output_dir(repo)
    return cfg


def effective(repo: Path) -> dict[str, Any]:
    """`tcadvisor config`: the settings a run on `repo` uses, as JSON-ready values."""
    cfg = resolve(repo)
    return {**cfg, "build_dir": str(cfg["build_dir"]), "output_dir": str(cfg["output_dir"]),
            "config_file": str(config_path(repo.resolve())) if config_path(repo).is_file() else None}
