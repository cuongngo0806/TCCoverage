"""Changed data followed through unchanged modules to the code that sends it out (spec 006 US1).

Lesson: module A changed what it put into a frame; B and C were untouched, C forwarded the frame as it always
had and sent wrong data. The responsibility to validate was C's, but no review looked at C.

Starting from the lines a change touched, values are followed with the per-function facts of
``index/flow.py``: into callees through arguments, back to callers through return values and out-parameters,
up to a bounded number of function boundaries. Every *emitting* call reached (send / write / publish-like
names, third-party APIs, project sinks from ``lessons.json``) yields a DataPath: producer → forwarders →
emitter, with the functions where a condition reads the value marked as *checked*. Where the value leaves
what can be followed (stored in a member, a container kept beyond the function, a TU budget), a break is
recorded so it becomes an uncertainty flag instead of disappearing.
"""
from __future__ import annotations

import fnmatch
import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tcadvisor.models import SymbolRef

EMITTER_WORDS = {"send", "sendto", "sendmsg", "write", "writev", "fwrite", "publish", "post", "notify", "emit",
                 "transmit", "enqueue", "serialize", "deliver", "output", "upload", "broadcast", "reply", "respond"}
_NOT_EMITTER = {"log", "logger", "trace", "debug", "print", "printf", "dump", "assert"}
_CONTAINER_OPS = {"push_back", "push_front", "emplace_back", "emplace_front", "emplace", "insert", "push",
                  "insert_or_assign", "try_emplace"}
_WORD = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


@dataclass
class Step:
    usr: str
    name: str
    file: str
    line: int  # line where the value moves on (call / return)
    role: str  # producer | forwarder | emitter
    checked_at: int = 0  # line of a condition reading the value before it moves on (0 = none)
    detail: str = ""

    def ref(self, facts: dict[str, Any]) -> SymbolRef:
        return SymbolRef(self.name, "function", self.file, max(1, facts.get("line", self.line)))


@dataclass
class DataPath:
    root: str
    steps: list[Step]
    emitter_call: str
    emitter_line: int

    @property
    def checked(self) -> list[Step]:
        return [s for s in self.steps[1:] if s.checked_at]


@dataclass
class Break:
    root: str
    where: str
    line: int
    reason: str


@dataclass
class FlowIndex:
    """Lazily parsed flow facts, bounded by ``max_tus`` translation units (constitution V)."""
    repo: Path
    entries_by_file: dict[str, Any]  # repo-relative source file -> compile command
    tu_of_header: Callable[[str], str | None]
    cache: Any
    max_tus: int
    functions: dict[str, dict[str, Any]] = field(default_factory=dict)
    loaded: set[str] = field(default_factory=set)
    exhausted: bool = False
    preloaded: dict[str, dict[str, Any]] = field(default_factory=dict)  # changed files, parsed by ingest
    _extractor: Any = None

    def _tu_for(self, rel: str) -> str | None:
        if rel in self.entries_by_file:
            return rel
        p = Path(rel)
        for ext in (".cc", ".cpp", ".cxx", ".c"):
            for cand in (p.with_suffix(ext), Path(str(p.with_suffix(ext)).replace("/include/", "/src/"))):
                if cand.as_posix() in self.entries_by_file:
                    return cand.as_posix()
        return self.tu_of_header(rel)

    def load_file(self, rel: str) -> bool:
        if rel in self.preloaded:
            if rel not in self.loaded:
                self.loaded.add(rel)
                for usr, f in self.preloaded[rel]["functions"].items():
                    self.functions[usr] = f  # new revision wins over cached working-tree facts
            return True
        tu = self._tu_for(rel)
        if tu is None:
            return False
        if tu in self.loaded:
            return True
        if len(self.loaded) >= self.max_tus:
            self.exhausted = True
            return False
        from tcadvisor.index.clang_index import file_sha
        from tcadvisor.index.flow import FLOW_VERSION, FlowExtractor
        entry = self.entries_by_file[tu]
        key = hashlib.sha256(("\0".join(entry.args) + f"\0flow{FLOW_VERSION}").encode()).hexdigest()
        data = self.cache.get_flow(tu, key) if self.cache else None
        if data is None or not all(file_sha(self.repo / d) == h for d, h in data["deps"].items()):
            self._extractor = self._extractor or FlowExtractor(self.repo)
            try:
                data = self._extractor.extract_flow(entry.file, entry.args)
            except Exception:  # noqa: BLE001 - a TU libclang cannot load must not abort the analysis
                data = {"deps": {}, "functions": {}, "errors": 1}
            if self.cache and data["deps"]:
                self.cache.put_flow(tu, key, data)
        self.loaded.add(tu)
        for usr, f in data["functions"].items():
            self.functions.setdefault(usr, f)
        return True

    def get(self, usr: str, hint_file: str = "") -> dict[str, Any] | None:
        if usr not in self.functions and hint_file:
            self.load_file(hint_file)
        return self.functions.get(usr)


def words(name: str) -> set[str]:
    short = name.split("::")[-1]
    return {w.lower() for part in short.split("_") for w in _WORD.findall(part)}


def is_emitter(call: list[Any], sinks: list[str], is_third_party: Callable[[str, str], bool]) -> bool:
    _line, _usr, name, _def, external, *_ = call
    short = name.split("::")[-1]
    if any(fnmatch.fnmatchcase(name, p) or fnmatch.fnmatchcase(short, p) for p in sinks):
        return True
    if name.startswith(("std::", "__")):
        return False
    w = words(name)
    if w & _NOT_EMITTER:
        return False
    if external and is_third_party(name, external):
        return True
    return bool(w & EMITTER_WORDS)


def _taint(f: dict[str, Any], atoms: set[str], lines: set[int]) -> set[str]:
    t = set(atoms)
    events = sorted([(d[0], 0, d) for d in f["defs"]] + [(c[0], 1, c) for c in f["calls"]], key=lambda e: e[:2])
    for _ in range(2):  # second pass: values defined later in a loop body
        for line, kind, e in events:
            if kind == 0:
                if line in lines or t & set(e[2]):
                    t.add(e[1])
            else:
                _l, usr, _n, _d, _x, args, outs, base = e
                hot = line in lines or any(t & set(a) for a in args)
                if hot and base:
                    t.add(base)
                for k, tgt in outs:
                    if hot or f"outarg:{usr}:{k}" in t:
                        t.add(tgt)
    return t


def trace(index: FlowIndex, roots: list[tuple[str, SymbolRef, set[int]]], callers: Callable[[str], list[Any]],
          max_depth: int, sinks: list[str], is_third_party: Callable[[str, str], bool]
          ) -> tuple[list[DataPath], list[Break]]:
    """``roots``: (usr, ref, changed lines) of changed functions. Returns emitter paths and breaks."""
    paths: list[DataPath] = []
    breaks: list[Break] = []
    seen: set[tuple[str, str, frozenset]] = set()
    for root_usr, root_ref, lines in roots:
        rf = index.get(root_usr, root_ref.file_path)
        if rf is None:
            continue
        work = deque([(root_usr, frozenset(), frozenset(lines), [], 0)])
        while work:
            usr, atoms, hot_lines, path, depth = work.popleft()
            f = index.get(usr)
            if f is None or (root_usr, usr, atoms) in seen:
                continue
            seen.add((root_usr, usr, atoms))
            t = _taint(f, set(atoms), set(hot_lines))
            if not t and not hot_lines:
                continue
            role = "producer" if not path else "forwarder"
            for call in f["calls"]:
                line, cu, cname, cdef, cext, args, _outs, base = call
                ks = [k for k, a in enumerate(args) if t & set(a) or (line in hot_lines)]
                if not ks:
                    continue
                checked = max((c[0] for c in f["conds"] if c[0] <= line and t & set(c[1])), default=0)
                step = Step(usr, f["name"], f["file"], line, role, checked)
                if is_emitter(call, sinks, is_third_party):
                    wrapper = index.get(cu, cdef) if cdef and cu != usr and depth + 1 <= max_depth else None
                    if wrapper is not None:  # e.g. publish() wrapping transport_send(): follow to the real send
                        wt = _taint(wrapper, {f"param:{wrapper['params'][k]}" for k in ks
                                              if k < len(wrapper["params"])}, set())
                        if any(is_emitter(c2, sinks, is_third_party) and any(wt & set(a) for a in c2[5])
                               for c2 in wrapper["calls"]):
                            work.append((cu, frozenset(f"param:{wrapper['params'][k]}" for k in ks
                                                       if k < len(wrapper["params"])), frozenset(), path + [step],
                                         depth + 1))
                            continue
                    if path:  # the root emitting its own data is reviewed with the root itself
                        paths.append(DataPath(root_usr, path + [Step(usr, f["name"], f["file"], line, "emitter",
                                                                     checked, f"calls `{cname}`")], cname, line))
                    continue
                if cname.split("::")[-1] in _CONTAINER_OPS:
                    if base and not base.startswith("local:"):
                        breaks.append(Break(root_usr, f"{f['name']} ({f['file']}:{line})", line,
                                            f"stored into `{base.split(':', 1)[1]}` via `{cname}`"))
                    continue
                if depth + 1 > max_depth or cu == usr:
                    continue
                callee = index.get(cu, cdef) if cdef else None
                if callee is None:
                    if cdef and index.exhausted:
                        breaks.append(Break(root_usr, f"{f['name']} ({f['file']}:{line})", line,
                                            f"passed to `{cname}`, not traced (translation-unit budget reached)"))
                    continue
                params = callee["params"]
                work.append((cu, frozenset(f"param:{params[k]}" for k in ks if k < len(params)), frozenset(),
                             path + [step], depth + 1))
            stores = sorted({d[1] for d in f["defs"] if d[1].startswith(("member:", "global:")) and
                             (d[0] in hot_lines or t & set(d[2]))})
            if stores and path:
                breaks.append(Break(root_usr, f"{f['name']} ({f['file']}:{f['line']})", f["line"],
                                    "stored in " + ", ".join(f"`{s.split(':', 1)[1]}`" for s in stores[:3])))
            outs = [k for k, p in enumerate(f["params"]) if f["param_out"][k] and f"param:{p}" in t
                    and any(d[1] == f"param:{p}" for d in f["defs"])]
            if ("return" in t or outs) and depth + 1 <= max_depth:
                give = {f"call:{usr}"} | {f"outarg:{usr}:{k}" for k in outs}
                for dep in callers(usr):
                    if index.get(dep.dependent, dep.file) is not None:
                        work.append((dep.dependent, frozenset(give), frozenset(),
                                     path + [Step(usr, f["name"], f["file"], f["line"], role, 0, "returns it")],
                                     depth + 1))
    return paths, breaks
