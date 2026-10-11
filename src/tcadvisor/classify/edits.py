"""Corner cases derived from the shape of an edit (spec 007 US1, research R1-R3).

A reviewer who reads "test boundary values" does not know which value; the edit says which one. This module
pairs the old and new lines of one changed symbol and recognises a few edit shapes — an operator or constant that
changed, a condition that disappeared, a return value that changed, statements that swapped order, a call or an
assignment that is no longer made — and words a concrete hint for each, quoting the real code. It also lists
input classes for the parameters used on changed lines. Pure text: deterministic, no parser, no repository access.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from tcadvisor.ingest.changes import strip_comments

_TOK = re.compile(r"""("(?:\\.|[^"\\])*"|0[xX][0-9a-fA-F']+[uUlL]*|\d[\d']*(?:\.\d+)?(?:[eE][+-]?\d+)?[uUlLfF]*|"""
                  r"""'(?:\\.|[^'\\])*'|[A-Za-z_]\w*|->|<<=|>>=|<=|>=|==|!=|&&|\|\||<<|>>|\+\+|--|[-+*/%&|^]=|::|\S)""")
_NUM = re.compile(r"^(0[xX][0-9a-fA-F']+|\d[\d']*(?:\.\d+)?(?:[eE][+-]?\d+)?)[uUlLfF]*$")
_IDENT = re.compile(r"^[A-Za-z_]\w*$")
REL_OPS = {"<", "<=", ">", ">=", "==", "!="}
_COND_HEAD = re.compile(r"\b(if|while)\s*\(")
_ASSERT = re.compile(r"\b(assert|DCHECK|CHECK|ASSERT)(?:_(?:EQ|NE|LT|LE|GT|GE))?\s*\(")
_KEYWORDS = {"if", "while", "for", "switch", "return", "sizeof", "else", "case", "do", "new", "delete", "throw",
             "static_cast", "reinterpret_cast", "const_cast", "dynamic_cast", "catch", "alignof", "decltype"}
_DECL_START = re.compile(r"^\s*(?:const\s+|static\s+|constexpr\s+|auto\b|unsigned\b|signed\b|int\b|bool\b|char\b|"
                         r"long\b|short\b|double\b|float\b|size_t\b|u?int\d+_t\b|std::)")
_ERRORISH = re.compile(r"(?i)corrupt|error|fail|invalid|false|nullptr|null\b|-1\b|notfound|not_found|bad|abort|"
                       r"E[A-Z]{2,}")
MAX_HINTS = 8


@dataclass
class EditShape:
    kind: str  # operator_flip | logical_flip | negation_flip | constant_change | value_change | removed_guard |
    #            return_change | reorder | removed_call | removed_assignment | removed_term | lock_added |
    #            lock_removed | removed_assert
    old: str
    new: str
    hint: str


MAX_LINE = 400  # longer lines (data tables, literals) are cut: keeps every regex linear in practice


def norm(line: str) -> str:
    return " ".join(strip_comments(line).split())[:MAX_LINE]


def tokens(text: str) -> list[str]:
    return _TOK.findall(text)


def _lines(body: list[str]) -> list[str]:
    out = [norm(x) for x in body]
    return [x for x in out if x and x not in ("{", "}", "};")]


_STOP = {"&&", "||", ",", ";", "?", ":", "=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", "{",
         "}", "!"} | REL_OPS


def _join(toks: list[str]) -> str:
    out = ""
    for t in toks:
        tight = t in (".", "->", "::", "(", ")", "[", "]") or out in ("*", "&") or (out[-1:] in ("(", "[", ".", ">", ":") and
                                                               (out.endswith(("->", "::", "(", "[", ".")))) or not out
        out += t if tight else " " + t
    return out.strip()


def _operand(tok: list[str], i: int, step: int) -> str:
    """Expression next to the comparison at ``tok[i]``: everything that binds tighter (arithmetic, member access,
    calls, unary ``*`` / ``&``) up to a logical operator, comma, keyword or unmatched bracket."""
    out: list[str] = []
    j, depth = i + step, 0
    opener, closer = (("(", "["), (")", "]")) if step > 0 else ((")", "]"), ("(", "["))
    while 0 <= j < len(tok):
        t = tok[j]
        if t in opener:
            depth += 1
        elif t in closer:
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (t in _STOP or t in _KEYWORDS):
            break
        out.append(t)
        j += step
    if step < 0:
        out.reverse()
    return _join(out) or "?"


def _cond_exprs(line: str) -> list[str]:
    """Condition texts of ``if (...)`` / ``while (...)`` / assert-like calls / ternaries on one line."""
    out = []
    code = norm(line)
    for rx in (_COND_HEAD, _ASSERT):
        for m in rx.finditer(code):
            i, depth = m.end(), 1
            while i < len(code) and depth:
                depth += {"(": 1, ")": -1}.get(code[i], 0)
                i += 1
            if depth:
                continue  # condition continues on the next line / unbalanced text: no reliable expression
            expr = code[m.end():i - 1].strip()
            cm = re.match(r"(?:\w*CHECK|ASSERT|EXPECT)_(EQ|NE|LT|LE|GT|GE)$", m.group(1) + code[m.start():m.end()]
                          .split("(")[0][len(m.group(1)):])
            if cm and "," in expr:
                a_, b_ = expr.split(",", 1)
                expr = f"{a_.strip()} {dict(EQ='==', NE='!=', LT='<', LE='<=', GT='>', GE='>=')[cm.group(1)]} {b_.strip()}"
            out.append(expr)
    if "?" in code and ":" in code and not out:
        m = re.search(r"(?:=|return|\()\s*([^?=;]+?)\s*\?", code)
        if m:
            out.append(m.group(1).strip())
    return [c for c in out if c]


def conjuncts(cond: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    i = 0
    while i < len(cond):
        ch = cond[i]
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth == 0 and cond[i:i + 2] in ("&&", "||"):
            parts.append(cur.strip())
            cur = ""
            i += 2
            continue
        cur += ch
        i += 1
    parts.append(cur.strip())
    out = []
    for p in parts:
        while p.startswith("(") and p.endswith(")") and p.count("(") == 1:
            p = p[1:-1].strip()
        if p:
            out.append(p)
    return out


def _idents(text: str) -> set[str]:
    return {t for t in tokens(text) if _IDENT.match(t) and t not in _KEYWORDS and t not in ("true", "false")}


def _negate(c: str) -> str:
    m = re.match(r"^(.+?)\s*(<=|>=|<|>|==|!=)\s*(.+)$", c)
    if m:
        neg = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}[m.group(2)]
        return f"{m.group(1)} {neg} {m.group(3)}"
    m = re.match(r"^!\s*\(?(.+?)\)?$", c)
    return m.group(1) if m else f"!{c}"


def _input_making(c: str, value: bool) -> str:
    """Words for the input that makes condition ``c`` evaluate to ``value``."""
    c = c.strip()
    if not value:
        c = _negate(c)
    m = re.match(r"^(.+?)\s*==\s*(nullptr|NULL|0)$", c) or re.match(r"^(nullptr|NULL)\s*==\s*(.+)$", c)
    if m:
        var = m.group(1) if m.group(2) in ("nullptr", "NULL", "0") else m.group(2)
        return f"call with `{var}` == nullptr / 0"
    m = re.match(r"^!\s*\(?([\w.\->:]+(?:\(\))?)\)?$", c)
    if m:
        return f"make `{m.group(1)}` false / null / zero"
    if re.match(r"^[\w.\->:]+$", c):
        return f"make `{c}` true / non-null"
    if re.search(r"(<=|>=|<|>)", c):
        return f"make `{c}` hold (including the equality edge)"
    return f"make `{c}` hold"


def _reject_input(cond: str, early_exit: bool = False) -> str:
    """The input a removed condition used to keep away from the code that now runs unconditionally: for a wrapping
    ``if (c) { code }`` that is ``c`` false, for an early exit ``if (c) return;`` it is ``c`` true."""
    return _input_making(cond, early_exit)


def _num_vals(lit: str) -> list[str]:
    raw = re.sub(r"[uUlLfF]+$", "", lit).replace("'", "")
    try:
        v = int(raw, 0)
    except ValueError:
        return [f"just below {lit}", lit, f"just above {lit}"]
    return [str(x) for x in sorted({v - 1, v, v + 1})]


def _op_hint(a: str, op_old: str, op_new: str, b: str, line: str) -> str:
    eq = f"`{a} == {b}`"
    if {op_old, op_new} in ({"<", "<="}, {">", ">="}):
        now = "now also holds" if op_new in ("<=", ">=") else "no longer holds"
        return (f"`{a} {op_new} {b}` {now} when {eq} (was `{op_old}`): test {a} == {b}, and one step below and "
                f"above (`{line[:90]}`)")
    if {op_old, op_new} == {"==", "!="}:
        return f"Condition inverted `{a} {op_old} {b}` → `{a} {op_new} {b}`: test {eq} and `{a} != {b}` (both branches swap)"
    return (f"Comparison changed `{a} {op_old} {b}` → `{a} {op_new} {b}`: test `{a}` below, equal to and above "
            f"`{b}`")


def _pair(old: list[str], new: list[str]) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """(paired old/new lines, old-only lines, new-only lines) — research R1."""
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    pairs, rem, add = [], [], []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            continue
        o, n = old[a1:a2], new[b1:b2]
        if op == "replace" and len(o) * len(n) > 400:  # large rewrite: pair by position, no fuzzy search
            pairs += list(zip(o, n))
            rem += o[len(n):]
            add += n[len(o):]
        elif op == "replace":
            used: set[int] = set()
            for x in o:
                best, bi = 0.0, -1
                for k, y in enumerate(n):
                    if k in used:
                        continue
                    r = difflib.SequenceMatcher(a=tokens(x), b=tokens(y), autojunk=False).ratio()
                    if r > best:
                        best, bi = r, k
                if bi >= 0 and (best >= 0.5 or (len(o) == len(n) == 1 and best >= 0.2)):
                    used.add(bi)
                    pairs.append((x, n[bi]))
                else:
                    rem.append(x)
            add += [y for k, y in enumerate(n) if k not in used]
        elif op == "delete":
            rem += o
        else:
            add += n
    return pairs, rem, add


def _pair_shapes(o: str, n: str, out: list[EditShape]) -> None:
    to, tn = tokens(o), tokens(n)
    if len(to) == len(tn):
        diff = [i for i, (a, b) in enumerate(zip(to, tn)) if a != b]
        if diff and all(to[i] in REL_OPS and tn[i] in REL_OPS for i in diff):
            for i in diff[:2]:
                out.append(EditShape("operator_flip", o, n, _op_hint(_operand(tn, i, -1), to[i], tn[i],
                                                                     _operand(tn, i, 1), n)))
            return
        if diff and all(to[i] in ("&&", "||") and tn[i] in ("&&", "||") for i in diff):
            out.append(EditShape("logical_flip", o, n,
                                 f"`{to[diff[0]]}` became `{tn[diff[0]]}` in `{n[:90]}`: test each operand true "
                                 "alone and false alone"))
            return
        if diff and all(_NUM.match(to[i]) and _NUM.match(tn[i]) for i in diff):
            for i in diff[:2]:
                vals = list(dict.fromkeys(_num_vals(tn[i]) + _num_vals(to[i])))
                out.append(EditShape("constant_change", o, n,
                                     f"Constant changed `{to[i]}` → `{tn[i]}` in `{n[:80]}`: test values "
                                     f"{', '.join(vals)} (new and old limit)"))
            return
    if to and tn and to[0] == "return" and tn[0] == "return" and to != tn:
        ov, nv = o[len("return"):].strip().rstrip(";").strip(), n[len("return"):].strip().rstrip(";").strip()
        situation = ("the error / invalid input that used to produce it (malformed, missing, out of range)"
                     if _ERRORISH.search(ov) and not _ERRORISH.search(nv) else "the input that reaches this return")
        out.append(EditShape("return_change", o, n,
                             f"Return value changed `{ov[:70]}` → `{nv[:70]}`: drive {situation} and check every "
                             f"caller handles the new error result / value"))
        return
    sm = difflib.SequenceMatcher(a=to, b=tn, autojunk=False)
    ops = [x for x in sm.get_opcodes() if x[0] != "equal"]
    if len(ops) == 1 and ops[0][0] in ("insert", "delete"):
        _op, a1, a2, b1, b2 = ops[0]
        piece = to[a1:a2] if _op == "delete" else tn[b1:b2]
        if piece == ["!"]:
            out.append(EditShape("negation_flip", o, n, f"Negation {'removed' if _op == 'delete' else 'added'} in "
                                 f"`{n[:90]}`: the branch now runs for the opposite inputs — test both"))
            return
    # value assigned / initialised changed: `name = A;` -> `name = B;`
    mo = re.match(r"^(.*?\b([A-Za-z_]\w*))\s*(?:=|\{)\s*([^=].*?)[;}]*$", o)
    mn = re.match(r"^(.*?\b([A-Za-z_]\w*))\s*(?:=|\{)\s*([^=].*?)[;}]*$", n)
    if mo and mn and mo.group(2) == mn.group(2) and mo.group(3).strip() != mn.group(3).strip() \
            and not _COND_HEAD.search(o) and mo.group(2) not in _KEYWORDS:
        name = mn.group(2)
        out.append(EditShape("value_change", o, n,
                             f"`{name}` now gets `{mn.group(3).strip()[:60]}` (was `{mo.group(3).strip()[:60]}`): test "
                             f"code that relies on the old value of `{name}` (limits, sizes, timeouts, flags)"))
    # removed term in an expression (dropped call / operand)
    for op, a1, a2, _b1, _b2 in ops:
        if op == "delete":
            piece = to[a1:a2]
            calls = [piece[k] for k in range(len(piece) - 1) if _IDENT.match(piece[k]) and piece[k + 1] == "("
                     and piece[k] not in _KEYWORDS]
            operand = any(t in ("+", "-", "*", "/", "%", "<<", ">>", "|", "&") for t in piece) and \
                any(_IDENT.match(t) or _NUM.match(t) for t in piece)
            if calls or operand:
                term = " ".join(piece).replace(" ( ", "(").replace(" )", ")").strip(" +-*/,")
                out.append(EditShape("removed_term", o, n,
                                     f"`{term[:60]}` was removed from `{n[:80]}`: the computed value changes whenever "
                                     "that term is non-zero — check every reader of the result (sizes, offsets, "
                                     "decoding / round trip)"))
                break


_EXIT_KW = re.compile(r"\b(return|continue|break|throw|goto)\b")


def _root_ids(text: str) -> set[str]:
    """Identifiers that are not member / method names (``x.size()`` -> {x}): what a condition is *about*."""
    toks = tokens(text)
    return {t for k, t in enumerate(toks) if _IDENT.match(t) and t not in _KEYWORDS and t not in
            ("true", "false", "nullptr", "NULL") and not (k and toks[k - 1] in (".", "->"))}


def _null_var(c: str) -> str | None:
    c = c.strip()
    m = (re.match(r"^!?\s*([A-Za-z_][\w.\->]*)$", c) or re.match(r"^([A-Za-z_][\w.\->]*)\s*[!=]=\s*(?:nullptr|NULL)$", c)
         or re.match(r"^(?:nullptr|NULL)\s*[!=]=\s*([A-Za-z_][\w.\->]*)$", c))
    return m.group(1) if m else None


def _removed_guards(pairs: list[tuple[str, str]], rem: list[str], new_conds: list[str], old: list[str],
                    out: list[EditShape]) -> None:
    new_roots = [_root_ids(c) for c in new_conds]
    candidates = [(o, n) for o, n in pairs] + [(o, None) for o in rem]
    for o, n in candidates:
        is_assert = bool(_ASSERT.search(o)) and not _COND_HEAD.search(o)
        oc = [c for e in _cond_exprs(o) for c in conjuncts(e)]
        if not oc:
            continue
        nc = {norm(c) for e in (_cond_exprs(n) if n else []) for c in conjuncts(e)}
        k = old.index(o) if o in old else -1
        nxt = old[k + 1] if 0 <= k < len(old) - 1 else ""
        early = bool(_EXIT_KW.search(o.split(")", 1)[-1] if ")" in o else "")) or bool(_EXIT_KW.match(nxt)) \
            or (nxt == "{" and k + 2 < len(old) and bool(_EXIT_KW.match(old[k + 2])))
        for c in oc:
            if norm(c) in nc:
                continue
            roots = _root_ids(c)
            nv = _null_var(c)
            if nv is not None:  # a null check is only kept by another null check of the same pointer
                if any(_null_var(x) == nv or re.search(rf"\w\s*\([^()]*(?<![\w.>]){re.escape(nv)}\b(?!\s*(?:\.|->))", x)
                       for x in new_conds):
                    continue  # still null-checked, or handed to a helper that checks it (`IsValid(p)`)
            # the same state is still checked (operator tweak, `size() > 0` -> `!empty()`, moved into a helper)
            elif roots and any(roots <= r for r in new_roots):
                continue
            if is_assert:
                out.append(EditShape("removed_assert", o, n or "",
                                     f"Removed check `{c[:80]}`: a violation is no longer detected here — "
                                     f"{_input_making(c, False)} and check what happens downstream"))
            elif early:
                out.append(EditShape("removed_guard", o, n or "",
                                     f"Removed early exit on `{c[:80]}`: the code after it now also runs when it "
                                     f"holds — {_reject_input(c, True)}"))
            else:
                out.append(EditShape("removed_guard", o, n or "",
                                     f"Removed condition `{c[:80]}`: the code it protected now also runs when it is "
                                     f"false — {_reject_input(c)}"))


def _reorders(old: list[str], new: list[str], rem: list[str], add: list[str], out: list[EditShape]) -> set[str]:
    moved = [x for x in dict.fromkeys(rem) if x in add]
    done: set[str] = set()
    oi = {x: i for i, x in reversed(list(enumerate(old)))}
    ni = {x: i for i, x in reversed(list(enumerate(new)))}
    for m in moved:
        if m not in oi or m not in ni:
            continue
        crossed = [x for x in old if x != m and x in ni and
                   (oi[x] < oi[m]) != (ni[x] < ni[m])]
        if not crossed:
            continue
        x = min(crossed, key=lambda y: abs(oi[y] - oi[m]))
        first, later = (m, x) if ni[m] < ni[x] else (x, m)
        out.append(EditShape("reorder", m, x,
                             f"Order changed: `{first[:70]}` now runs before `{later[:70]}` — the later statement "
                             "must not use what the earlier one released, reset, moved or overwrote (use after "
                             "free / stale value)"))
        done.add(m)
        if len(done) >= 2:
            break
    return done


_LOCK = re.compile(r"\b(?:\w*Lock(?:er|Guard)?|lock_guard|unique_lock|scoped_lock|shared_lock)\b(?:<[^>]*>)?\s+\w+\s*"
                   r"[({]\s*&?\s*([\w.\->]+)|([\w.\->]+)\s*(?:\.|->)\s*(?:lock|Lock|try_lock)\s*\(\s*\)|"
                   r"pthread_mutex_lock\s*\(\s*&?\s*([\w.\->]+)")


def lock_name(line: str) -> str | None:
    m = _LOCK.search(norm(line))
    return next((g for g in m.groups() if g), None) if m else None


def _removed_statements(rem: list[str], skip: set[str], add: list[str], out: list[EditShape]) -> None:
    added_text = " ".join(add)
    for a in add:
        lk = lock_name(a)
        if lk and not any(lock_name(o) == lk for o in rem):
            out.append(EditShape("lock_added", "", a,
                                 f"Lock on `{lk}` added (`{a[:60]}`): callers already holding it, callbacks invoked "
                                 "under it and lock order with other locks (deadlock)"))
    n = 0
    for o in rem:
        lk = lock_name(o)
        if lk and o not in skip:
            if not any(lock_name(a) == lk for a in add):
                out.append(EditShape("lock_removed", o, "",
                                     f"Lock on `{lk}` removed (`{o[:60]}`): run this function concurrently with the "
                                     f"other users of the data `{lk}` protected (data race, torn reads)"))
            continue
        if o in skip or n >= 3 or _cond_exprs(o) or o.startswith(("return", "}", "else", "case", "#")):
            continue
        mo = re.match(r"^(?:this->)?([A-Za-z_][\w.\->\[\]]*)\s*(?:[+\-*/%|&^]|<<|>>)?=(?!=)\s*(.+?);?$", o)
        if mo and not _DECL_START.match(o):
            target = mo.group(1)
            if not re.search(rf"\b{re.escape(target)}\s*(?:[+\-*/%|&^]|<<|>>)?=(?!=)", added_text):
                out.append(EditShape("removed_assignment", o, "",
                                     f"`{o[:80]}` is no longer done here: readers of `{target}` must not rely on it "
                                     "being updated on this path"))
                n += 1
            continue
        m = re.search(r"([A-Za-z_][\w:]*(?:(?:\.|->)[A-Za-z_]\w*)*)\s*\(", o)
        if m and m.group(1).split("::")[-1].split(".")[-1].split("->")[-1] not in _KEYWORDS:
            name = m.group(1)
            if not re.search(rf"\b{re.escape(name.split('::')[-1].split('->')[-1].split('.')[-1])}\s*\(", added_text):
                out.append(EditShape("removed_call", o, "",
                                     f"`{name}(…)` is no longer called here (`{o[:70]}`): whatever depended on its "
                                     "effect (state, counters, notifications, cleanup) must still be correct"))
                n += 1


def analyse(old_body: list[str], new_body: list[str], removed_lines: list[str] | None = None,
            added_lines: list[str] | None = None) -> list[EditShape]:
    """Edit shapes of one changed symbol. Bodies give order and context; without them (textual changes) the
    changed lines alone are compared."""
    old = _lines(old_body) if old_body else _lines(removed_lines or [])
    new = _lines(new_body) if new_body else _lines(added_lines or [])
    if len(old) + len(new) > 1500 and (removed_lines or added_lines):  # huge symbol: the changed lines only
        old, new = _lines(removed_lines or []), _lines(added_lines or [])
    if not old and not new:
        return []
    pairs, rem, add = _pair(old, new)
    out: list[EditShape] = []
    moved = _reorders(old, new, rem, add, out)
    rem = [x for x in rem if x not in moved]
    add = [x for x in add if x not in moved]
    for o, n in pairs:
        _pair_shapes(o, n, out)
    new_conds = [c for x in new for e in _cond_exprs(x) for c in conjuncts(e)]
    _removed_guards(pairs, rem, new_conds, old, out)
    _removed_statements(rem, moved, add, out)
    order = ["removed_guard", "lock_removed", "removed_assert", "operator_flip", "constant_change", "return_change", "reorder", "logical_flip",
             "negation_flip", "lock_added", "value_change", "removed_term", "removed_call",
             "removed_assignment"]
    out.sort(key=lambda s: order.index(s.kind))
    seen: set[str] = set()
    uniq = []
    for s in out:
        if s.hint not in seen:
            seen.add(s.hint)
            uniq.append(s)
    return uniq[:MAX_HINTS]


def shapes_of(ch) -> list[EditShape]:
    """``analyse`` for a SymbolChange, computed once (rules and patterns both need it)."""
    cached = getattr(ch, "_edit_shapes", None)
    if cached is None:
        cached = analyse(ch.old_body, ch.new_body, ch.removed_lines, ch.added_lines)
        ch._edit_shapes = cached
    return cached


# ---- parameter input classes (research R3) ---------------------------------------------------------------
_CONTAINER = re.compile(r"\b(string|string_view|Slice|vector|span|map|unordered_map|set|unordered_set|list|deque|"
                        r"array|QString|QByteArray|QList|QVector|basic_string|buffer|Buffer)\b")


def parameters(decl: list[str]) -> list[tuple[str, str]]:
    """(type text, name) of each parameter of a function declaration token list."""
    if "(" not in decl:
        return []
    i = decl.index("(")
    if i > 0 and decl[i - 1] == "operator" and decl[i + 1:i + 3] == [")", "("]:
        i += 2  # operator()(...)
    elif decl[:1] == ["decltype"] or (i > 0 and decl[i - 1] == "decltype"):
        depth = 0  # skip the decltype(...) of the return type
        for k in range(i, len(decl)):
            depth += {"(": 1, ")": -1}.get(decl[k], 0)
            if depth == 0:
                i = decl.index("(", k + 1) if "(" in decl[k + 1:] else i
                break
    depth, params, cur = 0, [], []
    for t in decl[i + 1:]:
        if t in ("(", "[", "{", "<"):
            depth += 1
        elif t in (")", "]", "}", ">"):
            if depth == 0:
                break
            depth -= 1
        elif t == ">>":
            depth -= 2
        if t == "," and depth == 0:
            params.append(cur)
            cur = []
        else:
            cur.append(t)
    params.append(cur)
    out = []
    for p in params:
        if "=" in p:
            p = p[:p.index("=")]
        if "(" in p:
            continue  # function pointer / callable parameter
        ids = [k for k, t in enumerate(p) if _IDENT.match(t)]
        if len(ids) < 2:
            continue
        name = p[ids[-1]]
        out.append((" ".join(p[:ids[-1]]), name))
    return out


def _pretty(typ: str) -> str:
    return re.sub(r"\s*(::|<|>|\*|&|,)\s*", lambda m: m.group(1) + (" " if m.group(1) == "," else ""), typ).strip()


def input_classes(decl: list[str], changed_lines: list[str], limit: int = 4) -> list[str]:
    text = " ".join(strip_comments(x) for x in changed_lines)
    out = []
    for typ, name in parameters(decl):
        if not re.search(rf"\b{re.escape(name)}\b", text):
            continue
        top = re.sub(r"<[^<>]*>", "", re.sub(r"<[^<>]*>", "", typ))
        if re.search(r"\b(unique_ptr|shared_ptr|weak_ptr)\b", typ) or ("*" in top and "char" not in top):
            cls = "nullptr"
        elif "char" in top and "*" in top:
            cls = "nullptr, empty string, very long string"
        elif _CONTAINER.search(typ):
            cls = "empty, one element, very large"
        elif re.search(r"\bbool\b", typ):
            cls = "true and false"
        elif re.search(r"\b(unsigned|size_t|uint\d*_t|uint)\b", typ):
            cls = "0, 1 and the maximum value (wrap-around)"
        elif re.search(r"\b(int|long|short|int\d+_t|ssize_t|ptrdiff_t)\b", typ):
            cls = "negative, 0 and the maximum value"
        elif re.search(r"\b(float|double)\b", typ):
            cls = "0, negative, very large and NaN"
        else:
            continue
        out.append(f"Input `{name}` ({_pretty(typ)[:40]}): {cls}")
        if len(out) >= limit:
            break
    return out
