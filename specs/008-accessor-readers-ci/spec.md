# Feature Specification: Readers behind accessors, robust text scan, and a recall gate in CI

**Feature Branch**: `ccr-f43a06ec-6132n5`

**Created**: 2026-10-11

**Status**: Draft

**Input**: "Continue" (cycle after spec 007): keep the goal — never miss the test cases where a change breaks code
elsewhere — and check that spec 007 generalises beyond the project it was tuned on.

## Evaluation that motivates this spec

`scripts/seeded_regressions.py --set yamlcpp`: 9 seeded side-effect edits on jbeder/yaml-cpp `1e0876c` (a second code
base: `m_` members, accessors in headers, string literals full of braces), ground truth written before any change.

| Measure (commit 6d03510) | yaml-cpp | leveldb dev / holdout (spec 007) |
|---|---|---|
| victim named | **6 / 9** | 12 / 12, 10 / 10 |
| concrete corner hinted | 9 / 9 | 12 / 12, 10 / 10 |
| victim MRR | 0.287 | 0.402, 0.347 |

Corner cases generalise; finding the code that breaks does not. Causes, each confirmed on a report:

1. **Readers behind an accessor**: `m_col` is read by `ostream_wrapper::col()` (an inline getter in a header) and the
   code that misbehaves is the getter's callers (`Emitter::EmitBeginDoc`, `WriteComment`). The same for
   `node_data::is_defined()` and `EmitterState::CurGroupLongKey()`.
2. **Text scan broken by string literals**: `m_stream << "{";` shifts the brace count, so every function after line
   ~240 of `emitter.cpp` is invisible to the text scan that resolves readers, guard scopes and textual changes.
3. **Text scan regression from spec 007**: constructor initialiser lines (`m_comment(false) {}`) are taken as function
   heads, producing readers named `m_comment` / `m_type`.
4. **State written under a changed condition**: `if (childCount % 2 == 0) longKey = false;` with `0` → `1`; the
   readers of `longKey` are not looked for because the write itself did not change.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Robust text scan (Priority: P1)

Function boundaries found by the text scan ignore braces inside string and character literals (including raw strings
on one line and escaped quotes), and a line that is a member initialiser or a plain call is never a function head.

**Acceptance Scenarios**:
1. **Given** a file with `out << "{";` and `out << '}';` inside functions, **Then** every later function is found with
   correct first/last lines.
2. **Given** a constructor with an initialiser list over several lines, **Then** the constructor is one function and
   no initialiser is reported as a function.

### User Story 2 - Readers behind accessors (Priority: P1)

When a reader of changed state is a trivial accessor (a function whose body only returns the member, possibly through
`.get()`, `->field`, a comparison or `!`), the callers of that accessor are listed as readers too, with the call site as
evidence ("reads `m_col` through `col()`").

**Acceptance Scenarios**:
1. **Given** `m_col = 0;` removed and `int col() const { return m_col; }` in the header, **Then** callers of `col()`
   get `removed_write` cases naming the accessor.
2. **Given** an accessor with logic (more than one statement), **Then** it is a normal reader and its callers are not
   expanded.

### User Story 3 - State written under a changed condition (Priority: P2)

When a condition changed its operator / constant / logical operator / negation, or was removed, members and fields
written inside that condition's scope get their readers listed (`conditional_write`, low tier, ≤ P2): the write now
happens in different states.

**Acceptance Scenarios**:
1. **Given** `if (n % 2 == 0) g->longKey = false;` with `0` → `1`, **Then** readers of `longKey` (and, via US2, the
   callers of its accessor) get a case.

### User Story 4 - Recall gate in CI (Priority: P2)

A CI workflow runs the unit/integration suite on every push and pull request, and the leveldb eval plus the seeded
benchmark (all sets), failing when the victims-named or corners-hinted counts drop below the committed thresholds.

**Acceptance Scenarios**:
1. **Given** a change that loses a victim in the seeded benchmark, **Then** the CI job fails and prints the scenario.
2. **Given** `scripts/seeded_regressions.py --min-victims N --min-corners M`, **Then** the exit code reflects the
   thresholds (per set) instead of requiring 100 %.

### Edge Cases
- Accessor called from hundreds of places: callers capped (same cap as readers), the rest counted.
- Multi-line string literals / raw strings spanning lines: best effort, never a crash.
- Accessor that is virtual or overloaded: callers taken from the graph by the accessor's symbol only.

## Requirements *(mandatory)*

- **FR-801**: The text scan MUST mask string / char literal contents before counting braces.
- **FR-802**: A line starting with `:` or `,`, or a candidate head without a return type that is not a qualified
  (`A::f`) / destructor name, MUST NOT start a function.
- **FR-803**: Trivial accessors among readers MUST be expanded to their graph callers (≤ 4 per item), evidence = call
  site, description names the accessor.
- **FR-804**: `conditional_write` MUST be produced only for condition-shaped edits and only for writes inside the
  condition's scope; ≤ 3 items per changed symbol; respects `--no-patterns`.
- **FR-805**: `scripts/seeded_regressions.py` MUST accept per-set minimum thresholds and the yaml-cpp set.
- **FR-806**: A CI workflow MUST run pytest, the leveldb eval and the seeded benchmark with thresholds.

## Success Criteria *(mandatory)*

- **SC-801**: yaml-cpp: victims named ≥ 8 / 9 (baseline 6), corners stay 9 / 9, MRR not lower than 0.287.
- **SC-802**: leveldb dev and holdout do not get worse on any of the three measures.
- **SC-803**: Full suite and leveldb eval pass; total benchmark time grows ≤ 15 %.

## Assumptions

- yaml-cpp scenarios count as a holdout for this cycle; its ground truth was fixed before implementation.
- GitHub Actions is the CI (repository is on GitHub); network access in CI is available for clones.
