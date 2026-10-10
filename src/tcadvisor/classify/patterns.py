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

Deterministic; every case points to concrete code. Team lessons (``lessons.json``) are matched afterwards.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tcadvisor.ingest.changes import strip_comments, textual_functions
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


def _git_grep(repo: Path, rev: str | None, args: list[str], limit: int = 200) -> list[tuple[str, int, str]]:
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
                    if ref is None or _same(ref, root):
                        continue
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
        out.extend(found[:MAX_PER_ROOT * 2])
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
