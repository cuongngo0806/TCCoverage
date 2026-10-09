"""Deterministic, additive risk-group rules (FR-003, research.md §6).

Every rule looks only at the old/new comment-free token streams, signatures and declarations of a
changed symbol — never at an LLM. Rules are additive: one change may trigger several groups.
``logic`` is added when control-flow/arithmetics changed, and is the fallback when nothing else
matched (spec Assumptions), so every change receives at least one classification.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

from tcadvisor.ingest.changes import SymbolChange
from tcadvisor.models import RiskClassification

OWNERSHIP_RAW = {"new", "delete", "malloc", "calloc", "realloc", "free", "nullptr", "NULL", "unique_ptr",
                 "shared_ptr", "weak_ptr", "make_unique", "make_shared", "release", "auto_ptr"}
OWNERSHIP_MOVE = {"move", "forward", "&&"}
THREAD_MUTEX = {"mutex", "recursive_mutex", "shared_mutex", "timed_mutex", "recursive_timed_mutex",
                "shared_timed_mutex", "lock_guard", "unique_lock", "scoped_lock", "shared_lock",
                "condition_variable", "condition_variable_any", "lock", "unlock", "try_lock", "notify_one",
                "notify_all", "wait", "wait_for", "wait_until", "call_once", "once_flag", "pthread_mutex_lock",
                "pthread_mutex_unlock", "pthread_mutex_t", "pthread_cond_wait", "pthread_cond_signal",
                "thread", "async", "future", "promise", "pthread_create", "detach", "join"}
THREAD_ATOMIC = {"atomic", "atomic_flag", "atomic_bool", "atomic_int", "memory_order", "memory_order_relaxed",
                 "memory_order_acquire", "memory_order_release", "memory_order_acq_rel", "memory_order_seq_cst",
                 "volatile", "fetch_add", "fetch_sub", "compare_exchange_weak", "compare_exchange_strong",
                 "exchange", "load", "store", "thread_local"}
LOCK_ACQUIRE = {"lock_guard", "unique_lock", "scoped_lock", "shared_lock", "lock", "pthread_mutex_lock"}
EXCEPTION_TOKENS = {"throw", "try", "catch", "noexcept", "rethrow_exception", "current_exception",
                    "exception_ptr", "terminate"}
DEBUG_TOKENS = {"NDEBUG", "_DEBUG", "DEBUG", "assert", "static_assert"}
LOGIC_TOKENS = {"if", "else", "switch", "case", "default", "return", "for", "while", "do", "break",
                "continue", "goto", "==", "!=", "<", ">", "<=", ">=", "&&", "||", "!", "?", ":", "+", "-",
                "*", "/", "%", "++", "--", "+=", "-=", "<<", ">>", "&", "|", "^", "~", "true", "false"}
_SYNC_ID = re.compile(r"(?i)^\w*(mutex|locker|spinlock|semaphore|critical_?section|guard_?lock)\w*$|^\w*Lock$")
_NUM = re.compile(r"^-?(0x[0-9a-fA-F]+|\d+(\.\d+)?)[uUlLfF]*$")
_CMP = re.compile(r"([A-Za-z_][\w.\->\[\]()]*)\s*(<=|>=|==|!=|<|>)\s*(-?(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?))")
_PP_LINE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif|define|undef|include|pragma)\b")

HINTS: dict[tuple[str, str | None], list[str]] = {
    ("logic", None): [
        "Exercise every branch whose condition changed (true and false paths)",
        "Boundary values around changed comparisons and loop limits (min, max, off-by-one)",
        "Error / early-return paths and default switch case",
    ],
    ("abi_layout", "header_change"): [
        "Rebuild every target that includes the header (no stale objects / prebuilt libs)",
        "Callers compiled against the old header still link and behave",
    ],
    ("abi_layout", "member_change"): [
        "sizeof / alignment / field offsets used by serialization, IPC or memcpy",
        "Aggregate / designated initialisation and default member values",
        "Copy / move / comparison operators still cover all members",
        "Virtual dispatch through base pointers (vtable change) in all derived classes",
    ],
    ("abi_layout", "signature_change"): [
        "All call sites pass the new parameters correctly (implicit conversions, default args)",
        "Overload resolution does not silently pick a different overload",
        "Function pointers / callbacks / mocks bound to the old signature",
    ],
    ("abi_layout", "inline_change"): [
        "Every translation unit inlining the old body is rebuilt (ODR, mixed old/new objects)",
    ],
    ("ownership_lifetime", "raw_pointer"): [
        "Null pointer input and allocation failure",
        "No double delete / leak on every exit path (including early return and exceptions)",
        "Object still alive when accessed asynchronously (callbacks, timers, other threads)",
    ],
    ("ownership_lifetime", "reference"): [
        "Referenced object outlives the reference (no dangling reference to temporaries/locals)",
        "Aliasing: same object passed for two reference parameters",
    ],
    ("ownership_lifetime", "move_semantics"): [
        "No use of an object after it was moved from",
        "Self-move / moved-from state is valid and destructible",
    ],
    ("thread_safety", "mutex"): [
        "Concurrent calls from two or more threads (data race on shared state)",
        "Re-entrancy: callback invoked while the lock is held (self-deadlock)",
        "Lock released on every exit path, including exceptions",
    ],
    ("thread_safety", "atomic"): [
        "Concurrent read-modify-write sequences are not split into separate atomic ops",
        "Memory ordering between the atomic and the data it guards",
    ],
    ("thread_safety", "lock_order"): [
        "Two threads acquiring the same locks in opposite order (deadlock)",
        "Lock hierarchy documented/observed by every caller",
    ],
    ("exception_safety", "noexcept_change"): [
        "A throw escaping a noexcept function calls std::terminate",
        "Containers (std::vector reallocation) choose copy vs move based on noexcept",
    ],
    ("exception_safety", "throw_added"): [
        "Every caller handles (or deliberately propagates) the new exception",
        "State stays consistent when an exception is thrown midway (strong/basic guarantee)",
        "Exceptions crossing C / thread / callback boundaries",
    ],
    ("build_config", "macro"): [
        "Build and run with the macro defined and undefined",
        "All #if/#else branches compile on every configuration/platform",
    ],
    ("build_config", "debug_release"): [
        "Behaviour in both Debug and Release (asserts compiled out under NDEBUG)",
    ],
    ("build_config", "target"): [
        "Clean configure + build of every affected target",
        "Link order / new or removed dependencies / compile definitions",
    ],
}


def token_delta(old: list[str], new: list[str]) -> tuple[list[str], list[str]]:
    added: list[str] = []
    removed: list[str] = []
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op in ("replace", "delete"):
            removed.extend(old[a1:a2])
        if op in ("replace", "insert"):
            added.extend(new[b1:b2])
    return added, removed


def _lock_sequence(tokens: list[str]) -> list[str]:
    seq = []
    for i, t in enumerate(tokens):
        if t in LOCK_ACQUIRE:
            # name of the mutex: first identifier inside the following parentheses
            for j in range(i + 1, min(i + 12, len(tokens))):
                if tokens[j] == "(":
                    k = j + 1
                    while k < len(tokens) and not (tokens[k][:1].isalpha() or tokens[k][:1] == "_"):
                        k += 1
                    if k < len(tokens):
                        seq.append(tokens[k])
                    break
    return seq


def _signature(decl: list[str]) -> dict[str, list[str]]:
    """Pointer / non-const reference parts of a declaration, by parameter (token based)."""
    if "(" not in decl:
        return {"ptr": [], "ref": []}
    i = decl.index("(")
    ret, depth, params, cur = decl[:i], 0, [], []
    for t in decl[i + 1:]:
        if t in "([{<":
            depth += 1
        elif t in ")]}>":
            if depth == 0:
                break
            depth -= 1
        if t == "," and depth == 0:
            params.append(cur)
            cur = []
        else:
            cur.append(t)
    params.append(cur)
    parts = [ret] + params

    def kind_of(p: list[str]) -> list[str]:  # type tokens without the parameter name
        return [t for t in p if t in ("*", "&", "&&", "const") or t[:1].isalpha()][:-1] if p else []
    ptr = [" ".join(kind_of(p)) for p in parts if "*" in p and not ("char" in p and "const" in p)]
    ref = [" ".join(kind_of(p)) for p in parts if "&" in p and "const" not in p]
    return {"ptr": ptr, "ref": ref}


def boundary_hints(lines: list[str], prefix: str = "Boundary") -> list[str]:
    out = []
    for ln in lines:
        for var, op, lit in _CMP.findall(ln):
            try:
                v = int(lit, 0) if not ("." in lit) else float(lit)
            except ValueError:
                continue
            if isinstance(v, int):
                vals = sorted({v - 1, v, v + 1})
                out.append(f"{prefix}: `{var} {op} {lit}` with {var} = {', '.join(map(str, vals))}")
            else:
                out.append(f"{prefix}: `{var} {op} {lit}` just below, at and just above {lit}")
    return list(dict.fromkeys(out))[:6]


def _fmt(tokens: set[str] | list[str]) -> str:
    return ", ".join(f"`{t}`" for t in sorted(set(tokens))[:6])


def classify(ch: SymbolChange, configurations: list[str]) -> list[RiskClassification]:
    out: list[RiskClassification] = []

    def add(group: str, sub: str | None, detail: str, extra_hints: list[str] | None = None,
            configs: list[str] | None = None) -> None:
        if any(r.risk_group == group and r.sub_reason == sub for r in out):
            return
        out.append(RiskClassification(group, sub, detail, (extra_hints or []) + HINTS.get((group, sub), []),
                                      configs))

    if ch.is_test_code:
        return [RiskClassification("logic", "test_code", f"test code changed: `{ch.name}` ({ch.rel_path}:{ch.line})",
                                   ["Run the changed test and confirm it fails without the product change "
                                    "(it really covers it)"])]
    if ch.is_log_only:
        return [RiskClassification("logic", "logging", f"only logging statements changed in `{ch.name}` "
                                   f"({ch.rel_path}:{ch.line})",
                                   ["Log text/format still matches what tests, monitoring or log parsers expect",
                                    "No side effects or expensive calls inside the log arguments; "
                                    "log level filtering still works"])]

    o, n = ch.old, ch.new
    old_tokens = o.tokens if o else []
    new_tokens = n.tokens if n else []
    if ch.kind == "file":
        old_tokens = " ".join(ch.removed_lines).split()
        new_tokens = " ".join(ch.added_lines).split()
    added, removed = token_delta(old_tokens, new_tokens)
    delta = set(added) | set(removed)
    changed_text = ch.added_lines + ch.removed_lines
    where = f"`{ch.name}` ({ch.rel_path}:{ch.line})"

    # ---- build_config ---------------------------------------------------------------------
    is_cmake = ch.kind == "file" and (ch.rel_path.endswith("CMakeLists.txt") or ch.rel_path.endswith(".cmake"))
    if is_cmake:
        add("build_config", "target", f"CMake build definition {ch.rel_path} changed", configs=configurations)
    pp_lines = [ln.strip() for ln in changed_text if _PP_LINE.match(ln)]
    if ch.kind == "macro":
        add("build_config", "macro", f"macro {where} definition {ch.change_kind}", configs=configurations)
    if ch.conditions:
        add("build_config", "macro", f"change in {where} is inside `{' && '.join(ch.conditions)}`",
            configs=configurations)
    if any(not ln.startswith("#include") for ln in pp_lines):
        add("build_config", "macro", f"preprocessor directives changed near {where}: "
            + "; ".join(f"`{ln}`" for ln in pp_lines[:3]), configs=configurations)
    if delta & DEBUG_TOKENS:
        add("build_config", "debug_release", f"{_fmt(delta & DEBUG_TOKENS)} changed in {where}",
            configs=configurations)

    if is_cmake:
        return out

    # ---- abi_layout ----------------------------------------------------------------------------
    if ch.kind in ("class", "struct") and o and n:
        if o.fields != n.fields:
            on, nn = [f[0] for f in o.fields], [f[0] for f in n.fields]
            if sorted(o.fields) == sorted(n.fields):
                what = "members reordered"
            elif set(on) == set(nn):
                what = "member types changed: " + _fmt({f"{a}:{b}" for a, b in set(n.fields) - set(o.fields)})
            else:
                parts = []
                if set(nn) - set(on):
                    parts.append("added " + _fmt(set(nn) - set(on)))
                if set(on) - set(nn):
                    parts.append("removed " + _fmt(set(on) - set(nn)))
                what = "members " + ", ".join(parts)
            add("abi_layout", "member_change", f"data layout of {where} changed ({what})")
        if o.virtuals != n.virtuals:
            new_pure = [v[:-4] for v in n.virtuals if v.endswith(" = 0") and v not in o.virtuals]
            add("abi_layout", "member_change", f"virtual function table of {where} changed"
                + (f"; new pure virtual {_fmt(new_pure)}" if new_pure else ""),
                ([f"Every implementation of `{ch.name}` (also outside this repo, e.g. mocks, plugins, downstream "
                  f"projects) must now override {_fmt(new_pure)} or it fails to compile"] if new_pure else [])
                + ["Objects created by old binaries / plugins used with the new vtable layout"])
        if o.bases != n.bases:
            add("abi_layout", "member_change", f"base classes of {where} changed")
    if ch.kind == "enum" and o and n and o.tokens != n.tokens:
        add("abi_layout", "member_change", f"enumerators of {where} changed (switch coverage, serialized values)",
            ["Every switch over the enum handles the new/removed enumerators",
             "Persisted / transmitted numeric values stay compatible"])
    if ch.kind in ("function", "method") and o and n and o.decl_tokens != n.decl_tokens:
        add("abi_layout", "signature_change",
            f"signature of {where} changed: `{' '.join(o.decl_tokens)[:120]}` -> `{' '.join(n.decl_tokens)[:120]}`")
    if ch.change_kind == "removed" and ch.kind != "file":
        add("abi_layout", "signature_change", f"{where} was removed; remaining users must be updated")
    if ch.kind in ("function", "method") and n and n.is_inline and o and o.tokens != n.tokens \
            and o.decl_tokens == n.decl_tokens:
        add("abi_layout", "inline_change", f"inline body of {where} changed (compiled into every includer)")
    if ch.is_header and ch.change_kind != "explicit" and not any(r.risk_group == "abi_layout" for r in out):
        if ch.kind == "file":
            inc = [ln for ln in changed_text if ln.strip().startswith("#include")]
            if inc or (set(added) | set(removed)) - {"#", "include"}:
                add("abi_layout", "header_change", f"header {ch.rel_path} changed at file scope"
                    + (f" (includes: {'; '.join(i.strip() for i in inc[:3])})" if inc else ""))
        else:
            add("abi_layout", "header_change", f"{where} declared in a header changed; every includer recompiles")

    # ---- ownership_lifetime ----------------------------------------------------------------------
    decl_added, decl_removed = token_delta(o.decl_tokens if o else [], n.decl_tokens if n else [])
    decl_delta = set(decl_added) | set(decl_removed)
    field_types = " ".join(t for f in ((o.fields if o else []) + (n.fields if n else [])) for t in f[1:])
    fields_changed = bool(o and n and o.fields != n.fields)
    od, nd = _signature(o.decl_tokens if o else []), _signature(n.decl_tokens if n else [])
    ptr_sig_changed = bool(o and n) and (od["ptr"] != nd["ptr"])
    if delta & OWNERSHIP_RAW or ptr_sig_changed or (fields_changed and "*" in field_types):
        add("ownership_lifetime", "raw_pointer",
            f"pointer ownership changed in {where}: {_fmt((delta & OWNERSHIP_RAW) or {'pointer parameter/return'})}")
    # `const T&` parameters are a calling convention, not a lifetime contract: only non-const references,
    # reference returns and reference members can dangle or alias (pilot: const& changes were top noise)
    if (bool(o and n) and od["ref"] != nd["ref"]) or (fields_changed and "&" in field_types.replace("&&", "")):
        add("ownership_lifetime", "reference", f"non-const reference parameter / reference return or member "
            f"changed in {where}")
    move = (delta & (OWNERSHIP_MOVE - {"&&"})) | (decl_delta & {"&&"})  # `&&` in a body is usually logical AND
    if move:
        add("ownership_lifetime", "move_semantics", f"move semantics changed in {where}: {_fmt(move)}")

    # ---- thread_safety ---------------------------------------------------------------------------
    # project wrappers (leveldb `MutexLock`, `port::Mutex`, Qt `QMutexLocker`, `SpinLock`, ...) count as well
    sync_ids = {t for t in delta if _SYNC_ID.search(t)} - THREAD_ATOMIC
    if delta & THREAD_MUTEX or sync_ids:
        add("thread_safety", "mutex", f"locking/threading primitives changed in {where}: "
            f"{_fmt((delta & THREAD_MUTEX) | sync_ids)}")
    if delta & THREAD_ATOMIC:
        add("thread_safety", "atomic", f"atomic/volatile usage changed in {where}: {_fmt(delta & THREAD_ATOMIC)}")
    if o and n:
        so, sn = _lock_sequence(o.tokens), _lock_sequence(n.tokens)
        if so != sn and Counter(so) == Counter(sn) and len(sn) > 1:
            add("thread_safety", "lock_order",
                f"lock acquisition order in {where} changed: {' -> '.join(so)} became {' -> '.join(sn)}")
    if fields_changed and re.search(r"\b(mutex|atomic)", field_types):
        add("thread_safety", "mutex" if "mutex" in field_types else "atomic",
            f"synchronisation member changed in {where}")

    # ---- exception_safety ------------------------------------------------------------------------
    noexcept_changed = bool(o and n and o.noexcept != n.noexcept) or "noexcept" in delta
    if noexcept_changed:
        add("exception_safety", "noexcept_change",
            f"exception specification of {where} changed" + (f" ({o.noexcept} -> {n.noexcept})" if o and n and o.noexcept != n.noexcept else ""))
    if delta & (EXCEPTION_TOKENS - {"noexcept"}):
        add("exception_safety", "throw_added",
            f"exception flow changed in {where}: {_fmt(delta & (EXCEPTION_TOKENS - {'noexcept'}))}")

    # ---- logic -----------------------------------------------------------------------------------
    logic_delta = (delta & LOGIC_TOKENS) | {t for t in delta if _NUM.match(t)}
    body_changed = bool(o and n and o.tokens != n.tokens and ch.kind in ("function", "method"))
    if logic_delta or (ch.kind in ("function", "method") and ch.change_kind in ("added", "modified")
                       and (body_changed or ch.change_kind == "added")) \
            or ch.change_kind == "explicit" or not out:
        detail = (f"control flow / computation changed in {where}: {_fmt(logic_delta)}" if logic_delta
                  else f"behaviour of {where} {ch.change_kind}")
        old_b = [h for h in boundary_hints(ch.removed_lines, "Previous boundary")
                 if h.split(":", 1)[1] not in {x.split(":", 1)[1] for x in boundary_hints(ch.added_lines)}]
        add("logic", None, detail, (boundary_hints(ch.added_lines) + old_b)[:6])
    return out
