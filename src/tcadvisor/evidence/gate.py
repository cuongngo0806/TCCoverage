"""Evidence gate (FR-006, Principle II): no case leaves the tool without resolvable evidence."""
from __future__ import annotations

from pathlib import Path

from tcadvisor.models import ImpactEdge, SymbolRef, TestCaseCandidate


class EvidenceError(RuntimeError):
    """A candidate failed evidence resolution for a reason outside the uncertainty taxonomy (a bug)."""


def _resolves(repo: Path, ref: SymbolRef, known_names: set[str]) -> bool:
    if not (repo / ref.file_path).is_file():
        return False
    return ref.kind == "file" or ref.qualified_name in known_names


def gate(cases: list[TestCaseCandidate], repo: Path, known_names: set[str]) -> list[TestCaseCandidate]:
    passed = []
    for c in cases:
        ok = []
        for ev in c.evidence:
            ref = ev if isinstance(ev, SymbolRef) else ev.from_symbol
            if _resolves(repo, ref, known_names):
                ok.append(ev)
        if not ok or not isinstance(ok[0], SymbolRef):
            raise EvidenceError(f"case '{c.description}' has no resolvable evidence: {c.evidence!r}")
        c.evidence = ok
        if not c.related_cmake_targets:
            c.related_cmake_targets = ["(no CMake target owns this file)"]
        passed.append(c)
    return passed
