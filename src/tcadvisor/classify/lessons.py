"""Team lessons and extra emitting points from ``.tcadvisor/lessons.json`` (spec 006, US1/US4).

Hand-written, local, deterministic: a lesson whose ``when`` matches a case adds its question to that case's
corner cases. ``sinks`` extend the built-in catalogue of emitting points used by data-path tracing.
Validated by hand against ``specs/006-lesson-patterns-test-report/contracts/lessons-config.schema.json``
(no jsonschema dependency at runtime).
"""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tcadvisor.models import UsageError

LESSONS_FILE = ".tcadvisor/lessons.json"
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
_WHEN_KEYS = {"tokens_any", "name_glob", "path_glob", "sub_reason"}


@dataclass
class Lesson:
    id: str
    title: str
    ask: str
    tokens_any: list[str] = field(default_factory=list)
    name_glob: str | None = None
    path_glob: str | None = None
    sub_reason: str | None = None

    def matches(self, name: str, path: str, tokens: set[str], sub_reason: str | None) -> bool:
        if self.tokens_any and not (set(self.tokens_any) & tokens):
            return False
        if self.name_glob and not (fnmatch.fnmatchcase(name, self.name_glob)
                                   or fnmatch.fnmatchcase(name.split("::")[-1], self.name_glob)):
            return False
        if self.path_glob and not fnmatch.fnmatchcase(path, self.path_glob):
            return False
        return not (self.sub_reason and self.sub_reason != sub_reason)


@dataclass
class LessonsConfig:
    sinks: list[str] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)

    def to_key(self) -> Any:
        return {"sinks": self.sinks, "lessons": [vars(l) for l in self.lessons]}


def load_lessons(repo: Path, explicit: Path | None = None) -> LessonsConfig:
    path = explicit if explicit is not None else repo / LESSONS_FILE
    if explicit is None and not path.is_file():
        return LessonsConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read lessons {path}: {exc}") from exc

    def bad(msg: str) -> UsageError:
        return UsageError(f"lessons {path}: {msg}")
    if not isinstance(data, dict) or set(data) - {"sinks", "lessons"}:
        raise bad("top level must be an object with optional 'sinks' and 'lessons'")
    sinks = data.get("sinks", [])
    if not isinstance(sinks, list) or not all(isinstance(s, str) and s for s in sinks):
        raise bad("'sinks' must be a list of non-empty strings")
    out = LessonsConfig(sinks=list(sinks))
    seen: set[str] = set()
    for i, raw in enumerate(data.get("lessons", [])):
        if not isinstance(raw, dict) or set(raw) - {"id", "title", "when", "ask"}:
            raise bad(f"lesson #{i + 1} must be an object with id, title, when, ask")
        lid, title, when, ask = raw.get("id"), raw.get("title"), raw.get("when"), raw.get("ask")
        if not isinstance(lid, str) or not _ID.match(lid) or lid in seen:
            raise bad(f"lesson #{i + 1}: 'id' must be a unique [A-Za-z0-9_.-]{{1,40}} string")
        if not (isinstance(title, str) and title and isinstance(ask, str) and ask):
            raise bad(f"lesson {lid}: 'title' and 'ask' must be non-empty strings")
        if not isinstance(when, dict) or not when or set(when) - _WHEN_KEYS:
            raise bad(f"lesson {lid}: 'when' needs at least one of {sorted(_WHEN_KEYS)}")
        toks = when.get("tokens_any", [])
        if not isinstance(toks, list) or not all(isinstance(t, str) for t in toks) or ("tokens_any" in when and not toks):
            raise bad(f"lesson {lid}: 'tokens_any' must be a non-empty list of strings")
        for k in ("name_glob", "path_glob", "sub_reason"):
            if k in when and not isinstance(when[k], str):
                raise bad(f"lesson {lid}: '{k}' must be a string")
        seen.add(lid)
        out.lessons.append(Lesson(lid, title, ask, list(toks), when.get("name_glob"), when.get("path_glob"),
                                  when.get("sub_reason")))
    return out
