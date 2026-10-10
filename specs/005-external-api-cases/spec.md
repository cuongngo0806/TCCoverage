# Spec: Test cases at third-party API boundaries (cycle 5)

## Problem

A module is often analysed with only its own code in the graph (codegraph / compile db of the module). Its
third-party dependencies are visible only as declarations in headers: the advisor knows *that* a changed
function now calls `vendor_send(buf, len)`, not what `vendor_send` does. Cycle 4 dropped these callees
silently; convergence tasks T219/T220 (spec 002) turned them into `uncertainty_flags`. Reviewers still get no
concrete case to check at that boundary.

## Clarifications (decided)

- The library body is never needed: cases come from the callee's **declaration** (as parsed by libclang from
  the include path in `compile_commands.json`) and from the **call site** in the analysed repo.
- Cases are emitted on the **calling function** (a changed symbol in the repo), so evidence always resolves
  (constitution II). The external callee itself never becomes an impact node.
- Standard library calls (`std::`, reserved `__` names, C standard headers and `bits/` internals) are not
  third-party: counted in `run_notes`, no case.
- No new risk group and no new uncertainty category (data-model: the taxonomies only grow by constitution
  amendment): existing groups, new `sub_reason` `external_call`.
- One case per calling function (bounded volume; ranking guarded by the cycle-4 benchmark), not propagated to
  callers of the calling function.
- Known library behaviour the declaration cannot show (error codes, threading rules) comes from an optional,
  local, hand-written contract file — never from an LLM.

## User Stories

### US1 — Case at the boundary (P1)
A developer changes `dispatch()` to call `vendor_send(s.c_str(), code)` from a library outside the repo. The
report contains a case "Verify how `dispatch` handles the third-party API it now calls: `vendor_send`" with
corner cases derived from `vendor_send`'s declaration (error return, pointer/length parameters, ...).
**Test**: integration fixture with a header-only fake vendor library outside the repo.

### US2 — Project knowledge about a library (P2)
A team records once that `vendor_send` returns `-EAGAIN` when the queue is full. Every later case on a caller
of `vendor_send` lists that corner case, labelled as coming from the contract file.
**Test**: same fixture + `.tcadvisor/external-contracts.json`.

## Functional Requirements

- **FR-501** A callee on a changed line whose declaration is outside the repository is a *third-party call*;
  standard-library callees are excluded and counted in `run_notes`.
- **FR-502** From the callee declaration and the call site the advisor derives, deterministically:
  pointer return (null), status-like return (integral / `bool` / enum / `*error*`/`*status*`/`*result*`/
  `optional`/`expected` types: failure value), result discarded at the call site, may throw (C++ linkage and
  not `noexcept`), non-const pointer/reference parameters (out-parameter / ownership), callback parameters
  (function pointer, `std::function`), pointer + size-like parameter pairs (boundary lengths).
- **FR-503** One `TestCaseCandidate` per calling function with `sub_reason: external_call`, the most severe risk
  group among the derived signals (`exception_safety` / `ownership_lifetime` / `thread_safety` / `logic`),
  evidence = the calling function, activation condition naming each callee, its header and call line, and one
  hint per derived signal (at most 10; may-throw callees merged into one hint). Emitted at hop 0 only, ordered
  after the other hop-0 cases. Operators, constructors/destructors/conversions and `const` queries contribute
  no signal of their own (a `const` query only for a pointer return or a callback); a call with nothing to
  test yields no case (the FR-505 flag remains).
- **FR-504** Optional `.tcadvisor/external-contracts.json` in the analysed repo (or `--contracts FILE`):
  `{"<qualified name or fnmatch pattern>": ["corner case", ...]}`. Matching entries are added to the hints,
  prefixed `Contract:`. An unreadable file is a usage error (exit 2).
- **FR-505** The `dynamic_runtime_dependency` flag for the third-party call (T219) is kept: the library's
  behaviour remains a blind spot even when cases exist.

## Success Criteria

- **SC-501** Fixture tests for US1 and US2 green; full suite green.
- **SC-502** Benchmark of spec 004 (`scripts/pilot_regressions.py`, 55 regressions): recall unchanged and MRR
  of dev *and* holdout not lower than the same harness on the cycle-4 code.
