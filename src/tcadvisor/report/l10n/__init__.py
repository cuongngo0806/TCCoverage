"""Report language (vi default, en): render-time translation of the report's English text.

``report.json`` keeps the English text the pipeline emits (the machine contract: AI verifiers, case keys, lessons and
tests read it); the Markdown, HTML and brief renderings - and the VS Code view, through the ``l10n`` map written into
``report.json`` - show it in ``report_language``.

Catalog entries are ``(english_template, translated_template)`` pairs. A template is literal text with placeholders:

* ``{name}``   - any text, copied as is (symbol names, files, numbers, code);
* ``{t_name}`` - any text that is itself translated (a nested sentence or label).

A sentence is matched against the whole template (most literal text first). Sentences no entry matches are tried as
``"; "``-joined parts; anything still unmatched is shown in English and reported by :meth:`Translator.misses`
(tests require none for the reports of the test projects).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Iterable

LANGUAGES = ("vi", "en")
_PH = re.compile(r"\{(t_)?([a-z][a-z0-9_]*)\}")


def _compile(en: str) -> re.Pattern[str]:
    out, pos, seen = [], 0, set()
    for m in _PH.finditer(en):
        out.append(re.escape(en[pos:m.start()]))
        name = (m.group(1) or "") + m.group(2)
        if name in seen:
            raise ValueError(f"duplicate placeholder {{{name}}} in {en!r}")
        seen.add(name)
        out.append(f"(?P<{name}>.+?)")
        pos = m.end()
    out.append(re.escape(en[pos:]))
    return re.compile("".join(out), re.S)


def _literal_len(en: str) -> int:
    return len(_PH.sub("", en))


@lru_cache(maxsize=None)
def _catalog(lang: str) -> tuple[dict[str, str], list[tuple[re.Pattern[str], str, str]]]:
    if lang != "vi":
        return {}, []
    from tcadvisor.report.l10n import vi
    exact: dict[str, str] = {}
    rules: list[tuple[re.Pattern[str], str, str]] = []
    for en, tr in vi.entries():
        exact.setdefault(en, tr)  # also the lookup of ui() templates
        if _PH.search(en):
            rules.append((_compile(en), tr, en))
    rules.sort(key=lambda r: (-_literal_len(r[2]), r[2]))
    return exact, rules


class Translator:
    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in LANGUAGES else "en"
        self._exact, self._rules = _catalog(self.lang)
        self._misses: dict[str, int] = {}
        self._memo: dict[str, str | None] = {}

    @property
    def active(self) -> bool:
        return self.lang != "en"

    def ui(self, en: str, **kw: Any) -> str:
        """Fixed report wording (headings, labels); ``en`` is an English template with ``{name}`` fields."""
        text = self._exact.get(en, en) if self.active else en
        return text.format(**kw) if kw else text

    def __call__(self, text: str | None) -> str:
        """A sentence emitted by the pipeline."""
        if not text or not self.active:
            return text or ""
        out = self._sentence(text)
        if out is None:
            parts = text.split("; ")
            done = [self._sentence(p) for p in parts] if len(parts) > 1 else [None]
            if all(d is not None for d in done):
                return "; ".join(d for d in done if d is not None)
            self._misses[text] = self._misses.get(text, 0) + 1
            return text
        return out

    def _sentence(self, text: str) -> str | None:
        if text in self._memo:
            return self._memo[text]
        out = self._exact.get(text)
        if out is None:
            for pat, tr, _en in self._rules:
                m = pat.fullmatch(text)
                if m:
                    vals = {k: (self(v) if k.startswith("t_") else v) for k, v in m.groupdict().items()}
                    out = tr.format(**vals)
                    break
        self._memo[text] = out
        return out

    def all(self, texts: Iterable[str]) -> list[str]:
        return [self(t) for t in texts]

    def misses(self) -> dict[str, int]:
        return dict(self._misses)


def localize(r: dict[str, Any], T: Translator) -> dict[str, Any]:
    """A copy of report ``r`` whose pipeline-emitted text is in ``T``'s language (identity for English)."""
    if not T.active:
        return r

    def case(c: dict[str, Any]) -> dict[str, Any]:
        return {**c, "description": T(c["description"]), "activation_condition": T(c["activation_condition"]),
                "corner_cases": T.all(c.get("corner_cases") or []),
                "target_reasons": T.all(c.get("target_reasons") or []),
                "related_cmake_targets": [T(x) if x.startswith("(") else x for x in c.get("related_cmake_targets") or []],
                **({"path": [{**x, "role": T(x["role"])} for x in c["path"]]} if c.get("path") else {})}

    def sym(s: dict[str, Any]) -> dict[str, Any]:
        return {**s, "risks": [{**x, "detail": T(x.get("detail")), "hints": T.all(x.get("hints") or [])}
                               for x in s.get("risks") or []]}

    return {**r,
            "test_case_candidates": [case(c) for c in r["test_case_candidates"]],
            "changed_symbols": [sym(s) for s in r.get("changed_symbols") or []],
            "uncertainty_flags": [{**f, "reason": T(f["reason"])} for f in r["uncertainty_flags"]],
            "test_gaps": [{**g, "reason": T(g["reason"])} for g in r.get("test_gaps") or []],
            "run_notes": T.all(r.get("run_notes") or []),
            "out_of_scope": [{**o, "reason": T(o["reason"])} for o in r.get("out_of_scope") or []],
            "affected_targets": [{**t, "relation": T(t["relation"])} for t in r.get("affected_targets") or []],
            "trigger_sources": [{**t, "sources": [{**x, "guard": T(x.get("guard"))} for x in t["sources"]]}
                                for t in r.get("trigger_sources") or []]}


def l10n_map(r: dict[str, Any], T: Translator) -> dict[str, str]:
    """English -> translated text for every translated string of ``r`` (the VS Code view reads report.json)."""
    if not T.active:
        return {}
    loc, out = localize(r, T), {}

    def walk(a: Any, b: Any) -> None:
        if isinstance(a, str):
            if a != b:
                out[a] = b
        elif isinstance(a, dict):
            for k in a:
                walk(a[k], b.get(k) if isinstance(b, dict) else None)
        elif isinstance(a, list) and isinstance(b, list):
            for x, y in zip(a, b):
                walk(x, y)

    walk(r, loc)
    return out
