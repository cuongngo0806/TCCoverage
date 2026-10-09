"""External code-graph providers (spec 002): impact comes from codegraph / GitNexus, normalised into
the advisor's own Graph so traversal, priority, evidence gate and reports stay identical."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from tcadvisor.graph.impact import Dep, Graph
from tcadvisor.index.clang_index import IndexFacts
from tcadvisor.models import SymbolRef, UncertaintyFlag, UsageError

KINDS = {"function", "method", "class", "struct", "enum", "macro", "variable", "file"}
_GTEST = re.compile(r"\b(TEST|TEST_F|TEST_P|TYPED_TEST|TYPED_TEST_P|FRIEND_TEST)\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)")
_TEST_NAMES = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST", "TYPED_TEST_P"}


@dataclass
class Root:
    node_id: str  # the advisor's root id (USR or file:...)
    name: str  # qualified name as the advisor knows it
    spelling: str  # last name component
    kind: str
    file: str
    line: int


@dataclass
class ProviderEdge:
    dependent: str
    dependency: str
    relation: str
    file: str
    line: int
    confidence: float | None = None
    heuristic: bool = False


@dataclass
class ProviderResult:
    edges: list[ProviderEdge] = field(default_factory=list)
    refs: dict[str, SymbolRef] = field(default_factory=dict)
    flags: list[UncertaintyFlag] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    flows: dict[str, list[str]] = field(default_factory=dict)  # node id -> execution flows (GitNexus processes)


class Provider:
    name = "base"
    env_var = ""
    binary = ""

    def __init__(self, repo: Path, depth: int, bin_path: str | None = None):
        self.repo = repo
        self.depth = depth
        self.bin = bin_path or os.environ.get(self.env_var) or shutil.which(self.binary)
        if not self.bin:
            raise UsageError(f"--graph {self.name}: '{self.binary}' not found on PATH (set {self.env_var} or "
                             f"install it, see README 'Graph providers')")

    def run(self, *args: str, timeout: int = 600) -> str:
        env = dict(os.environ, CODEGRAPH_TELEMETRY="0", NO_COLOR="1", DO_NOT_TRACK="1")
        res = subprocess.run([self.bin, *args], cwd=self.repo, capture_output=True, text=True, timeout=timeout,
                             env=env, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            raise RuntimeError(f"{self.binary} {' '.join(args)} failed: {res.stderr.strip()[-500:]}")
        return res.stdout

    def run_json(self, *args: str) -> dict:
        out = self.run(*args)
        start = out.find("{")
        return json.loads(out[start:]) if start >= 0 else {}

    def exclude_index_dir(self, dirname: str) -> None:
        """Keep the provider's index out of `git status` without touching tracked files (Principle VIII)."""
        ex = self.repo / ".git" / "info" / "exclude"
        try:
            text = ex.read_text() if ex.exists() else ""
            if dirname not in text.split():
                ex.parent.mkdir(parents=True, exist_ok=True)
                ex.write_text(text + ("" if text.endswith("\n") or not text else "\n") + dirname + "\n")
        except OSError:
            pass

    def prepare(self) -> list[str]:
        raise NotImplementedError

    def impact(self, roots: list[Root]) -> ProviderResult:
        raise NotImplementedError


def norm_kind(k: str | None) -> str:
    k = (k or "").lower()
    return k if k in KINDS else {"constructor": "method", "namespace": "file", "typedef": "class",
                                 "interface": "class", "union": "struct", "module": "file"}.get(k, "function")


def strip_anon(name: str) -> str:
    return name.replace("(anonymous)::", "").replace("(anonymous namespace)::", "")


def test_label(repo: Path, ref: SymbolRef) -> str | None:
    """`Suite.Name` for a GoogleTest-style test body (optional adapter; nothing is executed)."""
    if ref.qualified_name.split("::")[-1] not in _TEST_NAMES:
        return None
    try:
        lines = (repo / ref.file_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for ln in lines[max(0, ref.line - 1): ref.line + 2]:
        m = _GTEST.search(ln)
        if m:
            return f"{m.group(2)}.{m.group(3)}"
    return None


def build_overlay(base: Graph | None, facts: IndexFacts, results: ProviderResult) -> Graph:
    g = Graph(facts)
    if base is not None:
        g.file_targets = base.file_targets
    g.refs = dict(results.refs)
    seen = set()
    for e in results.edges:
        key = (e.dependent, e.dependency, e.relation)
        if key in seen or e.dependent == e.dependency:
            continue
        seen.add(key)
        g.dependents[e.dependency].append(Dep(e.dependent, e.relation, e.file, max(1, e.line)))
        if e.relation == "inherit_override":
            g.override_group[e.dependent].add(e.dependency)
            g.override_group[e.dependency].add(e.dependent)
    return g


def get_provider(name: str, repo: Path, depth: int, bin_path: str | None = None) -> Provider | None:
    from tcadvisor.graph.providers.codegraph import CodegraphProvider
    from tcadvisor.graph.providers.gitnexus import GitNexusProvider

    if name == "clang":
        return None
    if name == "auto":
        if os.environ.get("TCADVISOR_CODEGRAPH") or shutil.which("codegraph"):
            return CodegraphProvider(repo, depth, bin_path)
        return None
    if name == "codegraph":
        return CodegraphProvider(repo, depth, bin_path)
    if name == "gitnexus":
        return GitNexusProvider(repo, depth, bin_path)
    raise UsageError(f"unknown --graph '{name}'")
