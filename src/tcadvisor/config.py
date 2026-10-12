"""Project configuration `<repo>/.tcadvisor/config.json`, shared by the CLI and the AI chat front-ends (the
`tc-coverage` skill / prompts for Claude Code and GitHub Copilot that `tcadvisor init` installs), so every way of
running the tool on a workspace uses the same settings.

`include_tests` (default false): unit-test / mock code is left out (changed tests, test functions calling the change,
test files including it, re-run lists, test gaps); `test_paths` adds globs of such files. `ai_verify`: `off` (default),
`chat` (the skill / Copilot prompt AI-verifies every analysis before answering) or `claude` (`tcadvisor analyze` runs
the headless Claude Code verification itself; setting it approves sending the packed code windows to the model
provider). Cases an AI closes leave the main report for `report.ai-verified.*`.

Spec 012: reports go to `<repo>/.tcadvisor/reports/<run>/` (one folder per analysis); `build` holds the confirmed
build profile (build system + variants, see `index/variants.py`); the settings only the removed VS Code extension
could set (Claude binary / models / budget, impact-source binary, extra analysis options) are keys again.

Precedence: command-line flag > config file > built-in default. Unknown keys or invalid values are usage errors, so a
typo never silently selects another impact source, report language or build directory. Relative paths are relative
to the repository root.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

from tcadvisor.models import UsageError

GRAPHS = ("codegraph", "gitnexus", "clang")
LANGUAGES = ("vi", "en")
AI_VERIFY = ("off", "chat", "claude")
BUILD_SYSTEMS = ("auto", "cmake", "autotools")
INDEX_MODES = ("auto", "full", "lite")
FORMATS = ("md", "json", "html", "both", "all")
DEFAULTS: dict[str, Any] = {
    # core
    "graph": "codegraph", "language": "vi", "build_dir": "build", "output_dir": None, "targets": None,
    "max_hop_depth": 2, "include_tests": False, "test_paths": [], "ai_verify": "off",
    # build (spec 012)
    "build_system": "auto", "build": None,
    # analysis options (formerly CLI-only / VS Code extraArgs)
    "graph_bin": None, "contracts": None, "lessons": None, "target_patterns": None, "index": "auto", "jobs": None,
    "patterns": True, "history": True, "flow_max_tus": 4, "split_threshold": 50, "cache_dir": None,
    "allow_stale_compile_db": False,
    # report
    "format": "all", "attachment_warn_mb": 50,
    # AI verification (formerly VS Code ai.* settings)
    "python": None, "claude_bin": None, "verify_model": "haiku", "synth_model": "sonnet", "budget_usd": None,
    "verify_priorities": "P1,P2,P3", "verify_max_cases": 120, "verify_parallel": 4,
}
CHOICES = {"graph": GRAPHS, "language": LANGUAGES, "ai_verify": AI_VERIFY, "build_system": BUILD_SYSTEMS,
           "index": INDEX_MODES, "format": FORMATS}
PATH_KEYS = ("build_dir", "output_dir", "contracts", "lessons", "target_patterns", "cache_dir")
_STR_KEYS = ("graph_bin", "python", "claude_bin", "verify_model", "synth_model")
_BOOL_KEYS = ("include_tests", "patterns", "history", "allow_stale_compile_db")
_INT_MIN = {"max_hop_depth": 1, "jobs": 1, "flow_max_tus": 0, "split_threshold": 1, "attachment_warn_mb": 1,
            "verify_max_cases": 1, "verify_parallel": 1}
_NULLABLE = {k for k, v in DEFAULTS.items() if v is None}
_VARIANT_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_VARIANT_KEYS = {"name", "compile_db", "build_log", "log_sha256", "build_dir", "values", "value_source"}


def config_path(repo: Path) -> Path:
    return repo / ".tcadvisor" / "config.json"


def default_output_dir(repo: Path) -> Path:
    """Spec 012: reports live in the workspace, `<repo>/.tcadvisor/reports` (git-ignored locally); every analysis
    writes its own run folder inside it."""
    return repo.resolve() / ".tcadvisor" / "reports"


def check_build_profile(path: Path, value: Any) -> dict[str, Any]:
    """Validate the `build` key (contracts/config-build-profile.schema.json)."""
    def bad(msg: str) -> UsageError:
        return UsageError(f"{path}: 'build' {msg}")
    if not isinstance(value, dict):
        raise bad("must be an object {system, confirmed, variants}")
    extra = set(value) - {"system", "confirmed", "confirmed_at", "fingerprint", "variants"}
    if extra:
        raise bad(f"has unknown field(s) {', '.join(sorted(extra))}")
    if value.get("system", "auto") not in BUILD_SYSTEMS:
        raise bad(f"'system' must be one of {', '.join(BUILD_SYSTEMS)}")
    if not isinstance(value.get("confirmed", False), bool):
        raise bad("'confirmed' must be true or false")
    variants = value.get("variants")
    if not isinstance(variants, list) or not 1 <= len(variants) <= 16:
        raise bad("'variants' must be a list of 1-16 variants")
    seen: set[str] = set()
    for v in variants:
        if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not _VARIANT_NAME.match(v["name"]):
            raise bad("variant 'name' must match ^[A-Za-z0-9._-]+$")
        if v["name"] in seen:
            raise bad(f"variant name '{v['name']}' is used twice")
        seen.add(v["name"])
        if set(v) - _VARIANT_KEYS:
            raise bad(f"variant '{v['name']}' has unknown field(s) {', '.join(sorted(set(v) - _VARIANT_KEYS))}")
        for k in ("compile_db", "build_log", "log_sha256", "build_dir"):
            if v.get(k) is not None and not isinstance(v[k], str):
                raise bad(f"variant '{v['name']}': '{k}' must be a string")
        vals = v.get("values", {})
        if not isinstance(vals, dict) or not all(isinstance(x, (str, bool)) or x is None for x in vals.values()):
            raise bad(f"variant '{v['name']}': 'values' must map switch names to string, true/false or null")
        src = v.get("value_source", {})
        if not isinstance(src, dict) or any(x not in ("build", "user") for x in src.values()):
            raise bad(f"variant '{v['name']}': 'value_source' values must be 'build' or 'user'")
    return {"system": value.get("system", "auto"), "confirmed": value.get("confirmed", False),
            **{k: value[k] for k in ("confirmed_at", "fingerprint") if k in value}, "variants": variants}


def _check(path: Path, key: str, value: Any) -> Any:
    if key == "ai_verify" and isinstance(value, bool):
        value = "chat" if value else "off"
    if key not in DEFAULTS:
        close = difflib.get_close_matches(key, list(DEFAULTS), n=1)
        hint = f"; did you mean '{close[0]}'?" if close else f" (allowed: {', '.join(DEFAULTS)})"
        raise UsageError(f"{path}: unknown setting '{key}'{hint}")
    if value is None and key in _NULLABLE:
        return None
    if key in CHOICES:
        if value not in CHOICES[key]:
            raise UsageError(f"{path}: '{key}' must be one of {', '.join(CHOICES[key])}, not {value!r}")
    elif key in PATH_KEYS or key in _STR_KEYS:
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"{path}: '{key}' must be a {'path' if key in PATH_KEYS else 'non-empty'} (string)")
    elif key == "targets":
        if isinstance(value, list) and all(isinstance(t, str) for t in value):
            value = ",".join(value)
        if not isinstance(value, str):
            raise UsageError(f"{path}: 'targets' must be a list of build target / product names or a comma-separated "
                             "string")
    elif key in _INT_MIN:
        if not isinstance(value, int) or isinstance(value, bool) or value < _INT_MIN[key]:
            raise UsageError(f"{path}: '{key}' must be an integer >= {_INT_MIN[key]}")
        if key == "verify_parallel" and value > 16:
            raise UsageError(f"{path}: 'verify_parallel' must be <= 16")
    elif key in _BOOL_KEYS:
        if not isinstance(value, bool):
            raise UsageError(f"{path}: '{key}' must be true or false")
    elif key == "test_paths":
        if not (isinstance(value, list) and all(isinstance(t, str) and t.strip() for t in value)):
            raise UsageError(f"{path}: 'test_paths' must be a list of globs, e.g. [\"src/**/sim/*\"]")
    elif key == "budget_usd":
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise UsageError(f"{path}: 'budget_usd' must be a number > 0 (or null for no cap)")
    elif key == "verify_priorities":
        if isinstance(value, list):
            value = ",".join(value)
        prios = [p.strip() for p in str(value).split(",") if p.strip()]
        if not prios or any(p not in ("P1", "P2", "P3") for p in prios):
            raise UsageError(f"{path}: 'verify_priorities' must be a subset of P1,P2,P3")
        value = ",".join(prios)
    elif key == "build":
        value = check_build_profile(path, value)
    return value


def read_file(repo: Path) -> dict[str, Any]:
    """The raw (validated) keys present in the config file."""
    path = config_path(repo)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError(f"{path}: expected a JSON object like {json.dumps({k: v for k, v in DEFAULTS.items() if v})}")
    return {key: _check(path, key, value) for key, value in data.items()}


def load_config(repo: Path) -> dict[str, Any]:
    """The project's settings merged over the defaults (paths not yet resolved)."""
    return {**DEFAULTS, **read_file(repo)}


def resolve_sources(repo: Path, **flags: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Settings for one run plus where each came from (`flag`, `config`, `default`). A flag given on the command
    line wins over the config file. Path keys come back as absolute paths (config paths are relative to the
    repository root, flag paths to the cwd); `build_dir` and `output_dir` are always set."""
    file_keys = read_file(repo)
    cfg = {**DEFAULTS, **file_keys}
    src = {k: ("config" if k in file_keys else "default") for k in DEFAULTS}
    root = repo.resolve()
    for key in PATH_KEYS:
        if cfg[key] is not None:
            cfg[key] = (root / cfg[key]).resolve()
    for k, v in flags.items():
        if v is not None:
            cfg[k] = v
            src[k] = "flag"
    for key in PATH_KEYS:
        if cfg[key] is not None:
            cfg[key] = Path(cfg[key])
    if cfg["output_dir"] is None:
        cfg["output_dir"] = default_output_dir(repo)
    return cfg, src


def resolve(repo: Path, **flags: Any) -> dict[str, Any]:
    return resolve_sources(repo, **flags)[0]


def effective(repo: Path) -> dict[str, Any]:
    """`tcadvisor config --json`: the settings a run on `repo` uses, as JSON-ready values."""
    cfg = resolve(repo)
    out = {k: (str(v) if isinstance(v, Path) else v) for k, v in cfg.items()}
    out["config_file"] = str(config_path(repo.resolve())) if config_path(repo).is_file() else None
    return out


def effective_table(repo: Path) -> list[tuple[str, Any, str]]:
    """`tcadvisor config`: (key, effective value, source) for every key."""
    cfg, src = resolve_sources(repo)
    return [(k, str(cfg[k]) if isinstance(cfg[k], Path) else cfg[k], src[k]) for k in DEFAULTS]
