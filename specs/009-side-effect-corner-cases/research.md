# Research — spec 009

## R1 Pairing old and new lines

- **Decision**: per changed symbol, normalise lines (comments stripped, whitespace collapsed) and run
  `difflib.SequenceMatcher` on old body vs new body (`old_body` / `new_body` added to `SymbolChange`); `replace`
  opcodes with equal length are paired line by line, unequal ones by best `SequenceMatcher.ratio() ≥ 0.5`.
- **Rationale**: the diff hunks already isolate the lines; bodies give order (needed for reorders) and context.
- **Alternatives**: AST diff via libclang (heavier, not available for textual changes) — rejected.

## R2 Edit shapes recognised

| Shape | Detection on a paired (old, new) line or block | Hint |
|---|---|---|
| operator flip | same tokens except one relational/equality operator | equality case of the operands |
| logical flip | `&&`↔`||`, `!` added/removed | each operand true/false combination that flips |
| constant change | same tokens except numeric literal(s) | old, new, ±1 around both |
| removed condition | old line has `if/while/?/assert` condition whose text is in no new line, or a conjunct (`&& x`) dropped | input the condition rejected; P1 `removed_guard` |
| return change | `return A;` → `return B;` | old → new value, input that reaches it |
| reorder | normalised line present in old and new body with relative order to a neighbour statement inverted | later statement must not use state the earlier released/reset/moved |
| removed call / assignment | old line with a call / `x = …` that no new line contains | "no longer done on this path" |
| new deref without null check | added `p->` / `*p` where an old guard on `p` was removed | null input |

## R3 Parameter input classes

- **Decision**: parse the new declaration tokens into parameters (reuse the `rules._signature` splitter);
  classify by type text: `*`/smart pointer → null; `std::string|string_view|Slice|vector|span|map|set|list|array|
  char*` → empty / one / large; signed integral → negative / 0 / max; unsigned / size_t → 0 / max (wrap); bool →
  both; float/double → 0 / negative / NaN; enum (type name known as enum in facts is not required) — skipped.
  Only parameters whose name appears on a changed line; ≤ 4.

## R4 Finding readers of state (US2)

- Members: the graph records uses of a field only as a `uses_type` edge to the class, so readers are found by a
  word-bounded `git grep` restricted to files with the class's file stem (same rule as spec 006 `shared_state`),
  excluding writers (`name =`, `name +=`), the changed symbol, and functions changed in the same diff.
- Globals / `g_` / `s_` / `k` constants: repository-wide grep (bounded).
- Setter → reader: name pairs `SetX/X/GetX`, `setX/getX/x`, `set_x/get_x/x`; readers are graph callers of the
  getter (fallback grep `\bX\s*\(`).
- Lock coupling: members (identifiers ending `_`, `m_…`, `mX`) used in the changed function after the
  added/removed lock line → readers as above, `thread_safety` group.
- Changed default: a changed line in a class/struct or at namespace scope matching `type name = value;` /
  `name{value}` / `#define NAME value` / `constexpr … NAME = …` with a different value → readers of `name`.
- Class consumer: a modified method that writes `member_` (assignment or mutating call `member_.Insert(…)`,
  `push_back`, `insert`, `emplace`, `erase`, `clear`, `Add`, `Put`) → other methods of the same class (by qualified
  scope, from the graph's symbol table) whose body reads that member; low tier.

## R5 Sibling-source noise

- **Decision**: a guard line must be `if`/ternary/`assert` (not `while`/`for`), and must contribute at least one
  identifier that the paired old line did not contain; otherwise it is a boundary tweak, covered by R2 hints.

## R6 Ranking

- New pattern kinds join `PATTERN_LOW_SUBS` (after the substantive cases of the same distance) — the spec 006
  measurement showed this placement keeps MRR on RocksDB/vsomeip. `removed_guard` only changes the priority of the
  changed symbol's own case (hop 0), which already ranks first in its distance bucket.

## R7 Test gaps

- **Decision**: a changed symbol (not test code, not file-level) is a gap when no impact node reached from it
  carries a GoogleTest label (`existing_tests`). Output `test_gaps: [{symbol, reason}]`.
