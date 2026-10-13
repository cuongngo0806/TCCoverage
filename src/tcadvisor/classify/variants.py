"""Build-variant profile (spec 012 US3, research R5/R6): cases whose evidence is provably not built in any confirmed
variant leave the main list for `not_built` (they stay in report.json, with the excluding condition).

A location (file, line) is *not built in variant V* when
* the file is a source no active product of V lists (automake conditionals of `Makefile.am` false in V) or, when V
  has its own compile database, a source file absent from it (`source_not_in_compile_db`); or
* its enclosing `#if` chain evaluates to false with V's macro values (command-line `-D`/`-U` of V's compile
  database, the generated `config.h`, values the user set at confirmation).

Three-valued logic everywhere: anything that cannot be decided (unknown macro, function-like macro, `__has_include`)
keeps the case and adds an uncertainty flag. A case moves only when **every** evidence location is not built in
**every** selected variant (recall first, Principle VII).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NO_PROFILE_NOTE = ("no confirmed build profile: nothing filtered; run 'tcadvisor profile' to confirm the build "
                   "variants")
Value = Any  # str (defined, with that text) | False (known undefined / off) | True (on) | None (unknown)


@dataclass
class RunProfile:
    system: str
    variants: list[dict[str, Any]]
    state: str  # confirmed | stale | overridden
    fingerprint: str | None = None
    notes: list[str] = field(default_factory=list)


def profile_for_run(repo: Path, cfg: dict[str, Any], variants: str | None, use_filter: bool,
                    interactive: bool = False) -> tuple[RunProfile | None, list[str]]:
    """The profile a run applies (None = no filtering) and the run notes about it. Interactive first run without a
    confirmed profile: the confirmation dialog runs first (`tcadvisor profile`)."""
    if not use_filter:
        return None, ["build profile ignored for this run (--no-variant-filter): nothing filtered"]
    prof = cfg.get("build")
    if (not prof or not prof.get("confirmed")) and interactive:
        from tcadvisor.index.variants import confirm_interactively
        prof = confirm_interactively(repo, cfg)
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


# ---- #if evaluation ---------------------------------------------------------------------------------------------
_TOKEN = re.compile(r"\s*(?:(0[xX][0-9a-fA-F]+|\d+)[uUlL]*|([A-Za-z_]\w*)|(\|\||&&|==|!=|<=|>=|<<|>>|[-+*/%<>!~&|^()?:,])"
                    r"|('(?:\\.|[^'])*'))")


class _Unknown(Exception):
    pass


def _tokens(expr: str) -> list[str]:
    out, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise _Unknown(expr[pos:])
        if m.group(4):
            raise _Unknown("character literal")
        out.append(m.group(1) or m.group(2) or m.group(3))
        pos = m.end()
    return out


def _macro_int(v: Value, values: dict[str, Value], depth: int) -> int | None:
    if v is None:
        return None
    if v is False:
        return 0
    if v is True:
        return 1
    text = str(v).strip() or "1"  # `#define X` with an empty body: defined, value 1 in practice for flags
    try:
        return int(text.rstrip("uUlL"), 0)
    except ValueError:
        return evaluate_expr(text, values, depth + 1) if depth < 8 else None


class _Parser:
    """Recursive descent over C preprocessor expressions; None = unknown (three-valued)."""

    def __init__(self, toks: list[str], values: dict[str, Value], depth: int):
        self.t, self.i, self.values, self.depth = toks, 0, values, depth

    def peek(self) -> str | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self) -> str:
        if self.i >= len(self.t):
            raise _Unknown("unexpected end")
        self.i += 1
        return self.t[self.i - 1]

    def parse(self) -> int | None:
        v = self.ternary()
        if self.peek() is not None:
            raise _Unknown("trailing tokens")
        return v

    def ternary(self) -> int | None:
        c = self.binary(0)
        if self.peek() == "?":
            self.take()
            a = self.ternary()
            if self.take() != ":":
                raise _Unknown("?:")
            b = self.ternary()
            if c is None:
                return a if a == b else None
            return a if c else b
        return c

    _LEVELS = [("||",), ("&&",), ("|",), ("^",), ("&",), ("==", "!="), ("<", "<=", ">", ">="), ("<<", ">>"),
               ("+", "-"), ("*", "/", "%")]

    def binary(self, level: int) -> int | None:
        if level == len(self._LEVELS):
            return self.unary()
        left = self.binary(level + 1)
        while self.peek() in self._LEVELS[level]:
            op = self.take()
            right = self.binary(level + 1)
            left = self._apply(op, left, right)
        return left

    @staticmethod
    def _apply(op: str, a: int | None, b: int | None) -> int | None:
        if op == "&&":
            if a == 0 or b == 0:
                return 0
            return None if a is None or b is None else 1
        if op == "||":
            if (a is not None and a != 0) or (b is not None and b != 0):
                return 1
            return None if a is None or b is None else 0
        if a is None or b is None:
            return None
        try:
            return int({"|": a | b, "^": a ^ b, "&": a & b, "==": a == b, "!=": a != b, "<": a < b, "<=": a <= b,
                        ">": a > b, ">=": a >= b, "<<": a << b if 0 <= b < 64 else 0, ">>": a >> b if 0 <= b < 64 else 0,
                        "+": a + b, "-": a - b, "*": a * b,
                        "/": a // b if b else 0, "%": a % b if b else 0}[op])
        except (ZeroDivisionError, OverflowError):
            return None

    def unary(self) -> int | None:
        tok = self.take()
        if tok == "!":
            v = self.unary()
            return None if v is None else int(not v)
        if tok == "-":
            v = self.unary()
            return None if v is None else -v
        if tok == "+":
            return self.unary()
        if tok == "~":
            v = self.unary()
            return None if v is None else ~v
        if tok == "(":
            v = self.ternary()
            if self.take() != ")":
                raise _Unknown(")")
            return v
        if tok == "defined":
            paren = self.peek() == "("
            if paren:
                self.take()
            name = self.take()
            if paren and self.take() != ")":
                raise _Unknown("defined(")
            v = self.values.get(name)
            return None if v is None else int(v is not False)
        if tok[0].isdigit():
            return int(tok, 0)
        if tok[0].isalpha() or tok[0] == "_":
            if self.peek() == "(":  # function-like macro / __has_include / __has_attribute
                raise _Unknown(tok)
            if tok in ("true", "false") and tok not in self.values:
                return int(tok == "true")
            return _macro_int(self.values.get(tok), self.values, self.depth)
        raise _Unknown(tok)


def evaluate_expr(expr: str, values: dict[str, Value], depth: int = 0) -> int | None:
    try:
        return _Parser(_tokens(expr), values, depth).parse()
    except _Unknown:
        return None


def _directive(part: str) -> tuple[str, str]:
    m = re.match(r"#\s*(ifdef|ifndef|if|elif|else)\b\s*(.*)$", part.strip())
    return (m.group(1), m.group(2).strip()) if m else ("if", part.strip())


def _clause(kind: str, rest: str, values: dict[str, Value]) -> int | None:
    if kind in ("ifdef", "ifndef"):
        name = rest.split()[0] if rest.split() else ""
        v = values.get(name)
        d = None if v is None else int(v is not False)
        return d if kind == "ifdef" or d is None else int(not d)
    if kind == "else":
        return 1
    return evaluate_expr(rest, values)


def evaluate_chain(chain: str, values: dict[str, Value]) -> bool | None:
    """One entry of `ingest.changes.conditional_stack`: `#if A / #elif B / #else` = the branch after the last ` / `
    is the active one: all earlier clauses false and the last one true."""
    parts = [_directive(p) for p in re.split(r"\s+/\s+(?=#)", chain)]
    result: bool | None = True
    for i, (kind, rest) in enumerate(parts):
        v = _clause(kind, rest, values)
        want_true = i == len(parts) - 1
        if v is None:
            result = None
            continue
        if bool(v) != want_true:
            return False
    return result


def evaluate(conditions: list[str], values: dict[str, Value]) -> bool | None:
    """All enclosing chains (outermost first): False if any is false, None if any is unknown, else True."""
    out: bool | None = True
    for c in conditions:
        r = evaluate_chain(c, values)
        if r is False:
            return False
        if r is None:
            out = None
    return out


def am_condition(conds: list[str], values: dict[str, Value]) -> bool | None:
    """Automake conditionals (`FEATURE_X`, `!FEATURE_X`) with values `AM:FEATURE_X` (True/False)."""
    out: bool | None = True
    for c in conds:
        neg = c.startswith("!")
        v = values.get("AM:" + c.lstrip("!"))
        if v is None or isinstance(v, str):
            out = None
            continue
        if bool(v) == neg:
            return False
    return out


# ---- per-variant knowledge ----------------------------------------------------------------------------------------
@dataclass
class VariantView:
    name: str
    values: dict[str, Value]  # global switch values (AM:*, --enable-*, macros from config.h / user)
    cdb: Any = None  # CompileDatabase of the variant (or None)
    cdb_files: set[Path] = field(default_factory=set)

    def macros_for(self, file: Path) -> dict[str, Value]:
        vals = dict(self.values)
        if self.cdb is not None:
            e = self.cdb.by_file.get(file)
            entries = [e] if e is not None else self.cdb.entries
            per: dict[str, set] = {}
            for ent in entries:
                for k, v in _cmdline_macros(ent.args).items():
                    per.setdefault(k, set()).add(v)
            for k, vs in per.items():
                if len(vs) == 1:
                    vals[k] = next(iter(vs))
                else:
                    vals.setdefault(k, None)
        return vals


def _cmdline_macros(args: tuple[str, ...]) -> dict[str, Value]:
    out: dict[str, Value] = {}
    it = iter(args)
    for a in it:
        if a in ("-D", "-U"):
            a = a + next(it, "")
        if a.startswith("-D") and len(a) > 2:
            name, _, val = a[2:].partition("=")
            out[name] = val if val else "1"
        elif a.startswith("-U") and len(a) > 2:
            out[a[2:]] = False
    return out


def load_views(repo: Path, profile: RunProfile) -> list[VariantView]:
    from tcadvisor.index.compile_db import CompileDatabase
    from tcadvisor.index.variants import build_values
    views = []
    for v in profile.variants:
        cdb = None
        if v.get("compile_db"):
            p = Path(v["compile_db"])
            p = p if p.is_absolute() else repo / p
            try:
                cdb = CompileDatabase.load(p.parent if p.name.endswith(".json") else p, repo, allow_stale=True)
            except Exception:  # noqa: BLE001 - a missing variant database only means less is provable
                cdb = None
        values = {**build_values(repo, v), **{k: x for k, x in (v.get("values") or {}).items() if x is not None}}
        views.append(VariantView(v["name"], values, cdb, set(cdb.by_file) if cdb else set()))
    return views


@dataclass
class Exclusion:
    variant: str
    reason: str  # source_not_in_product | conditional_dir | preprocessor | source_not_in_compile_db
    condition: str | None
    where: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"variant": self.variant, "reason": self.reason, "condition": self.condition, "where": self.where}


class LocationJudge:
    """`built(rel, line, view)` → (True|False|None, Exclusion|None), cached per file."""

    def __init__(self, repo: Path, model: Any, header_ext: set[str]):
        self.repo = repo
        self.model = model  # index.automake.BuildModel or None (CMake)
        self.header_ext = header_ext
        self._stacks: dict[str, dict[int, list[str]]] = {}

    def _stack(self, rel: str) -> dict[int, list[str]]:
        if rel not in self._stacks:
            from tcadvisor.ingest.changes import conditional_stack
            try:
                text = (self.repo / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            self._stacks[rel] = conditional_stack(text.splitlines())
        return self._stacks[rel]

    def file_built(self, rel: str, view: VariantView) -> tuple[bool | None, Exclusion | None]:
        path = (self.repo / rel).resolve()
        if path.suffix.lower() in self.header_ext:
            return None, None  # a header is built wherever a built TU includes it: never excluded by file
        if self.model is not None and path in self.model.source_conditions:
            alts = self.model.source_conditions[path]
            res = [am_condition(a, view.values) for a in alts]
            if any(r is True for r in res):
                return True, None
            if res and all(r is False for r in res):
                conds = " / ".join(" && ".join(a) for a in alts if a)
                where = self.model.defined_at.get(next(iter(self.model.targets.file_to_targets.get(path, [])), ""))
                return False, Exclusion(view.name, "source_not_in_product", f"if {conds}", where)
        if view.cdb is not None and view.cdb_files:
            if path in view.cdb_files:
                return True, None
            return False, Exclusion(view.name, "source_not_in_compile_db", None,
                                    f"{rel} is not compiled in this variant's compile database")
        return None, None

    def built(self, rel: str, line: int, view: VariantView) -> tuple[bool | None, Exclusion | None]:
        f, why = self.file_built(rel, view)
        if f is False:
            return False, why
        conds = self._stack(rel).get(line, [])
        if not conds:
            return (True if f is True or f is None else f), None
        r = evaluate(conds, view.macros_for((self.repo / rel).resolve()))
        if r is False:
            return False, Exclusion(view.name, "preprocessor", " && ".join(conds), f"{rel}:{line}")
        return r, None


def _locations(case: Any, root_lines: dict[str, list[tuple[str, int]]], graph: Any) -> list[tuple[str, int]]:
    """Where the impact of a case is built: the changed lines for a changed symbol (hop 0), else every call site /
    use from the case's symbol to the symbol it depends on (all of them, not only the one shown as evidence)."""
    from tcadvisor.models import ImpactEdge
    if case.hop_distance == 0 and case.node_id in root_lines:
        return root_lines[case.node_id]
    edges = [e for e in case.evidence if isinstance(e, ImpactEdge)]
    locs: list[tuple[str, int]] = []
    if graph is not None and case.node_id:
        for e in edges:
            qn = e.to_symbol.qualified_name
            ids = list(graph.by_name.get(qn, [])) + list(graph.by_name.get(qn.split("::")[-1], []))
            for t in dict.fromkeys(i for i in ids if graph.file_of(i) == e.to_symbol.file_path):
                locs += [(d.file, d.line) for d in graph.dependents.get(t, []) if d.dependent == case.node_id]
    if not locs:
        locs = [(e.file_path, e.line) for e in edges]
    if not locs:
        locs = [(e.file_path, e.line) for e in case.evidence if hasattr(e, "file_path")]
    return locs


def _all_out(lines: list[tuple[str, int]], views: list[VariantView], judge: LocationJudge
             ) -> tuple[bool, list[Exclusion]]:
    reasons: list[Exclusion] = []
    for v in views:
        for rel, line in lines:
            b, why = judge.built(rel, line, v)
            if b is not False:
                return False, []
            reasons.append(why)
    return bool(lines), reasons


def apply_profile(cases: list[Any], profile: RunProfile, views: list[VariantView], judge: LocationJudge,
                  root_lines: dict[str, list[tuple[str, int]]], graph: Any, changes: list[Any],
                  case_roots: dict[str, set[str]] | None = None
                  ) -> tuple[list[Any], list[dict[str, Any]], list[dict[str, Any]], list[Any]]:
    """(kept cases, not_built entries, not_built_changes, uncertainty flags). A case also moves when every changed
    root it is reached from is itself not built (its impact cannot reach the case in any selected variant)."""
    from tcadvisor.models import SymbolRef, UncertaintyFlag
    kept, moved, flags = [], [], []
    undecided: dict[str, list[str]] = {}
    root_out = {nid: _all_out(lines, views, judge) for nid, lines in root_lines.items()}
    for c in cases:
        roots = (case_roots or {}).get(c.node_id) or ({c.node_id} if c.node_id in root_lines else set())
        if c.hop_distance > 0 and roots and all(root_out.get(r, (False, []))[0] for r in roots):
            moved.append({"case": c.to_dict(), "excluded_by": [x.to_dict() for x in _dedupe(
                [w for r in sorted(roots) for w in root_out[r][1]])]})
            continue
        locs = _locations(c, root_lines, graph)
        reasons: list[Exclusion] = []
        all_out = bool(locs)
        for v in views:
            for rel, line in locs:
                b, why = judge.built(rel, line, v)
                if b is False:
                    reasons.append(why)
                    continue
                all_out = False
                if b is None:
                    conds = judge._stack(rel).get(line, [])
                    if conds:
                        undecided.setdefault(f"{rel}:{line}", []).append(v.name)
                break
            if not all_out:
                break
        if all_out:
            moved.append({"case": c.to_dict(), "excluded_by": [r.to_dict() for r in _dedupe(reasons)]})
        else:
            kept.append(c)
    for where, names in sorted(undecided.items()):
        rel, _, line = where.rpartition(":")
        conds = judge._stack(rel).get(int(line), [])
        flags.append(UncertaintyFlag(
            "build_config_incomplete_macro",
            f"{where} is guarded by `{' && '.join(conds)}`, which cannot be evaluated for variant(s) "
            f"{', '.join(sorted(set(names)))} (macro values unknown); the case is kept",
            SymbolRef(rel, "file", rel, int(line))))
    not_built_changes = []
    for ch in changes:
        out, reasons = root_out.get(ch.node_id) or _all_out([(ch.rel_path, ch.line)], views, judge)
        if out:
            not_built_changes.append({"path": ch.rel_path, "symbol": ch.name, "line": ch.line,
                                      "excluded_by": [r.to_dict() for r in _dedupe(reasons)]})
    return kept, moved, not_built_changes, flags


def _dedupe(reasons: list[Exclusion]) -> list[Exclusion]:
    seen, out = set(), []
    for r in reasons:
        k = (r.variant, r.reason, r.condition, r.where)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
