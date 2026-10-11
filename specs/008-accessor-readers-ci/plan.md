# Implementation Plan: spec 008

**Branch**: `ccr-f43a06ec-6132n5` | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md)

## Summary
Fix the text scan (`ingest/changes.py` `textual_functions`, `_FN_HEAD`; `graph/sources.py` `guard_scope` uses the same
brace counting), expand trivial accessors among state readers and add `conditional_write` in `classify/patterns.py`,
thresholds + yaml-cpp set in `scripts/seeded_regressions.py`, and `.github/workflows/ci.yml`.

## Technical Context
Python 3.10+, libclang (existing), git; pytest; no new dependency. Performance: ≤ +15 % benchmark time.

## Constitution Check
I–IX ✅: cases only; every new case has evidence (accessor call site / reader line); deterministic (text + graph);
overflow stated; bounded greps; local-first (CI only runs the tool on public repos); English.

## Design
- `mask_literals(line)`: replace the contents of `"..."` and `'...'` (escape-aware) with spaces; used by
  `textual_functions` and `guard_scope` before counting braces and before matching heads.
- `_FN_HEAD` candidates: reject when the stripped line starts with `:` or `,`; when no prefix (return type) precedes
  the name, accept only `A::f`, `A::~A`, `~A` names.
- `patterns._accessor(ref, member, files)`: body (text) has ≤ 1 statement and it is `return <expr>;` where `<expr>`
  mentions the member; then `graph.by_name` → usr(s) of the accessor (same file / qualified name) → `graph.callers`
  → readers (ref, call file, call line), marked `via=<accessor>`.
- `conditional_write`: for shapes in {operator_flip, constant_change, logical_flip, negation_flip, removed_guard} with a
  new-side condition line, `guard_scope(new_body, idx)` → writes in scope (`x = `, `p->f = `, `m_x++`, mutating calls)
  → field name (last identifier of the lhs) → `_readers(..., member_access=True for ->/. fields)` (+ accessor
  expansion).
- Benchmark: `--min-victims SET=N`, `--min-corners SET=N` (repeatable); default = all.
- CI: ubuntu-latest, Python 3.11, `pip install -e .[dev]`, apt clang + cmake, pytest, eval, seeded with thresholds
  from `specs/008-accessor-readers-ci/results.md`.

## Project Structure
```text
src/tcadvisor/ingest/changes.py   # mask_literals, head rules
src/tcadvisor/graph/sources.py    # guard_scope uses mask_literals
src/tcadvisor/classify/patterns.py# accessor expansion, conditional_write
scripts/seeded_regressions.py     # thresholds
.github/workflows/ci.yml
tests/unit/test_textscan.py, tests/integration/test_us8_accessors.py
```
