"""Lesson-learned patterns: "the change was right, but something else broke" (spec 006 US4, research R4).

Each detector reads the diff and the code (git, libclang-free text scans bounded per root) and returns cases
whose evidence is the *other* code a reviewer must look at:

- ``symmetric_counterpart``  encode ↔ decode, open ↔ close, … of a changed function
- ``same_code_elsewhere``    other functions containing a line the change removed or rewrote
- ``new_enum_value``         switch / case sites over an enum that gained enumerators
- ``return_meaning``         callers deciding on a result that can now take a new constant value
- ``shared_state``           readers of a member / global the change now writes
- ``new_early_exit``         an added return / throw / break in the middle of a changed function
- ``config_reader``          other readers of a setting / flag the change reads

Spec 007 (lost side effects, "fixed here, broke there"; the readers are neither callers nor callees):

- ``removed_write``          readers of a member / global the change no longer writes (or writes differently)
- ``setter_readers``         callers of the getter paired with a setter call the change removed
- ``lock_coupling``          other accessors of the members used under a lock the change added or removed
- ``changed_default``        readers of a field / constant whose initial value changed
- ``class_consumer``         same-class methods reading members a modified method writes
- ``conditional_write``      (spec 008) readers of state written under a condition the edit changed
- ``guard_removed_callee``   functions called under a condition the change removed or weakened: they are now
                             reached in states the condition used to exclude

Deterministic; every case points to concrete code. Team lessons (``lessons.json``) are matched afterwards.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tcadvisor.ingest.changes import is_test_path, strip_comments, textual_functions
from tcadvisor.models import SymbolRef, TestCaseCandidate

PAIRS = [("encode", "decode"), ("serialize", "deserialize"), ("pack", "unpack"), ("marshal", "unmarshal"),
         ("open", "close"), ("lock", "unlock"), ("acquire", "release"), ("register", "unregister"),
         ("subscribe", "unsubscribe"), ("start", "stop"), ("init", "deinit"), ("connect", "disconnect"),
         ("send", "receive"), ("read", "write"), ("save", "load"), ("push", "pop"), ("add", "remove"),
         ("create", "destroy"), ("attach", "detach"), ("enable", "disable"), ("alloc", "free"),
         ("compress", "decompress"), ("encrypt", "decrypt"), ("begin", "end"), ("enter", "leave"),
         ("insert", "erase"), ("put", "get"), ("set", "get"), ("to", "from")]
CPP_GLOBS = ["*.c", "*.cc", "*.cpp", "*.cxx", "*.h", "*.hh", "*.hpp", "*.hxx", "*.inl", "*.ipp"]
MAX_PER_ROOT = 8
_TOKEN = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+|_")
_EXIT = re.compile(r"^\s*(?:}\s*)?(?:else\s+)?(?:if\s*\(.*\)\s*)?(return\b[^;]*;|throw\b|break\s*;|goto\s+\w+|co_return\b)")
_ACQUIRE = re.compile(r"\b(lock|lock_guard|unique_lock|scoped_lock|mutex|new|malloc|calloc|fopen|open|socket|acquire|"
                      r"begin\w*|start\w*|alloc\w*|create\w*|retain|ref)\b")
_MEMBER_W = re.compile(r"(?:this->|\b)((?:m_)?[A-Za-z]\w*_|m_\w+|m[A-Z]\w*|g_\w+|s_\w+)\s*(?:\[[^\]]*\]\s*)?"
                       r"([+\-*/%|&^]|<<|>>)?=(?!=)")
_SETTING = [re.compile(p) for p in (
    r"\b(FLAGS_\w+)", r"\bget_?[Cc]onfig\w*\s*\(\s*\"?([\w.\-]+)", r"\b(?:\w*[Cc]onfig\w*|\w*[Oo]ptions?\w*|"
    r"\w*[Ss]ettings?\w*|cfg|conf|opts)\s*(?:\.|->|::)\s*(?:get_?)?(\w+)", r"\b(is_\w+_enabled)\s*\(",
    r"\b(\w+_enabled_?)\b", r"\bgetenv\s*\(\s*\"(\w+)\"")]
_CONST = re.compile(r"^(-?\d[\w.']*|true|false|nullptr|NULL|k[A-Z]\w*|[A-Z][A-Z0-9_]{2,}|[\w:]*::[A-Za-z_]\w*|"
                    r"E[A-Z]+|-?E\w+)$")


GREP_BUDGET = [40]  # git grep calls per analysis (constitution V); reset by detect()


def _git_grep(repo: Path, rev: str | None, args: list[str], limit: int = 200) -> list[tuple[str, int, str]]:
    if GREP_BUDGET[0] <= 0:
        return []
    GREP_BUDGET[0] -= 1
    cmd = ["git", "-C", str(repo), "grep", "-n", "-I", *args]
    if rev:
        cmd.append(rev)
    cmd += ["--", *CPP_GLOBS]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    out = []
    for raw in res.stdout.splitlines()[:limit]:
        if rev and raw.startswith(rev + ":"):
            raw = raw[len(rev) + 1:]
        parts = raw.split(":", 2)
        if len(parts) == 3 and parts[1].isdigit():
            out.append((parts[0], int(parts[1]), parts[2]))
    return out


class _Files:
    def __init__(self, repo: Path, rev: str | None):
        self.repo, self.rev, self.cache = repo, rev, {}
        self.via: dict[tuple[str, str, int], str] = {}  # reader -> accessor it was reached through (spec 008)
        self.accessors: set[tuple[str, str]] = set()  # (qualified name, file) of readers that are trivial accessors

    def lines(self, rel: str) -> list[str]:
        if rel not in self.cache:
            text = None
            if self.rev:
                r = subprocess.run(["git", "-C", str(self.repo), "show", f"{self.rev}:{rel}"], capture_output=True,
                                   text=True, errors="replace")
                text = r.stdout if r.returncode == 0 else None
            if text is None:
                try:
                    text = (self.repo / rel).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
            lines = text.splitlines()
            self.cache[rel] = (lines, textual_functions(lines))
        return self.cache[rel][0]

    def function_at(self, rel: str, line: int) -> SymbolRef | None:
        self.lines(rel)
        fns = [f for f in self.cache[rel][1] if f[1] <= line <= f[2]]
        if not fns:
            return None
        name, a, _b = min(fns, key=lambda f: f[2] - f[1])
        return SymbolRef(name, "function", rel, a)

    def body(self, ref: SymbolRef) -> list[tuple[int, str]]:
        lines = self.lines(ref.file_path)
        fns = [f for f in self.cache[ref.file_path][1] if f[1] <= ref.line <= f[2]]
        if not fns:
            return []
        _n, a, b = min(fns, key=lambda f: f[2] - f[1])
        return [(i, lines[i - 1]) for i in range(a, b + 1)]


def _short(name: str) -> str:
    return name.split("::")[-1].split("<")[0]


def _same(a: SymbolRef, b: SymbolRef) -> bool:
    return _short(a.qualified_name) == _short(b.qualified_name) and a.file_path == b.file_path


def _case(ev: SymbolRef, root_id: str, pattern: str, desc: str, act: str, hints: list[str], targets,
          group: str = "logic", path=None) -> TestCaseCandidate:
    from tcadvisor.classify.cases import priority
    return TestCaseCandidate(id="", description=desc, activation_condition=act, evidence=[ev],
                             priority=priority(1, group, pattern), risk_group=group,
                             related_cmake_targets=sorted(targets(ev.file_path)) or ["(no CMake target owns this file)"],
                             node_id=root_id, sub_reason=pattern, hop_distance=1, pattern=pattern, path=path,
                             hints=hints)


def counterpart_names(short: str) -> list[str]:
    toks = [t for t in _TOKEN.findall(short)]
    out = []
    for i, t in enumerate(toks):
        for a, b in PAIRS:
            for x, y in ((a, b), (b, a)):
                if t.lower() == x and not (x in ("to", "from", "get", "set", "put") and len(toks) < 2):
                    rep = y.capitalize() if t[0].isupper() else (y.upper() if t.isupper() else y)
                    out.append("".join(toks[:i] + [rep] + toks[i + 1:]))
    return list(dict.fromkeys(o for o in out if o != short))


def detect(repo: Path, rev: str | None, changes: list, roots: dict[str, SymbolRef], graph,
           targets) -> list[TestCaseCandidate]:
    files = _Files(repo, rev)
    GREP_BUDGET[0] = 40
    root_names = {_short(r.qualified_name) for r in roots.values()}
    out: list[TestCaseCandidate] = []
    for ch in changes:
        if ch.node_id not in roots or ch.is_test_code or ch.is_log_only:
            continue
        root = roots[ch.node_id]
        rn = f"`{root.qualified_name}`"
        found: list[TestCaseCandidate] = []
        added = [strip_comments(x) for x in ch.added_lines]
        removed = [strip_comments(x) for x in ch.removed_lines]

        if ch.kind in ("function", "method"):
            # symmetric counterpart
            for cand in counterpart_names(_short(root.qualified_name)):
                if cand in root_names:
                    continue  # changed in the same commit: reviewed with it
                scope = root.qualified_name.rsplit("::", 1)[0] if "::" in root.qualified_name else ""
                usrs = graph.by_name.get(f"{scope}::{cand}" if scope else cand, []) or [
                    u for n, us in graph.by_name.items() if n == cand or n.endswith("::" + cand) for u in us]
                refs = [graph.symbol_ref(u) for u in usrs]
                refs = [r for r in refs if r is not None and r.kind in ("function", "method")]
                if not refs:  # lite index / provider mode: same file or its header / source twin
                    for f in dict.fromkeys([root.file_path] + [h for h in (str(Path(root.file_path).with_suffix(x))
                                                                           for x in (".h", ".hpp", ".cpp", ".cc"))
                                                               if (repo / h).is_file()]):
                        files.lines(f)
                        refs += [SymbolRef(n, "function", f, a) for n, a, _b in files.cache[f][1]
                                 if _short(n) == cand]
                refs = sorted(refs, key=lambda r: (not r.qualified_name.startswith(scope + "::") if scope else 0,
                                                   r.file_path != root.file_path, r.file_path, r.line))[:1]
                for r in refs:
                    found.append(_case(r, ch.node_id, "symmetric_counterpart",
                                       f"`{r.qualified_name}` is the counterpart of the changed {rn}: check both sides "
                                       "still agree", f"Changed {rn}; counterpart by name", [
                                           f"Round trip: data produced by {rn} is accepted by `{r.qualified_name}` "
                                           "(and the reverse), including boundary and error values",
                                           "Data written by the old version is still handled (compatibility)",
                                           "Error / partial paths are symmetric (what one side allocates, locks or "
                                           "registers, the other releases)"], targets))

            # same code elsewhere
            seen_lines = 0
            for ln in removed:
                text = ln.strip()
                if len(re.sub(r"\s", "", text)) < 25 or not re.search(r"[(=<>]", text) or seen_lines >= 3:
                    continue
                seen_lines += 1
                hits = _git_grep(repo, rev, ["-F", "-e", text], limit=40)
                for f, line, _t in hits:
                    ref = files.function_at(f, line)
                    if ref is None or _same(ref, root) or _short(ref.qualified_name) in root_names:
                        continue  # changed in this commit too (moved code): reviewed with the change
                    if any(_same(ref, c.evidence[0]) for c in found if c.pattern == "same_code_elsewhere"):
                        continue
                    found.append(_case(ref, ch.node_id, "same_code_elsewhere",
                                       f"`{ref.qualified_name}` contains the same code the change rewrote in {rn}: "
                                       "check whether it needs the same fix",
                                       f"`{text[:120]}` ({f}:{line})", [
                                           f"Apply the scenario that motivated the change in {rn} to "
                                           f"`{ref.qualified_name}` and compare the behaviour",
                                           "If the copy is intentionally different, record why in the test result"],
                                       targets))

            # new constant returned -> callers that decide on it
            new_ret = {m.strip() for x in added for m in re.findall(r"\breturn\s+([^;]+);", x)}
            old_ret = {m.strip() for x in removed for m in re.findall(r"\breturn\s+([^;]+);", x)}
            if ch.old is not None:
                old_txt = " ".join(ch.old.tokens)
                old_ret |= {m.strip().replace(" ", "") for m in re.findall(r"\breturn\s+([^;]+);", old_txt)}
            fresh = sorted(v for v in new_ret if _CONST.match(v.replace(" ", "")) and v.replace(" ", "") not in
                           {o.replace(" ", "") for o in old_ret})
            if fresh and ch.change_kind == "modified":
                for dep in graph.callers(ch.node_id)[:40]:
                    ref = graph.symbol_ref(dep.dependent)
                    if ref is None or ref.kind not in ("function", "method"):
                        continue
                    call = re.compile(rf"\b{re.escape(_short(root.qualified_name))}\s*\(")
                    uses = [t for _i, t in files.body(ref) if call.search(t) and
                            re.search(r"\b(if|switch|while)\b|[=!<>]=|[<>?]|=\s*[\w:.>-]*\b" +
                                      re.escape(_short(root.qualified_name)), t)]
                    if uses:
                        found.append(_case(ref, ch.node_id, "return_meaning",
                                           f"`{ref.qualified_name}` decides on the result of {rn}, which can now also "
                                           f"return {', '.join(f'`{v}`' for v in fresh[:4])}: check that outcome",
                                           f"New return value(s) in {rn}: {', '.join(fresh[:4])}", [
                                               f"Make {rn} return {fresh[0]} and check the branch "
                                               f"`{ref.qualified_name}` takes",
                                               "No caller treats the new value as success by accident (e.g. `if (r)` "
                                               "on an error code)"], targets))

            # shared state written by the change -> readers
            written = []
            for x in added:
                for m in _MEMBER_W.finditer(x):
                    if m.group(1) not in written and not re.match(r"\s*(?:auto|int|bool|const|unsigned|size_t|"
                                                                  r"std::)\b", x):
                        written.append(m.group(1))
            for name in written[:3]:
                scope_files = {ch.rel_path}
                stem = Path(ch.rel_path).stem
                if name.startswith(("g_", "s_")):
                    hits = _git_grep(repo, rev, ["-w", "-e", name], limit=60)
                else:
                    hits = [h for h in _git_grep(repo, rev, ["-w", "-e", name], limit=200)
                            if h[0] in scope_files or Path(h[0]).stem == stem]
                readers = []
                for f, line, t in hits:
                    if re.search(rf"\b{re.escape(name)}\s*(?:\[[^\]]*\]\s*)?([+\-*/%|&^]|<<|>>)?=(?!=)", t):
                        continue  # another writer
                    ref = files.function_at(f, line)
                    if ref is None or _same(ref, root) or any(_same(ref, r) for r in readers):
                        continue
                    readers.append(ref)
                for ref in readers[:4]:
                    found.append(_case(ref, ch.node_id, "shared_state",
                                       f"`{ref.qualified_name}` reads `{name}`, which the change now writes differently "
                                       f"in {rn}: check it tolerates the new value and timing",
                                       f"{rn} writes `{name}` on a changed line", [
                                           f"Exercise `{ref.qualified_name}` after {rn} stored each new value of "
                                           f"`{name}`",
                                           "Concurrent access: is the read synchronised with the new write?"],
                                       targets, group="thread_safety" if re.search(
                                           r"thread|async|mutex|atomic", " ".join(added)) else "logic"))

            # new early exit inside the function
            if ch.new is not None and ch.change_kind == "modified":
                end = ch.new.end
                exits = [(ln, t) for ln, t in zip(ch.added_line_numbers, ch.added_lines)
                         if _EXIT.search(strip_comments(t)) and ln < end - 1]
                if exits:
                    body = files.body(root)
                    first = exits[0][0]
                    acquired = sorted({m.group(1) for i, t in body if i < first
                                       for m in _ACQUIRE.finditer(strip_comments(t))})
                    hints = [f"Reach the new exit at line {first} (`{strip_comments(exits[0][1]).strip()[:80]}`) and "
                             "check everything set up before it is undone"]
                    if acquired:
                        hints.append(f"Acquired before the exit: {', '.join(acquired[:6])} — released on this path?")
                    hints.append(f"Callers of {rn} handle the new outcome (no half-initialised state, no missing "
                                 "callback / reply)")
                    ex = _case(root, ch.node_id, "new_early_exit",
                               f"New early exit in {rn}: check resources and callers on that path",
                               f"Added exit at {ch.rel_path}:{first}", hints, targets,
                               group="ownership_lifetime" if acquired else "logic")
                    ex.hop_distance = 0  # about the changed function itself
                    found.append(ex)

        # configuration / flags read by the change -> other readers
        settings = []
        for x in added:
            for rx in _SETTING:
                for m in rx.finditer(x):
                    v = m.group(1)
                    if v and len(v) > 3 and v not in settings and v.lower() not in ("get", "value", "size"):
                        settings.append(v)
        for name in settings[:2]:
            readers = []
            for f, line, _t in _git_grep(repo, rev, ["-w", "-F", "-e", name], limit=80):
                ref = files.function_at(f, line)
                if ref is None or _same(ref, root) or any(_same(ref, r) for r in readers):
                    continue
                readers.append(ref)
            for ref in readers[:4]:
                found.append(_case(ref, ch.node_id, "config_reader",
                                   f"`{ref.qualified_name}` also reads setting `{name}` used by the changed {rn}: check "
                                   "both behave consistently for every value",
                                   f"{rn} reads `{name}` on a changed line", [
                                       f"Run with `{name}` at each value (default, on/off, min/max, unset) and compare "
                                       f"{rn} with `{ref.qualified_name}`",
                                       "Changing the setting at runtime: both readers see the same value"], targets))

        # enumerators added -> switch / case users
        if ch.kind == "enum" and ch.old is not None and ch.new is not None:
            old_ids = set(re.findall(r"[A-Za-z_]\w*", " ".join(ch.old.tokens)))
            new_ids = [t for t in dict.fromkeys(re.findall(r"[A-Za-z_]\w*", " ".join(ch.new.tokens)))
                       if t not in old_ids and t not in ("enum", "class", "struct")]
            if new_ids and old_ids:
                known = sorted(i for i in old_ids if i not in ("enum", "class", "struct", _short(root.qualified_name))
                               and not i.isdigit())[:20]
                pat = (r"case[[:space:]]+([A-Za-z_][A-Za-z0-9_:]*::)?(" + "|".join(map(re.escape, known))
                       + r")([^A-Za-z0-9_]|$)")  # POSIX ERE for git grep -E
                users = []
                for f, line, _t in _git_grep(repo, rev, ["-E", "-e", pat], limit=120):
                    ref = files.function_at(f, line)
                    if ref is None or any(_same(ref, r) for r in users):
                        continue
                    users.append(ref)
                for ref in users[:MAX_PER_ROOT]:
                    found.append(_case(ref, ch.node_id, "new_enum_value",
                                       f"`{ref.qualified_name}` switches over `{root.qualified_name}`, which gained "
                                       f"{', '.join(f'`{n}`' for n in new_ids[:4])}: check the new value is handled",
                                       f"New enumerator(s) in {rn}", [
                                           f"Pass {new_ids[0]} to `{ref.qualified_name}`: handled explicitly, not by a "
                                           "silent `default:`",
                                           "Serialized / persisted values and tables indexed by the enum still line up"],
                                       targets, group="abi_layout"))
        found += coupling(repo, rev, ch, root, root_names, graph, files, targets)
        out.extend(found[:MAX_PER_ROOT * 2])
    return out


# ---- spec 007 US2: lost side effects and state coupling ---------------------------------------------------
_MEMBERISH = re.compile(r"^(?:m_\w+|m[A-Z]\w*|[a-z]\w*_|g_\w+|s_\w+|k[A-Z]\w*|[A-Z][A-Z0-9_]{2,})$")
_SETTER = re.compile(r"^(?:Set|Update|Increment|Inc|Mark)([A-Z]\w*)$|^(?:set|update|increment|mark)(?:_([a-z]\w*)|"
                     r"([A-Z]\w*))$")
_MUTATE = re.compile(r"(?:this->)?\b((?:m_)?[A-Za-z]\w*_|m_\w+)\s*(?:\.|->)\s*(?:Insert|insert|push_back|push_front|"
                     r"emplace\w*|erase|clear|Add|Put|append|Append|reset|assign|resize|pop\w*|Set\w*|set\w*|fetch_\w+|store|"
                     r"exchange|compare_exchange_\w+)\s*\(")
MAX_READERS = 4
_COND_SHAPES = {"operator_flip", "constant_change", "logical_flip", "negation_flip", "removed_guard"}
_COND_LINE = re.compile(r"\b(?:if|while)\s*\(|\?")
_DECL_LINE = re.compile(r"^\s*(?:const\s+|static\s+|auto\b|unsigned\b|int\b|bool\b|char\b|long\b|short\b|double\b|"
                        r"float\b|size_t\b|u?int\d+_t\b|std::\w+[<\w:,\s>]*\s+[A-Za-z_]\w*\s*[=({;])")
_FIELD_WRITE = re.compile(r"((?:[A-Za-z_]\w*|\)|\])\s*(?:->|\.)\s*)?([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)?"
                          r"(?:[+\-*/%|&^]|<<|>>)?=(?!=)")
MAX_ITEMS = 3


def _by_short(graph) -> dict[str, list[tuple[str, str]]]:
    """short name -> [(qualified name, usr)], built once per graph (the by_name table can hold 100k names)."""
    idx = getattr(graph, "_tc_short_index", None)
    if idx is None:
        idx = {}
        for n, us in graph.by_name.items():
            for u in us:
                idx.setdefault(_short(n), []).append((n, u))
        try:
            graph._tc_short_index = idx
        except AttributeError:
            pass
    return idx


def _qualify(ref: SymbolRef, graph) -> SymbolRef:
    """A text-found function defined inside a class body has no class in its name: take the graph's symbol of the
    same short name in the same file when there is exactly one."""
    if graph is None or "::" in ref.qualified_name:
        return ref
    hits = [r for _n, u in _by_short(graph).get(ref.qualified_name, [])
            if (r := graph.symbol_ref(u)) is not None and r.file_path == ref.file_path]
    return hits[0] if len({h.qualified_name for h in hits}) == 1 else ref


def _readers(repo: Path, rev: str | None, files: _Files, name: str, root: SymbolRef, root_names: set[str],
             stem: str | None, member_access: bool = False, writers: bool = False,
             graph=None) -> list[tuple[SymbolRef, str, int]]:
    """Functions reading ``name`` (not writing it unless ``writers``), bounded; ``stem`` restricts to the class's
    own files."""
    if member_access:
        hits = _git_grep(repo, rev, ["-E", "-e", rf"(\.|->)[[:space:]]*{re.escape(name)}([^A-Za-z0-9_]|$)"], limit=200)
    else:
        hits = _git_grep(repo, rev, ["-w", "-e", name], limit=200)
    if stem is not None:
        hits = [h for h in hits if Path(h[0]).stem == stem]
    out: list[tuple[SymbolRef, str, int]] = []
    for f, line, t in hits:
        code = strip_comments(t)
        if re.search(rf"\b{re.escape(name)}\s*(?:\[[^\]]*\]\s*)?(?:[+\-*/%|&^]|<<|>>)?=(?!=)", code) \
                and not re.search(r"\b(if|while|return|assert)\b", code) and not writers:
            continue  # another writer
        if not writers and re.search(rf"\b{re.escape(name)}\s*(?:\.|->)\s*(?:push_back|push_front|emplace\w*|insert|"
                                     r"erase|clear|reset|assign|resize|reserve|pop_\w+|swap|append)\s*\(", code) \
                and not re.search(r"\b(if|while|return|assert)\b|[=<>!]=|[<>?]", code):
            continue  # a mutating call: another writer, not a consumer of the stored value
        ref = files.function_at(f, line)
        acc = _trivial_accessor(files, ref, f, line, code, name)
        if acc is not None and graph is not None:
            # the accessor itself stays a reader (when found); its callers are the ones that see the value
            if ref is not None and not (_same(ref, root) or _short(ref.qualified_name) in root_names
                                        or any(_same(ref, r[0]) for r in out)):
                q = _qualify(ref, graph)
                files.accessors.add((q.qualified_name, f))
                out.append((q, f, line))
            callers, extra = _accessor_callers(graph, files, acc, f, name, root, root_names)
            for cref, cf, cl in callers:
                if not any(_same(cref, r[0]) for r in out):
                    out.append((cref, cf, cl))
                    files.via[(cref.qualified_name, cf, cl)] = \
                        f"through the accessor `{acc}` that returns `{name}`" + \
                        (f" (+{extra} more caller(s) of it not listed)" if extra else "")
            continue
        if ref is not None and re.search(rf"(?<![\w.>]){re.escape(name)}\s*[({{]", code) and "::" in ref.qualified_name \
                and _short(ref.qualified_name) == ref.qualified_name.split("::")[-2].split("<")[0]:
            continue  # constructor initialiser list: a writer
        if ref is None or _same(ref, root) or _short(ref.qualified_name) in root_names \
                or any(_same(ref, r[0]) for r in out):
            continue
        out.append((_qualify(ref, graph), f, line))
    # product code first: tests, benchmarks and examples only fill the remaining slots
    return sorted(out, key=lambda r: _proximity(r, root))


MAX_ACCESSOR_CALLERS = 4
_ONE_LINE_GETTER = re.compile(r"(~?[A-Za-z_]\w*)\s*\([^()]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:override\s*)?"
                              r"\{\s*return\b[^;{}]*;\s*\}")


def _trivial_accessor(files: _Files, ref: SymbolRef | None, f: str, line: int, code: str, name: str) -> str | None:
    """Short name of the accessor when the hit is a trivial one (a body of one ``return <expr using name>;``)."""
    m = _ONE_LINE_GETTER.search(code)
    if m and re.search(rf"\breturn\b[^;]*\b{re.escape(name)}\b", code):
        return m.group(1)
    if ref is None:
        return None
    body = [strip_comments(t).strip() for _i, t in files.body(ref)]
    inner = " ".join(b for b in body[1:-1] if b)
    sig = body[0] if body else ""
    if "{" in sig and sig.split("{", 1)[1].strip().rstrip("}").strip():
        inner = (sig.split("{", 1)[1] + " " + inner).strip()
    inner = inner.rstrip("}").strip()
    if re.fullmatch(rf"return\b[^;]*\b{re.escape(name)}\b[^;]*;", inner):
        return _short(ref.qualified_name)
    return None


def _forwards(files: _Files, ref: SymbolRef, callee: str) -> bool:
    """``ref`` only returns the result of calling ``callee`` (a forwarding accessor: ``return m_p->is_defined();``)."""
    body = [strip_comments(t).strip() for _i, t in files.body(ref)]
    if not body:
        return False
    text = " ".join(body)
    inner = text.split("{", 1)[1].rsplit("}", 1)[0].strip() if "{" in text and "}" in text else ""
    # the whole return expression is the call, reached through members only: `return m_p->f();`, `return d.f();`
    return bool(re.fullmatch(rf"return\s+(?:\*?\s*[A-Za-z_]\w*(?:\(\))?\s*(?:\.|->|::)\s*)*{re.escape(callee)}"
                             rf"\s*\([^;{{}}()]*\)\s*;", inner))


def _accessor_callers(graph, files: _Files, acc: str, f: str, name: str, root: SymbolRef, root_names: set[str]
                      ) -> tuple[list[tuple[SymbolRef, str, int]], int]:
    """Graph callers of the accessor ``acc`` declared in file ``f`` (capped); second value = callers not listed."""
    if graph is None:
        return [], 0
    usrs = [u for _n, u in _by_short(graph).get(acc, [])
            if (r := graph.symbol_ref(u)) is not None and r.file_path == f]
    found: list[tuple[SymbolRef, str, int]] = []
    seen: set[str] = set(usrs)
    frontier = [(u, acc) for u in usrs]
    for _depth in range(3):  # forwarding chains (pimpl: node::f -> node_ref::f -> node_data::f -> m_x)
        nxt = []
        for u, name_ in frontier:
            for dep in graph.callers(u):
                if dep.dependent in seen:
                    continue
                seen.add(dep.dependent)
                ref = graph.symbol_ref(dep.dependent)
                if ref is None or ref.kind == "file" or _same(ref, root) or _short(ref.qualified_name) in root_names \
                        or any(_same(ref, r[0]) for r in found):
                    continue
                if _forwards(files, ref, name_):
                    nxt.append((dep.dependent, _short(ref.qualified_name)))
                    continue
                found.append((ref, ref.file_path, dep.line))
        frontier = nxt
        if not frontier:
            break
    found.sort(key=lambda r: _proximity(r, root))
    return found[:MAX_ACCESSOR_CALLERS], max(0, len(found) - MAX_ACCESSOR_CALLERS)


def _proximity(r: tuple[SymbolRef, str, int], root: SymbolRef) -> tuple:
    """Which readers fill the capped slots: product code before tests / benchmarks, then the changed file, then its
    directory, then the rest (stable: graph / grep order inside a bucket)."""
    f = r[1]
    return (is_test_path(f), bool(re.search(r"(?i)bench|example|sample|demo", f)), f != root.file_path,
            str(Path(f).parent) != str(Path(root.file_path).parent))


def _more(n: int) -> str:
    return f" (+{n} more reader(s) not listed)" if n > 0 else ""


def coupling(repo: Path, rev: str | None, ch, root: SymbolRef, root_names: set[str], graph, files: _Files,
             targets) -> list[TestCaseCandidate]:
    from tcadvisor.classify import edits as E
    rn = f"`{root.qualified_name}`"
    stem = Path(ch.rel_path).stem
    shapes = E.shapes_of(ch)
    out: list[TestCaseCandidate] = []
    items = 0

    def emit(kind: str, name: str, readers, desc, act, hints, group="logic", cap=MAX_READERS):
        for ref, f, line in readers[:cap]:
            via = files.via.get((ref.qualified_name, f, line))
            out.append(_case(ref, ch.node_id, kind, desc(ref) + (f", {via}" if via else "") + _more(len(readers) - cap),
                             f"{act} (read at {f}:{line})", hints(ref), targets, group=group))

    is_fn = ch.kind in ("function", "method")
    for x in shapes:
        if items >= MAX_ITEMS:
            break
        if x.kind in ("removed_assignment", "value_change") and is_fn:
            m = re.match(r"^(?:this->)?([A-Za-z_]\w*)", x.old)
            name = m.group(1) if m else ""
            if not _MEMBERISH.match(name):
                continue
            items += 1
            glob = name.startswith(("g_", "s_")) or bool(re.match(r"k[A-Z]", name)) or name.isupper()
            readers = _readers(repo, rev, files, name, root, root_names, None if glob else stem, graph=graph)
            verb = "no longer writes" if x.kind == "removed_assignment" else "now writes differently"
            emit("removed_write", name, readers,
                 lambda r, n=name, v=verb: f"`{r.qualified_name}` reads `{n}`, which {rn} {v}: check it still "
                                          "behaves when the old update does not happen",
                 f"{rn}: `{x.old[:80]}`" + (f" → `{x.new[:60]}`" if x.new else " removed"),
                 lambda r, n=name: [f"Run `{r.qualified_name}` after {rn} on the changed path and check the value of "
                                    f"`{n}` it sees", "Concurrent / repeated calls: two calls in a row, interleaved "
                                    "with the reader"])
        elif x.kind == "removed_call":
            m = re.match(r"^`([^`(]+)\(", x.hint)
            callee = m.group(1) if m else ""
            short = re.split(r"::|\.|->", callee)[-1]
            sm = _SETTER.match(short)
            if not sm:
                continue
            items += 1
            base = next(g for g in sm.groups() if g)
            base = base[:1].upper() + base[1:] if sm.group(2) is None else base
            cands = [base, "Get" + base, "get" + base, "get_" + base.lower(), base[:1].lower() + base[1:],
                     "Is" + base, "is_" + base.lower()]
            scope = callee.rsplit("::", 1)[0] if "::" in callee else ""
            # getters of the class that owns the setter (``obj.SetX`` has no scope: the classes that declare SetX)
            idx = _by_short(graph)
            owners = {scope} if scope else {n.rsplit("::", 1)[0] for n, _u in idx.get(short, []) if "::" in n}
            getters = [u for c in cands for n, u in idx.get(c, [])
                       if ("::" in n and any(n.rsplit("::", 1)[0] == o or n.rsplit("::", 1)[0].endswith("::" + o)
                                             for o in owners)) or (not owners and n == c)]
            readers = []
            for g in getters[:3]:
                for dep in graph.callers(g):
                    ref = graph.symbol_ref(dep.dependent)
                    if ref is None or ref.kind == "file" or _short(ref.qualified_name) in root_names \
                            or any(_same(ref, r[0]) for r in readers):
                        continue
                    readers.append((ref, ref.file_path, dep.line))
            gname = next((graph.symbol_ref(g).qualified_name for g in getters[:1] if graph.symbol_ref(g)), base)
            emit("setter_readers", base, readers,
                 lambda r, c=callee, gn=gname: f"`{r.qualified_name}` reads `{gn}`, but {rn} no longer calls "
                                               f"`{c}`: check the value it now sees",
                 f"{rn} no longer calls `{callee}`",
                 lambda r, gn=gname: [f"Drive {rn} on the changed path, then `{r.qualified_name}`: `{gn}` must still "
                                      "be what it expects (counts, sizes, state flags)",
                                      "Mismatch checks / asserts on that value in the reader"])
        elif x.kind in ("lock_removed", "lock_added") and is_fn:
            lk = E.lock_name(x.old or x.new) or ""
            body = " ".join(E.norm(t) for t in (ch.new_body or ch.old_body))
            members = [m for m in dict.fromkeys(re.findall(r"(?<![\w.>])((?:m_)?[a-z]\w*_|m_\w+)(?!\w)", body))
                       if m != lk and not lk.endswith(m)][:2]
            for mem in members:
                if items >= MAX_ITEMS:
                    break
                items += 1
                readers = _readers(repo, rev, files, mem, root, root_names, stem, writers=True, graph=graph)
                emit("lock_coupling", mem, readers,
                     lambda r, mm=mem: f"`{r.qualified_name}` also accesses `{mm}`, which {rn} uses with the lock on "
                                       f"`{lk}` {'removed' if x.kind == 'lock_removed' else 'added'}: check concurrent "
                                       "access",
                     f"{rn}: `{(x.old or x.new)[:80]}` {'removed' if x.kind == 'lock_removed' else 'added'}",
                     lambda r, mm=mem: [f"Call {rn} and `{r.qualified_name}` from two threads at once (data race on "
                                        f"`{mm}`)", "Lock order: does the reader hold another lock while taking "
                                        f"`{lk}`?"], group="thread_safety", cap=2)
        elif x.kind in ("value_change", "constant_change") and not is_fn:
            m = re.search(r"\b([A-Za-z_]\w*)\s*(?:=|\{)", x.old) or re.match(r"^#\s*define\s+(\w+)", x.old)
            name = m.group(1) if m else ""
            if len(name) < 4 or name in ("return", "const", "static"):
                continue
            items += 1
            member = ch.kind in ("class", "struct") and not _MEMBERISH.match(name)
            readers = _readers(repo, rev, files, name, root, root_names, None, member_access=member, graph=graph)
            emit("changed_default", name, readers,
                 lambda r, n=name: f"`{r.qualified_name}` reads `{n}`, whose initial value changed in {rn}: check it "
                                   "with the new default",
                 f"{rn}: `{x.old[:70]}` → `{x.new[:70]}`",
                 lambda r, n=name: [f"Run `{r.qualified_name}` with the new default of `{n}` and with the old one "
                                    "(configs that set it explicitly)", f"Limits derived from `{n}` (minimum, maximum, "
                                    "clipping, division)"])
    # spec 008: state written under a condition the edit changed -> its readers see the write in other states
    if is_fn and ch.new is not None and items < MAX_ITEMS:
        from tcadvisor.graph.sources import guard_scope
        done_fields: set[str] = set()
        for x in [y for y in shapes if y.kind in _COND_SHAPES and y.new and _COND_LINE.search(y.new)][:2]:
            idx = next((i for i, t in enumerate(ch.new_body) if E.norm(t) == x.new), None)
            if idx is None:
                continue
            first, last = guard_scope(ch.new_body, idx + 1)
            for k in range(first, min(last, len(ch.new_body)) + 1):
                code = strip_comments(ch.new_body[k - 1])
                if k == idx + 1:
                    code = code.rsplit(")", 1)[-1]  # braceless `if (c) x = y;`: only what follows the condition
                elif _DECL_LINE.match(code):
                    continue
                for m in _FIELD_WRITE.finditer(code):
                    access, fld = m.group(1), m.group(2)
                    if fld in done_fields or len(fld) < 3 or fld in ("return", "else", "case") \
                            or not (access or _MEMBERISH.match(fld)):
                        continue
                    done_fields.add(fld)
                    if items >= MAX_ITEMS or len(done_fields) > 2:
                        break
                    items += 1
                    member = bool(access) and not _MEMBERISH.match(fld)
                    glob = fld.startswith(("g_", "s_")) or fld.isupper()
                    readers = _readers(repo, rev, files, fld, root, root_names, None if (glob or member) else stem,
                                       member_access=member, graph=graph)
                    cond = x.new[:80]
                    emit("conditional_write", fld, readers,
                         lambda r, n=fld, c=cond: f"`{r.qualified_name}` reads `{n}`, which {rn} writes only under the "
                                                  f"changed condition `{c}`: check it in the states where the write "
                                                  "now happens or no longer happens",
                         f"{rn}: condition `{x.old[:60]}` → `{x.new[:60]}` guards a write to `{fld}`",
                         lambda r, n=fld: [f"Drive {rn} with inputs on both sides of the changed condition, then "
                                           f"`{r.qualified_name}`: the value of `{n}` it sees must stay valid",
                                           "Boundary value of the condition (exactly at the limit)"])
    # callees protected by a removed / weakened condition are now reached in the states it excluded
    for x in [y for y in shapes if y.kind == "removed_guard" and y.new and ch.new is not None][:1]:
        from tcadvisor.graph.sources import guard_scope
        idx = next((i for i, t in enumerate(ch.new_body) if E.norm(t) == x.new), None)
        if idx is None:
            continue
        first, last = guard_scope(ch.new_body, idx + 1)
        cond = x.hint.split("`")[1] if x.hint.count("`") >= 2 else x.old
        state = f"`{cond[:60]}` holds" if x.hint.startswith("Removed early exit") else f"`{cond[:60]}` is false"
        seen: set[str] = set()
        for usr, _qn, _k, _df, _dl, line in ch.new.calls:
            local = line - ch.new.start + 1
            ref = graph.symbol_ref(usr)
            if not (first <= local <= last) or usr in seen or usr == ch.node_id or ref is None or ref.kind == "file":
                continue
            seen.add(usr)
            c = _case(ref, ch.node_id, "guard_removed_callee",
                      f"`{ref.qualified_name}` is now called from {rn} also when {state}: check it handles that "
                      "state",
                      f"Condition removed in {rn}: `{x.old[:80]}` (call at {ch.rel_path}:{line})", [
                          f"Call {rn} so that {state} and check `{ref.qualified_name}` (no crash, no corrupted state, "
                          "correct result)",
                          f"`{ref.qualified_name}`'s own preconditions (asserts, documented assumptions) still hold"],
                      targets)
            out.append(c)
            if len(seen) >= 3:
                break
    # producer / consumer within the class: members a modified method writes, read by its class mates
    if is_fn and ch.change_kind == "modified" and items < MAX_ITEMS and "::" in root.qualified_name:
        cls = root.qualified_name.rsplit("::", 1)[0].split("::")[-1]
        written = []
        for t in ch.new_body:
            code = strip_comments(t)
            for m in list(_MUTATE.finditer(code)) + list(_MEMBER_W.finditer(code)):
                mem = m.group(1)
                if mem and mem not in written and (mem.endswith("_") or mem.startswith("m_")):
                    written.append(mem)
        done = {c.evidence[0].qualified_name for c in out}
        for mem in written[:2]:
            readers = [r for r in sorted(_readers(repo, rev, files, mem, root, root_names, stem, graph=graph),
                                         key=lambda r: (r[0].qualified_name, r[1]) in files.accessors)
                       if (r[0].qualified_name.rsplit("::", 1)[0].split("::")[-1] == cls
                           or "::" not in r[0].qualified_name)  # defined inside the class body (same file stem)
                       and (r[0].qualified_name, r[1], r[2]) not in files.via  # accessor callers: other code
                       and r[0].qualified_name not in done]
            if not readers:
                continue
            emit("class_consumer", mem, readers[:2],
                 lambda r, mm=mem: f"`{r.qualified_name}` reads `{mm}`, which the modified {rn} writes: check it still "
                                   "understands what is stored there",
                 f"{rn} writes `{mem}`",
                 lambda r: [f"Round trip: store through {rn}, read back through `{r.qualified_name}` (boundary and "
                            "empty values)", "Data stored by the old version (compatibility)"])
            done |= {r[0].qualified_name for r in readers[:2]}
    return out


def apply_lessons(cases: list[TestCaseCandidate], lessons, changes: list, nodes) -> None:
    """Team lessons (``lessons.json``): add ``Lesson <id> (<title>): <ask>`` to matching cases."""
    if not lessons.lessons:
        return
    toks: dict[str, set[str]] = {}
    for ch in changes:
        toks[ch.node_id] = set(re.findall(r"[A-Za-z_]\w*", " ".join(ch.added_lines + ch.removed_lines)))
    for c in cases:
        ev = c.evidence[0]
        node = nodes.get(c.node_id)
        rids = node.root_ids if node is not None and c.hop_distance > 0 else {c.node_id}
        t = set().union(*(toks.get(r, set()) for r in rids)) if rids else set()
        for lesson in lessons.lessons:
            if lesson.matches(ev.qualified_name, ev.file_path, t, c.sub_reason):
                c.hints.append(f"Lesson {lesson.id} ({lesson.title}): {lesson.ask}")
                c.lessons.append(lesson.id)
