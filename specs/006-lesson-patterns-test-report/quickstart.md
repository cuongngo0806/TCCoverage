# Quickstart / validation scenarios (spec 006)

Prerequisites: `pip install -e '.[dev]'`, cmake + clang (fixture), optional Playwright + Chromium for the
form scenario. Fixture project: `tests/conftest.py` (extended with modules A/B/C and a four-source
function). All commands analyse a commit range of the fixture repo `R` built in `B`.

## S1 — A → B → C data path (US1)

1. Change only how `A::build_status()` fills `Frame::code` (A writes, B `relay()` copies, C `publish()`
   passes it to `transport_send()`).
2. `tcadvisor analyze --repo R --build-dir B --commit-range HEAD~1..HEAD --print brief`
3. Expect: a case with `pattern: data_path_emitter` on `C::publish` whose `path` is
   `A::build_status (producer) → B::relay (forwarder) → C::publish (emitter, transport_send)`, and a
   lower-ranked `data_path_forwarder` case on `B::relay`; neither B nor C changed.
4. Add `if (f.code > kMax) return;` in `C::publish` (no other change to A's commit) → the emitter case says
   "checked in `C::publish`" and ranks below unchecked paths.
5. Make B push the frame into a `std::deque` instead → a `dynamic_runtime_dependency` flag "data path from
   `A::build_status` stored in container at B.cpp:<line>; not traced further".

## S2 — Four trigger sources (US2)

1. `F::handle_timeout()` is called from `on_timer`, `on_disconnect`, `on_error` and a callback registered in
   `setup()`; the change adds `if (!session_) return;` before the call in `on_timer` only.
2. Expect: three `sibling_source` cases (`on_disconnect`, `on_error`, registration in `setup`), each with
   its own source chain as `path`, and `on_timer` reported as covered by the change.
3. Add the same guard to `on_error` in the commit → two sibling cases remain; `on_error` listed as
   "guard present, confirm equivalent".

## S3 — Lesson patterns and team lessons (US4)

- Change `encode_frame` → `symmetric_counterpart` case on `decode_frame`.
- Fix a line that also exists verbatim in another function → `same_code_elsewhere` case on that function.
- Add an enumerator to `State` → `new_enum_value` cases on functions switching over `State`.
- Add `.tcadvisor/lessons.json` with `{"lessons":[{"id":"L7","title":"Unit conversion","when":{"tokens_any":["ms","sec"]},"ask":"Check every caller passes milliseconds"}]}`
  → matching cases list `Lesson L7: Check every caller passes milliseconds`.

## S4 — Fill, save, re-run (US3)

1. Open `OUT/report.html` in a browser. For TC-0001 choose *Fail* → the form blocks completion until a
   defect reference or attachment is added; attach `screenshot.png` and `app.log`.
2. Mark TC-0002 *Cannot occur* without a comment → blocked; add a reason → complete.
3. Click *Save report* → a new `report-<commit>-<date>.html` is downloaded; reopening it shows both
   verdicts, the inline screenshot, the log in the attachment list, summary "1 fail / 1 n/o / N untested",
   "Incomplete" banner.
4. `tcadvisor results report-<...>.html` → prints the summary, exit 4 (incomplete / fail).
5. Edit the function behind TC-0002, commit, re-run with `--previous-report report-<...>.html` → TC-0001's
   result carried over unchanged, TC-0002's marked `needs re-check`; a case that disappeared is in
   "No longer reported".
6. Print to PDF → summary + every case with verdicts, image inline, attachment list with sha256.
7. VS Code: *TC Coverage: Show Report* → fill a verdict → *Save report* opens a save dialog.

## S5 — Benchmark gate (FR-617 / SC-605)

`scripts/pilot_regressions.py` on the spec 004 pairs (see `specs/005-external-api-cases/results.md` for the
setup) with and without `--no-patterns`: no regression lost; dev and holdout MRR not lower; median time
within +25%. Results recorded in `specs/006-lesson-patterns-test-report/results.md`.
