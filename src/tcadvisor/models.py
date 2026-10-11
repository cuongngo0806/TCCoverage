"""Logical data model (data-model.md). Plain dataclasses, JSON-serialisable via ``to_dict``."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

RISK_GROUPS = (
    "logic",
    "abi_layout",
    "ownership_lifetime",
    "thread_safety",
    "exception_safety",
    "build_config",
)
# FR-004a: these outrank logic/build_config.
HIGH_SEVERITY = frozenset({"abi_layout", "thread_safety", "exception_safety", "ownership_lifetime"})

RELATIONS = ("call", "inherit_override", "include", "instantiate", "link_to_target", "uses_type", "macro_expand")
UNCERTAINTY_CATEGORIES = (
    "uninstantiated_template",
    "dynamic_runtime_dependency",
    "di_config_routing",
    "build_config_incomplete_macro",
)


class PrerequisiteError(Exception):
    """FR-013: missing/stale compile database or CMake File API reply (exit code 1)."""


class UsageError(Exception):
    """Invalid or conflicting user input (exit code 2)."""


@dataclass(frozen=True)
class SymbolRef:
    qualified_name: str
    kind: str  # function|method|class|struct|enum|macro|variable|file
    file_path: str  # repo-relative, posix separators
    line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def label(self) -> str:
        return self.qualified_name


@dataclass(frozen=True)
class ImpactEdge:
    relation: str
    from_symbol: SymbolRef
    to_symbol: SymbolRef
    file_path: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "from_symbol": self.from_symbol.to_dict(),
            "to_symbol": self.to_symbol.to_dict(),
            "source_location": {"file_path": self.file_path, "line": max(1, self.line)},
        }


@dataclass
class ImpactNode:
    node_id: str
    symbol: SymbolRef
    hop_distance: int  # 0 = changed root, 1 = direct, 2.. = indirect
    edges: list[ImpactEdge] = field(default_factory=list)
    root_ids: set[str] = field(default_factory=set)
    risk_groups: set[str] = field(default_factory=set)
    targets: list[str] = field(default_factory=list)
    root_hops: dict[str, int] = field(default_factory=dict)  # root id -> hop distance from that root
    root_edges: dict[str, list[ImpactEdge]] = field(default_factory=dict)  # root id -> justifying edges

    def add_reach(self, root: str, hop: int, groups: set[str], edge: ImpactEdge) -> None:
        self.root_ids.add(root)
        self.risk_groups |= groups
        self.root_hops[root] = min(hop, self.root_hops.get(root, hop))
        lst = self.root_edges.setdefault(root, [])
        if edge not in lst and len(lst) < 6:
            lst.append(edge)
        if edge not in self.edges and len(self.edges) < 12:
            self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "symbol": self.symbol.to_dict(),
            "hop_distance": self.hop_distance,
            "edges": [e.to_dict() for e in self.edges],
            "roots": sorted(self.root_ids),
            "risk_groups": sorted(self.risk_groups),
            "targets": self.targets,
        }


@dataclass
class RiskClassification:
    risk_group: str
    sub_reason: str | None
    detail: str  # concrete, English explanation of the triggering signal
    hints: list[str] = field(default_factory=list)  # corner cases to exercise
    affected_build_configs: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChangedSymbol:
    """A root of the impact traversal: a symbol (or file) whose semantics changed."""

    node_id: str
    symbol: SymbolRef
    change_kind: str  # modified|added|removed
    risks: list[RiskClassification] = field(default_factory=list)
    is_template: bool = False
    is_virtual: bool = False
    in_conditional: list[str] = field(default_factory=list)  # preprocessor conditions around residual lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "symbol": self.symbol.to_dict(),
            "change_kind": self.change_kind,
            "risks": [r.to_dict() for r in self.risks],
        }


@dataclass
class PathStep:
    """One function on a data path (spec 006 US1) or a trigger-source chain (US2)."""
    symbol: SymbolRef
    role: str  # producer|forwarder|emitter|source|via|target
    line: int
    checked: bool = False  # a condition reads the value here before it moves on
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol.to_dict(), "role": self.role, "line": max(1, self.line),
                "checked": self.checked, "detail": self.detail}


@dataclass
class TestCaseCandidate:
    id: str
    description: str
    activation_condition: str
    evidence: list[SymbolRef | ImpactEdge]
    priority: str
    risk_group: str
    related_cmake_targets: list[str]
    node_id: str = ""
    sub_reason: str | None = None
    hop_distance: int = 0
    hints: list[str] = field(default_factory=list)
    bug_history: int = 0  # fix commits touching the evidence file in the last 12 months (ranking signal)
    key: str = ""  # stable identity across runs (spec 006 FR-612), independent of list position
    code_fingerprint: str = ""  # hash of the evidence function text: carried-over results need re-check if it moves
    pattern: str | None = None  # lesson pattern behind the case (spec 006)
    path: list[PathStep] | None = None
    lessons: list[str] = field(default_factory=list)
    test_result: dict[str, Any] | None = None  # tester's record (distinct from the AI `verification`)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "activation_condition": self.activation_condition,
            "evidence": [e.to_dict() for e in self.evidence],
            "priority": self.priority,
            "risk_group": self.risk_group,
            "sub_reason": self.sub_reason,
            "hop_distance": self.hop_distance,
            "node_id": self.node_id,
            "corner_cases": self.hints,
            "bug_history": self.bug_history,
            "related_cmake_targets": self.related_cmake_targets,
            "key": self.key,
            "code_fingerprint": self.code_fingerprint,
            "pattern": self.pattern,
            "path": [s.to_dict() for s in self.path] if self.path else None,
            "lessons": self.lessons,
            "test_result": self.test_result,
        }


@dataclass
class UncertaintyFlag:
    category: str
    reason: str
    related_symbol: SymbolRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "reason": self.reason,
            "related_symbol": self.related_symbol.to_dict() if self.related_symbol else None,
        }


@dataclass
class ChangeInput:
    mode: str  # git_diff|explicit_symbols
    target_repo_path: str
    commit_range: str | None = None
    working_tree: bool = False
    symbols: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "mode": self.mode,
            "target_repo_path": self.target_repo_path,
            "commit_range": self.commit_range,
            "working_tree": self.working_tree,
            "symbols": None,
        }
        if self.symbols is not None:
            d["symbols_requested"] = list(self.symbols)
        return d
