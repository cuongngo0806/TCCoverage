"""CMake File API (codemodel-v2) reader: file -> owning target(s) (FR-005, research.md §2)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tcadvisor.models import PrerequisiteError

QUERY_HINT = (
    "Create the query file '<build>/.cmake/api/v1/query/codemodel-v2' (empty file) and re-run the CMake "
    "configure step so the File API reply is generated."
)


@dataclass
class TargetInfo:
    name: str
    type: str
    source_dir: Path
    sources: set[Path] = field(default_factory=set)
    dependencies: set[str] = field(default_factory=set)  # names of targets this one links/depends on


@dataclass
class TargetModel:
    targets: dict[str, TargetInfo]
    file_to_targets: dict[Path, set[str]]

    def targets_for(self, file: Path) -> set[str]:
        return set(self.file_to_targets.get(file, ()))

    def dependents_of(self, target: str) -> set[str]:
        """Targets that (transitively) depend on ``target`` — e.g. test executables linking a library."""
        out, frontier = set(), {target}
        while frontier:
            nxt = {t.name for t in self.targets.values() if t.dependencies & frontier} - out - {target}
            out |= nxt
            frontier = nxt
        return out

    def targets_for_cmake_file(self, cmake_file: Path) -> set[str]:
        d = cmake_file.parent
        return {t.name for t in self.targets.values() if t.source_dir == d or d in t.source_dir.parents}


def load_target_model(build_dir: Path) -> TargetModel:
    reply = build_dir / ".cmake" / "api" / "v1" / "reply"
    if not reply.is_dir():
        raise PrerequisiteError(f"CMake File API reply directory not found: '{reply}'. {QUERY_HINT}")
    indexes = sorted(reply.glob("index-*.json"))
    if not indexes:
        raise PrerequisiteError(f"No CMake File API index file in '{reply}'. {QUERY_HINT}")
    index = json.loads(indexes[-1].read_text(encoding="utf-8"))
    codemodel_file = None
    for obj in index.get("objects", []):
        if obj.get("kind") == "codemodel":
            codemodel_file = obj["jsonFile"]
    if not codemodel_file:
        raise PrerequisiteError(f"CMake File API reply in '{reply}' has no codemodel-v2 object. {QUERY_HINT}")
    codemodel = json.loads((reply / codemodel_file).read_text(encoding="utf-8"))
    src_root = Path(codemodel["paths"]["source"]).resolve()

    targets: dict[str, TargetInfo] = {}
    id_to_name: dict[str, str] = {}
    raw_deps: dict[str, list[str]] = {}
    for cfg in codemodel.get("configurations", []):
        for t in cfg.get("targets", []):
            tj = json.loads((reply / t["jsonFile"]).read_text(encoding="utf-8"))
            name = tj["name"]
            id_to_name[tj.get("id", name)] = name
            info = targets.setdefault(
                name,
                TargetInfo(name, tj.get("type", ""), (src_root / tj.get("paths", {}).get("source", ".")).resolve()),
            )
            for s in tj.get("sources", []):
                p = Path(s["path"])
                info.sources.add((p if p.is_absolute() else src_root / p).resolve())
            raw_deps.setdefault(name, []).extend(d["id"] for d in tj.get("dependencies", []))
    for name, deps in raw_deps.items():
        targets[name].dependencies = {id_to_name[d] for d in deps if d in id_to_name} - {name}

    file_to_targets: dict[Path, set[str]] = {}
    for t in targets.values():
        for s in t.sources:
            file_to_targets.setdefault(s, set()).add(t.name)
    return TargetModel(targets, file_to_targets)
