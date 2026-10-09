"""Explicit symbol input (FR-001 b / FR-001a): symbols only, never bare files."""
from __future__ import annotations

import json
import re
from pathlib import Path

from tcadvisor.index.clang_index import IndexFacts
from tcadvisor.models import UsageError

_FILE_LIKE = re.compile(r"[/\\]|\.(c|cc|cpp|cxx|h|hh|hpp|hxx|inl)$", re.I)
ALLOWED_KINDS = {"function", "method", "class", "struct"}


def parse_symbol_args(symbols: str | None, symbols_file: str | None) -> list[str]:
    names: list[str] = []
    if symbols:
        names = [s.strip() for s in symbols.split(",") if s.strip()]
    elif symbols_file:
        try:
            data = json.loads(Path(symbols_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UsageError(f"cannot read symbols file '{symbols_file}': {exc}") from exc
        items = data.get("symbols", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise UsageError("symbols file must contain a JSON list (or {\"symbols\": [...]})")
        for it in items:
            if isinstance(it, str):
                names.append(it)
            elif isinstance(it, dict) and it.get("qualified_name"):
                names.append(str(it["qualified_name"]))
            else:
                raise UsageError(f"symbols file entry {it!r} has no 'qualified_name'; a file path alone is not "
                                 "an acceptable entry (FR-001a)")
    if not names:
        raise UsageError("no symbols given")
    for n in names:
        if _FILE_LIKE.search(n):
            raise UsageError(f"'{n}' looks like a file path. Explicit mode accepts functions/methods/classes "
                             "only (e.g. ns::Class::method), never whole files (FR-001a)")
    return names


def resolve_symbols(names: list[str], facts: IndexFacts) -> dict[str, list[str]]:
    """name -> list of USRs (all overloads). Unknown names are a usage error."""
    out: dict[str, list[str]] = {}
    missing = []
    for name in names:
        n = name.lstrip(":")
        exact = [u for u, s in facts.symbols.items() if s["name"] == n and s["kind"] in ALLOWED_KINDS]
        if not exact:
            exact = [u for u, s in facts.symbols.items()
                     if s["name"].endswith("::" + n) and s["kind"] in ALLOWED_KINDS]
        if not exact:
            missing.append(name)
        else:
            out[name] = sorted(exact)
    if missing:
        raise UsageError("symbol(s) not found in the index (must be a function/method/class): " + ", ".join(missing))
    return out
