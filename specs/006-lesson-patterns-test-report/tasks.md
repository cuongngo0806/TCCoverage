---
description: "Tasks for spec 006 — lesson-learned impact patterns and a fillable test report"
---

# Tasks: Lesson-learned impact patterns and a fillable test report

**Input**: `specs/006-lesson-patterns-test-report/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: included — spec success criteria SC-601, SC-602, SC-606 are fixture-verified and SC-605 is the benchmark gate.

**Organization**: by user story. Delivery order follows plan.md: US3 (report, MVP) → US2 (sources) → US1 (data paths) → US4 (patterns). Task ids use the 6xx range of this spec.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 data paths · US2 trigger sources · US3 fillable report · US4 lesson patterns

---

## Phase 1: Setup

- [x] T601 Add `--previous-report`, `--lessons`, `--flow-max-tus` (default 60), `--no-patterns`, `--attachment-warn-mb` (default 50) to `Options` in `src/tcadvisor/pipeline.py` and `analyze` in `src/tcadvisor/cli/main.py`; add them to `specs/001-change-impact-test-advisor/contracts/cli-contract.md` (per `contracts/cli.md`)
- [x] T602 [P] Add `.tcadvisor/lessons.json` loader `load_lessons(repo, explicit) -> LessonsConfig` (validate against `contracts/lessons-config.schema.json` by hand, no jsonschema at runtime; invalid → `UsageError`, exit 2) in `src/tcadvisor/classify/lessons.py`; include `lessons` content in the run-cache key in `src/tcadvisor/pipeline.py`

---

## Phase 2: Foundational (blocks every story)

- [x] T603 Extend `TestCaseCandidate` in `src/tcadvisor/models.py` with `key: str`, `code_fingerprint: str`, `pattern: str | None`, `path: list[PathStep] | None`, `lessons: list[str]`, `test_result: dict | None` and add `PathStep` dataclass (`symbol`, `role` ∈ `producer|forwarder|emitter|source|via|target`, `line`, `checked`, `detail`); emit them in `to_dict()`
- [x] T604 Compute stable `key = sha1(evidence qualified name | evidence file | risk_group | sub_reason | sorted root qualified names | pattern counterpart)[:12]` and `code_fingerprint = sha1(comment-stripped text of the evidence function)[:12]` for every case after ranking in `src/tcadvisor/classify/cases.py` (helper reads source lines via `textual_functions`); keys must be unique (suffix `-2`, `-3` on collision)
- [x] T605 [P] Extend `specs/001-change-impact-test-advisor/contracts/output-schema.json` with the new case fields and the optional top-level `test_results` block (`$ref` to `specs/006-lesson-patterns-test-report/contracts/report-results.schema.json` content inlined)
- [x] T606 [P] Unit tests: key stable across re-ordering and unrelated edits, fingerprint changes when the evidence function body changes, in `tests/unit/test_case_keys.py`

**Checkpoint**: every case has a stable key; schema test (`tests/integration/test_schema.py`) passes.

---

## Phase 3: User Story 3 — Fillable verification report (P1) 🎯 MVP

**Goal**: testers record verdict / comment / tester / date / defect / embedded attachments per case in `report.html`, save one file, re-run carries results over.

**Independent test**: quickstart S4 (fill, save, reopen, `tcadvisor results`, re-run with `--previous-report`).

- [x] T607 [P] [US3] Results block reader/writer in `src/tcadvisor/report/results.py`: `read_results(html_path) -> dict` (parse `<script type="application/json" id="results">`, schema 1, else `UsageError`), `validate_record(rec) -> list[str]` (rules: verdict ∈ `pass|fail|not_testable|cannot_occur|null`; "comment … required (non-empty) for `not_testable`, `cannot_occur`"; "tester … required when `verdict` set"; "date … required when `verdict` set" as `YYYY-MM-DD`; "`fail` requires `defect_ref` or ≥ 1 attachment"), `summary(block, cases) -> dict` (counts per verdict, untested, needs_recheck, incomplete, total attachment bytes)
- [x] T608 [US3] Carry-over in `src/tcadvisor/report/results.py`: `carry_over(previous, cases, report_key) -> block` copies records by `key`, sets `needs_recheck: true` when `code_fingerprint` differs (store fingerprint in each record as `fingerprint`), `carried_from` = previous `report_key`, moves unknown keys to `orphaned_results` with `last_description`, keeps only referenced attachments; wire `--previous-report` in `src/tcadvisor/pipeline.py` (report gets `test_results`, each case `test_result`)
- [x] T609 [US3] Fillable form in `src/tcadvisor/report/html.py` per `contracts/report-form.md`: per-case panel (verdict radios Pass / Fail / Cannot be tested / Cannot occur / Clear, comment, tester remembered in `localStorage` inside try/catch, date default today, defect ref, file input + drag & drop → FileReader base64, dedupe by sha256 via `crypto.subtle`, inline image preview, remove), inline rule messages, badges (verdict, needs re-check, carried over), `#results` JSON block, results filters, "No longer reported" section
- [x] T610 [US3] Report-level UI in `src/tcadvisor/report/html.py`: summary bar (counts, incomplete banner, total attachment size + warning above `attachment_warn_mb`), *Save report* (serialise document with updated `#results` → Blob download `report-<short-commit>-<YYYYMMDD-HHMM>.html`; inside VS Code webview `acquireVsCodeApi().postMessage({type:"saveReport", html})`), `beforeunload` warning on unsaved changes, `@media print` layout (summary, every case with verdict fields, inline images, attachment list with sha256, first 40 lines of text attachments)
- [x] T611 [P] [US3] VS Code: handle `saveReport` message in the report webview of `vscode-extension/src/extension.ts` (`showSaveDialog` default next to the report, `workspace.fs.writeFile`), enable scripts + file input in the webview options; `npm run compile` passes
- [x] T612 [P] [US3] Verdict columns in `src/tcadvisor/report/render.py`: Markdown case lines and `--print brief` lines end with `[PASS|FAIL|N/T|N/O|—]` and `(re-check)`; summary line `test results: … pass / … fail / … n/t / … n/o / … untested`
- [x] T613 [US3] `tcadvisor results <report.html> [--json]` subcommand in `src/tcadvisor/cli/main.py` (prints summary + incomplete/failing cases; exit 0 complete, 4 incomplete or any fail)
- [x] T614 [P] [US3] Unit tests for reader, validation rules, summary, carry-over (fingerprint change → needs_recheck, vanished key → orphaned) in `tests/unit/test_results.py`
- [x] T615 [US3] Integration test in `tests/integration/test_us6_report.py`: analyze → inject a results block into `report.html` → `tcadvisor results` exit codes → edit code → re-run with `--previous-report` → carried / needs_recheck / orphaned as expected; Playwright scenario (fill Fail + attach file, save, reopen, check block) skipped when Playwright is not importable

**Checkpoint**: US3 usable on its own — the team can fill and submit reports.

---

## Phase 4: User Story 2 — Every trigger source of a shared function (P1)

**Goal**: list every distinct source reaching a changed / guarded function; one case per uncovered sibling source.

**Independent test**: quickstart S2 (four sources, guard added in one).

- [x] T616 [P] [US2] Fixture in `tests/conftest.py`-compatible helper `tests/integration/fixtures_us6.py`: `F::handle_timeout` reached from `on_timer`, `on_disconnect`, `on_error` and a callback registered in `setup()` (function pointer)
- [x] T617 [US2] `src/tcadvisor/graph/sources.py`: `sources_of(graph, target, depth) -> list[TriggerSource]` (caller chains collapsed to entry + immediate caller; `facts.address_taken` registrations as `kind: registration`), `guard_signature(change, target_name) -> set[str]` (identifiers in conditions on added lines before the call to target), `has_guard(repo, source, ids, target_name) -> present|absent|unknown` using `textual_functions` on the source file
- [x] T618 [US2] Targets in `src/tcadvisor/pipeline.py`: (a) every changed function → its own sources; (b) every function called on a changed line whose call is under an added condition → its sources, the changed caller marked `covered_by_change`; build cases `pattern/sub_reason: sibling_source` (evidence = source entry symbol, `path` = entry → via → target, risk group of the target root, hop = hop of the source node) in `src/tcadvisor/classify/cases.py`; top 8 expanded by (same module as covered source, fan-in, name), rest summarised in one case with the count
- [x] T619 [US2] Unresolvable sources (virtual-only, no caller, codegraph boundary) → `di_config_routing` / `dynamic_runtime_dependency` flags naming the target in `src/tcadvisor/evidence/uncertainty.py`
- [x] T620 [P] [US2] Tests: unit `tests/unit/test_sources.py` (guard signature, has_guard), integration `tests/integration/test_us6_sources.py` (three sibling cases, covered source marked, guard-present sibling listed as "confirm equivalent")

---

## Phase 5: User Story 1 — Data that passes through unchanged modules (P1)

**Goal**: changed data followed from producer A through forwarders B to emitters C; cases on C (and B), flags where tracing stops.

**Independent test**: quickstart S1.

- [x] T621 [P] [US1] Fixture modules A/B/C in `tests/integration/fixtures_us6.py`: `A::build_status` writes `Frame::code`, `B::relay(const Frame&)` passes it on, `C::publish(const Frame&)` calls `transport_send(buf, len)`; variants with a check in C and with a `std::deque` in B
- [x] T622 [US1] `src/tcadvisor/index/flow.py`: `extract_flow(tu, path) -> {usr: FlowFacts}` per data-model (params; calls with per-argument sources; returns; stores to members/globals; conditions with sources and lines) using one forward pass over each function body; source kinds `param:`, `local:`, `member:`, `call:<usr>`, `outarg:<usr>:<k>`, `literal`
- [x] T623 [US1] Cache flow facts: `flow_facts` table, `SCHEMA_VERSION = 2`, `get_flow/put_flow` keyed like `tu_facts` in `src/tcadvisor/cache/store.py`; on-demand extraction for TUs defining roots + impact nodes, bounded by `--flow-max-tus` (note + one flag per root beyond the bound) in `src/tcadvisor/pipeline.py`
- [x] T624 [US1] `src/tcadvisor/graph/dataflow.py`: taint seeds (returns / out-params / member stores / call arguments on changed lines), propagation across call edges (result of tainted call; argument → callee parameter k) up to `max_hop_depth` (+1 into an emitter wrapper), emitter detection (built-in catalogue of research R1 + spec 005 third-party calls + `lessons.json` `sinks`; logging excluded), `checked` when a condition reads the taint before the next call, breaks (container/queue methods `push*|emplace*|insert|enqueue`, callback/function-pointer args, unresolved callee, depth) → `DataPath.break`
- [x] T625 [US1] Cases `data_path_emitter` (evidence = emitter function + path edges; unchecked before checked) and `data_path_forwarder` (lower: `low` slot) in `src/tcadvisor/classify/cases.py`; breaks → `dynamic_runtime_dependency` flags with the stop location in `src/tcadvisor/pipeline.py`
- [x] T626 [P] [US1] Tests: unit `tests/unit/test_flow.py` (source extraction for assignment, member access, call result, out-arg), integration `tests/integration/test_us6_dataflow.py` (A→B→C case with full path, checked variant ranked lower, deque variant flagged)

---

## Phase 6: User Story 4 — Further lesson patterns and team lessons (P2)

**Goal**: seven built-in patterns + team lessons from `lessons.json`.

**Independent test**: quickstart S3, one fixture per pattern (+ a negative fixture each, SC-606).

- [x] T627 [P] [US4] `src/tcadvisor/classify/patterns.py`: `symmetric_counterpart` (pair table of research R4, counterpart in same class/namespace via index/provider refs, else same file stem)
- [x] T628 [P] [US4] `same_code_elsewhere` in `src/tcadvisor/classify/patterns.py` (removed/changed line ≥ 25 non-space chars or ≥ 3 consecutive lines; `git grep -F -n` in C++ files at the new revision; enclosing function via `textual_functions`; max 10; exclude the changed function itself)
- [x] T629 [P] [US4] `new_enum_value` and `return_meaning` in `src/tcadvisor/classify/patterns.py` (enumerator added / new returned constant → switch/compare users and branching callers)
- [x] T630 [P] [US4] `shared_state`, `new_early_exit`, `config_reader` in `src/tcadvisor/classify/patterns.py`
- [x] T631 [US4] Team lessons matching (`tokens_any`, `name_glob`, `path_glob`, `sub_reason`) → `Lesson <id>: <ask>` corner cases + `lessons` field in `src/tcadvisor/classify/lessons.py`; wire patterns + lessons into `src/tcadvisor/pipeline.py` (respect `--no-patterns`)
- [x] T632 [P] [US4] Tests: `tests/unit/test_patterns.py` and `tests/integration/test_us6_patterns.py` (positive + negative per pattern; lesson match)

---

## Phase 7: Polish, ranking gate & cross-cutting

- [x] T637 Merge duplicate cases found by two patterns (same evidence symbol + risk group): one case, both explanations and corner cases, `pattern` = first, others listed in the description, in `src/tcadvisor/classify/cases.py` (spec edge case)
- [ ] T633 Offline rank lab over benchmark reports with and without new cases (slots of research R5) in `scripts/rank_lab.py` (new `--new-cases` variant), choose the slot that keeps dev and holdout MRR ≥ base
- [ ] T634 Full benchmark (`scripts/pilot_regressions.py`, spec 004 pairs, codegraph) with and without `--no-patterns`; record recall, MRR all/dev/holdout, median cases, median time in `specs/006-lesson-patterns-test-report/results.md` (gate: no surfaced regression lost, MRR not lower, time ≤ +25%)
- [ ] T635 [P] Docs: README section "Lessons-learned cases and the test report", `.claude/skills/tc-coverage/SKILL.md` (how to present sibling-source / data-path cases and the report), `CLAUDE.md` layout lines
- [ ] T636 Full suite `python3 -m pytest -q`, review diff (code-review lens), quickstart S1–S4 by hand on the fixture, commit and push

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → stories. T603/T604 (case key) block US3 and every story's case construction.
- US3 (Phase 3) depends only on Phase 2 → MVP.
- US2 (Phase 4) and US1 (Phase 5) are independent of each other; both feed `classify/cases.py` (do T618 and T625 sequentially).
- US4 (Phase 6) uses `lessons.json` (T602) and, for `return_meaning`, the graph only; independent of US1/US2.
- Phase 7 after all stories (ranking needs every new case kind).

## Parallel Examples

- Phase 2: T605 ∥ T606 after T603/T604.
- US3: T607 ∥ T611 ∥ T612 ∥ T614; then T608 → T609 → T610 → T613 → T615.
- US2 ∥ US1 fixtures: T616 ∥ T621; T617 ∥ T622.
- US4: T627 ∥ T628 ∥ T629 ∥ T630, then T631 → T632.

## Implementation Strategy

1. MVP = Phases 1–3 (fillable report with stable keys) → usable immediately for the team's change reports.
2. Add US2 (cheap, directly addresses lesson #2), then US1 (lesson #1, biggest analysis piece).
3. US4 patterns last; each detector is independent and can ship one by one.
4. Ranking gate (Phase 7) before declaring the feature done; any new case kind that lowers MRR moves to a later slot.
