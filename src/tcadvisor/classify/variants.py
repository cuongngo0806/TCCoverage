"""Build-variant profile (spec 012 US3): which code is provably not built in any confirmed variant."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NO_PROFILE_NOTE = ("no confirmed build profile: nothing filtered; run 'tcadvisor profile' to confirm the build "
                   "variants")


@dataclass
class RunProfile:
    system: str
    variants: list[dict[str, Any]]
    state: str  # confirmed | stale | overridden
    fingerprint: str | None = None
    notes: list[str] = field(default_factory=list)


def profile_for_run(repo: Path, cfg: dict[str, Any], variants: str | None, use_filter: bool,
                    interactive: bool = False) -> tuple[RunProfile | None, list[str]]:
    """The profile a run applies (None = no filtering) and the run notes about it."""
    if not use_filter:
        return None, ["build profile ignored for this run (--no-variant-filter): nothing filtered"]
    prof = cfg.get("build")
    if not prof or not prof.get("confirmed"):
        return None, [NO_PROFILE_NOTE]
    chosen = prof["variants"]
    notes: list[str] = []
    state = "confirmed"
    if variants:
        names = [v.strip() for v in variants.split(",") if v.strip()]
        known = {v["name"] for v in chosen}
        unknown = [n for n in names if n not in known]
        if unknown:
            notes.append(f"unknown variant(s) {', '.join(unknown)} ignored (profile: {', '.join(sorted(known))})")
        chosen = [v for v in chosen if v["name"] in names]
        state = "overridden"
        if not chosen:
            return None, notes + [NO_PROFILE_NOTE]
    return RunProfile(prof.get("system", "auto"), chosen, state, prof.get("fingerprint")), notes
