# Feature Specification: Side-effect and corner-case completeness

**Feature Branch**: `ccr-f43a06ec-6132n5`

**Created**: 2026-10-11

**Status**: Draft

**Input**: User description (translated from Vietnamese): "Re-evaluate the app and how effective it is. The goal:
when code changes, do not miss the test cases that can cause defects through side effects, do not leave corner
cases unexplored, catch 'fix here, break there'. Propose further useful features. Use speckit and the workflow to
implement, verify and fix until done."

## Evaluation that motivates this spec

A seeded-regression benchmark (`scripts/seeded_regressions.py`) applies 12 small, realistic edits to google/leveldb
— the kind that fix one place and break another — and checks the report against a ground truth written before any
improvement: the functions that really break (*victims*) and the concrete corner case that exposes the bug.

| Measure (baseline, commit f0e2fb3) | Result |
|---|---|
| victim named anywhere in the case list | **8 / 12** |
| concrete corner case hinted on the changed symbol or a victim | **3 / 12** |
| victim MRR (1 / rank of the first victim case) | 0.295 |

What was missed, by kind:

- **Lost side effects**: a removed write of a member (`background_compaction_scheduled_ = true`), a removed setter
  call (`SetCount(...)`), a removed lock (`MutexLock l(&mutex_)`), a changed field default (`write_buffer_size`)
  — the readers of that state are where the defect shows up, and none of them was named.
- **Producer / consumer pairs**: a changed encoder (`MemTable::Add`) whose decoder (`MemTable::Get`) is in the same
  class but not a caller.
- **Corner cases tied to the edit**: `<` → `<=` produced "boundary values around changed comparisons" instead of
  "`left == right` now enters the loop"; swapping `free(e)` before a use of `e` produced no "use after free" hint;
  an error return replaced by `Status::OK()` produced no "malformed input" hint.
- **Noise burying victims**: a loop-condition tweak was treated as a new guard and produced 10 "sibling source"
  cases about unrelated callees ahead of the real callers; methods defined in a `.cc` class body were reported as
  "inline change: rebuild every includer".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Corner cases derived from the shape of the edit (Priority: P1)

A developer changes an operator, a constant, a condition, a return statement or the order of statements. Each case
on the changed symbol lists the concrete inputs that the edit makes behave differently, written with the real
expressions from the code: "`left <= right` now also holds when `left == right` (was excluded)", "constant 64 → 8:
test 7, 8, 9, 63, 64, 65", "removed condition `options.snapshot != nullptr`: call with a null snapshot", "the path
that returned `Status::Corruption(...)` now returns `Status::OK()`: feed malformed input", "`free(e)` now runs before
`(*e->deleter)(e->key(), e->value)`: the later statement must not use what the earlier one released".

**Why this priority**: a reviewer who reads "test boundary values" does not know which value; the edit itself says
which one. This is the cheapest way to make the case list actionable.

**Independent Test**: unit tests feed old/new line pairs for each edit shape and assert the produced hints; the
seeded benchmark corner score rises from 3/12.

**Acceptance Scenarios**:

1. **Given** a comparison whose operator changed between old and new line (`<`↔`<=`, `>`↔`>=`, `==`↔`!=`),
   **When** the advisor runs, **Then** a hint names the operands and the equality case that flips.
2. **Given** a numeric literal that changed in an otherwise identical line, **Then** a hint lists old, new and the
   values just around both.
3. **Given** a removed condition (an `if`/`while`/ternary/assert line in the old code whose condition no longer
   exists), **Then** a hint asks for the input the removed condition used to reject, and the case on the changed
   symbol is raised to P1 ("removed guard").
4. **Given** a return statement whose value changed, **Then** a hint names the old and the new value and asks for
   the input that reached it.
5. **Given** two statements that swapped order, **Then** a hint names both and asks whether the later one depends on
   state the earlier one changed (released, reset, moved).
6. **Given** a removed call or a removed assignment, **Then** a hint names it: "no longer done on this path".
7. **Given** a changed function whose parameters are used on changed lines, **Then** type-based input classes are
   listed per parameter (pointer → null; container / string / slice → empty, one element, large; signed integer →
   negative, 0, max; unsigned → 0, max; bool → both; floating point → 0, negative, NaN), at most 4 parameters.

---

### User Story 2 - Lost side effects and state coupling ("fix here, break there") (Priority: P1)

A developer removes or changes something whose effect is observed elsewhere: a write to a member or global, a call
to a setter, a lock, the default value of a field or constant, or the encoding written by one method and read by
another of the same class. The advisor names the functions that observe that state, with the location where they
read it as evidence, so the defect's real location is in the list even though it is neither a caller nor a callee.

**Why this priority**: 4 of the 12 seeded regressions were invisible for this reason alone; these are exactly the
"fixed here, broke there" defects.

**Independent Test**: a synthetic project fixture with each coupling kind; the report contains a case on each
reader that is not part of the diff and not a caller of the change.

**Acceptance Scenarios**:

1. **Given** a removed (or changed) assignment to a member or global, **When** the advisor runs, **Then** every
   other function (bounded) that reads it gets a case "reads `X`, which the change no longer writes / writes
   differently in `F`".
2. **Given** a removed call to a setter-like function (`SetX`, `setX`, `set_x`, `UpdateX`, `IncrementX`, `AddX`…),
   **Then** the callers of the paired reader (`X`, `GetX`, `getX`, `get_x`) get a case.
3. **Given** a lock acquisition added to or removed from a function, **Then** other functions that access the same
   members as the locked region get a thread-safety case "concurrent access to `m` with `F`".
4. **Given** a changed initial value of a field, global or named constant, **Then** the functions that read that
   name get a case naming old and new value.
5. **Given** a modified method that writes members of its class, **Then** other methods of the same class that read
   those members (and are not callers) get a low-priority "consumer" case.
6. **Given** more readers than the per-change limit, **Then** the remaining count is stated, not dropped silently.

---

### User Story 3 - Less noise in front of the real callers (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a condition that changed only its operator or constants (same identifiers as the old line), or a loop
   condition, **Then** no "sibling trigger source" cases are produced for it (the boundary hints of US1 cover it).
2. **Given** a method defined inside a class body in a source file (not a header), **Then** no "inline change:
   rebuild every includer" case is produced.

---

### User Story 4 - Test-gap summary (Priority: P2)

For every changed symbol the report states whether an existing test was found in its impact set. Changed symbols
with no existing test are listed as test gaps (report, brief output, HTML and Markdown), so the reviewer knows a new
test is likely needed rather than a re-run.

**Acceptance Scenarios**:

1. **Given** a change to a function that no test reaches within the hop depth, **Then** the report lists it under
   test gaps; **Given** one that a test reaches, **Then** the test is named instead.

---

### Edge Cases

- Macro-heavy or textual (parser did not see) changes: hints use the changed text only; no crash on unbalanced code.
- A reorder that is really a move of a block (many lines): reported once, not once per line pair.
- Setter without a matching getter: no reader cases, nothing invented.
- Members with very common names (`size`, `data`, `count`): readers restricted to the same class / same file stem.
- Third-party / system code readers: not listed (out of repo).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-701**: Edit-shape hints (US1.1–US1.6) MUST be derived deterministically from the old/new changed lines of a
  changed symbol and attached to its cases, quoting the real expressions; at most 8 per symbol.
- **FR-702**: A removed condition MUST raise the changed symbol's logic case to P1 with sub-reason `removed_guard`.
- **FR-703**: Parameter input classes (US1.7) MUST come from the parameter types of the new declaration and be
  limited to parameters referenced on changed lines (max 4 parameters).
- **FR-704**: Lost-side-effect / coupling cases (US2) MUST carry as evidence the reader symbol and the file:line of
  the read; they are pattern cases (`removed_write`, `setter_readers`, `lock_coupling`, `changed_default`,
  `class_consumer`) ranked after the substantive cases of the same distance.
- **FR-705**: Readers MUST be found deterministically (dependency graph facts first, bounded text search second);
  at most 4 readers per item, at most 3 items per changed symbol; overflow is stated in the case.
- **FR-706**: Sibling-source detection MUST ignore loop conditions and conditions that introduce no new identifier.
- **FR-707**: `inline_change` MUST only be reported for definitions located in header files.
- **FR-708**: The report MUST contain `test_gaps` (changed symbols without an existing test in their impact set);
  the brief, Markdown and HTML outputs MUST show them.
- **FR-709**: `--no-patterns` MUST disable the US2 cases as it does the spec 006 patterns.
- **FR-710**: The seeded benchmark MUST be part of the repository and documented.

### Key Entities

- **Edit shape**: (kind, old text, new text, hint) derived from one old/new line pair or block.
- **State reader**: (state name, reader symbol, file, line, coupling kind) behind a US2 case.
- **Test gap**: changed symbol + reason ("no existing test within N hops").

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-701**: Seeded benchmark: victims named in ≥ 11 of 12 scenarios (baseline 8).
- **SC-702**: Seeded benchmark: concrete corner hinted in ≥ 10 of 12 scenarios (baseline 3).
- **SC-703**: Seeded benchmark: victim MRR not lower than baseline (0.295) and the median case count grows by at
  most 50 %.
- **SC-704**: leveldb real-project eval keeps passing; full test suite passes; analysis time on the leveldb eval
  grows by at most 15 %.

## Assumptions

- The RocksDB / vsomeip pilot (spec 004) needs prepared worktrees that are not available in this environment;
  ranking is protected instead by placing every new case kind in the low pattern tier (no change to the order of
  existing cases except the new `removed_guard` P1 on the changed symbol itself, which only moves the changed
  symbol's own case up).
- Hints are additive text; the deterministic case list and its evidence rules (constitution II, III) are unchanged.
