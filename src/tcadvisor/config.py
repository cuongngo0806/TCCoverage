"""Project configuration `<repo>/.tcadvisor/config.json`, shared by the CLI, the VS Code extension and workflows.

Precedence: command-line flag > config file > built-in default. Unknown keys or values are usage errors, so a typo
never silently selects another impact source or report language.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tcadvisor.models import UsageError

GRAPHS = ("codegraph", "gitnexus", "clang")
LANGUAGES = ("vi", "en")
DEFAULTS: dict[str, Any] = {"graph": "codegraph", "language": "vi"}
CHOICES = {"graph": GRAPHS, "language": LANGUAGES}


def config_path(repo: Path) -> Path:
    return repo / ".tcadvisor" / "config.json"


def load_config(repo: Path) -> dict[str, Any]:
    """The project's settings merged over the defaults."""
    path = config_path(repo)
    cfg = dict(DEFAULTS)
    if not path.is_file():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError(f"{path}: expected a JSON object like {json.dumps(DEFAULTS)}")
    for key, value in data.items():
        if key not in CHOICES:
            raise UsageError(f"{path}: unknown setting '{key}' (allowed: {', '.join(CHOICES)})")
        if value not in CHOICES[key]:
            raise UsageError(f"{path}: '{key}' must be one of {', '.join(CHOICES[key])}, not {value!r}")
        cfg[key] = value
    return cfg


def resolve(repo: Path, **flags: Any) -> dict[str, Any]:
    """Settings for one run: a flag given on the command line wins over the config file."""
    cfg = load_config(repo)
    cfg.update({k: v for k, v in flags.items() if v is not None})
    return cfg
