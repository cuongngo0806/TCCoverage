"""Lite index for graph-provider mode (large repositories).

When impact comes from codegraph/GitNexus, parsing every translation unit with libclang is unnecessary.
This scan builds only what the rest of the pipeline needs from the compile database side — the include
graph (header -> includers, header -> translation units for compiler flags and CMake targets) — with a
regex over `#include` lines, resolved against the repository's files. Seconds instead of minutes on
~1M-line code bases. Symbols, call edges etc. come from the provider.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

from tcadvisor.index.clang_index import IndexFacts
from tcadvisor.index.compile_db import CPP_EXT, CompileDatabase

_INC = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.M)
_SKIP_DIRS = {".git", ".codegraph", ".gitnexus", "node_modules", "build", "third-party", "third_party", "external"}


def scan(repo: Path, cdb: CompileDatabase) -> tuple[IndexFacts, dict[str, int]]:
    repo = repo.resolve()
    files: list[str] = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not (Path(root) / d / "CMakeCache.txt").exists()]
        for n in names:
            if Path(n).suffix.lower() in CPP_EXT:
                files.append((Path(root) / n).relative_to(repo).as_posix())
    by_suffix: dict[str, list[str]] = defaultdict(list)
    for f in files:
        parts = f.split("/")
        for i in range(len(parts)):
            by_suffix["/".join(parts[i:])].append(f)
    facts = IndexFacts(repo)
    direct: dict[str, set[str]] = defaultdict(set)
    for f in files:
        try:
            text = (repo / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _INC.finditer(text):
            inc = m.group(1)
            cands = by_suffix.get(inc, [])
            if len(cands) > 1:  # prefer the includer's directory, then the shortest path
                here = str(Path(f).parent / inc).replace("\\", "/")
                cands = [c for c in cands if c == here] or sorted(cands, key=len)[:1]
            for c in cands:
                if c != f:
                    line = text.count("\n", 0, m.start()) + 1
                    facts.includes.add((f, c, line))
                    direct[f].add(c)
    tus = 0
    for e in cdb.entries:
        try:
            rel = e.file.relative_to(repo).as_posix()
        except ValueError:
            continue
        tus += 1
        seen, stack = {rel}, [rel]
        while stack:
            for d in direct.get(stack.pop(), ()):
                if d not in seen:
                    seen.add(d)
                    stack.append(d)
        facts.tu_files[rel] = seen
    return facts, {"tus": tus, "reparsed": 0, "reused": 0, "lite_files": len(files),
                   "lite_includes": len(facts.includes)}
