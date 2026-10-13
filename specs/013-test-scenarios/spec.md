# Feature Specification: Test scenarios — fewer, focused, visual test plan

**Feature Branch**: `013-test-scenarios`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "Real-project feedback (human-test/remotecontrolapp). (1) Test cases carry too much
text and no focus — the reader must see at a glance which tests to run now; visualize the plan. (2) Many cases
repeat: one test run along a call flow (entry → … → changed function) covers several TCs (e.g. TC-0153
processRxResSig → TC-0018 checkEndF → TC-0001 determineResSuspend share identical corner cases). Recompute:
group cases into deterministic test scenarios (one runnable test each) covering several TCs, dedupe their checks,
show a scenario-first plan in md/html/brief with flow visuals, keep the per-case detail (evidence) below. Also cut
noise found in the same run: include guards (#ifndef X_H after a multi-line license comment) are flagged as
build_config_incomplete_macro and make cases 'needs target'."

## Context — what the pilot showed

Run `human-test/remotecontrolapp/20261013-124545-61ffe19_cb62fef` (one commit, 6 files, 244 cases, 237 closed by
AI, 7 left to test):

- The 7 remaining cases are 3 call flows, not 7 tests: `processRxResSig → checkEndF → determineResSuspend`
  (TC-0153, TC-0018, TC-0001), `handleMessage → processOrderResp` (TC-0017, TC-0005), plus `completeFeature`
  (TC-0006) and the class member change (TC-0012). The rule corner cases of TC-0001/0018/0153 are word-for-word
  identical; each case prints 5–8 lines (When / Evidence / Corner / Target / AI / AI corners).
- Before the AI filter the same run has 244 cases; 35 of them are "method X of the changed class `rca::Feature`"
  (`contains`), 24 are "file includes the changed header" — one rebuild + one run covers each family.
- All 20 uncertainty flags are include guards (`#ifndef RDL_FEATURE_H`) of headers that start with a multi-line
  license comment; one of them also made TC-0012 "needs the target".

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One runnable test covers a whole call flow (Priority: P1)

A tester opens the report and sees a short list of **test scenarios**. Each scenario is one test to run: where to
trigger it (the entry function), the flow it walks through to the changed code, which test cases (TC ids) it
covers, and a short de-duplicated list of what to check. Cases on the same call flow are no longer separate tests.

**Why this priority**: duplicated cases waste test time and hide the few tests that matter; this is the main
complaint.

**Independent Test**: analyse a fixture where `a()` calls `b()` calls changed `c()`; the report has one scenario
"a → b → c" covering the three cases, with the shared corner cases listed once.

**Acceptance Scenarios**:

1. **Given** cases on one call chain (entry → … → changed function), **When** the report is built, **Then** they
   form one scenario triggered at the outermost function, listing every covered TC id.
2. **Given** a changed function called from two unrelated callers, **When** the report is built, **Then** there are
   two scenarios (one per source) and the changed function's own case is covered by the first, not repeated.
3. **Given** cases that share the same corner-case text, **When** the scenario is shown, **Then** each check appears
   once; generic checks ("exercise every branch…") are dropped when the scenario has concrete ones.
4. **Given** many cases reached through a non-call relation of one changed symbol (class members `contains`,
   header `include`, subclasses `inherit_override`), **When** the report is built, **Then** they form one scenario
   per (changed symbol, relation) with one representative to run and the others listed as covered.
5. **Given** the same analysis run twice, **Then** the scenarios, their order and ids are identical.

---

### User Story 2 - A focused, visual test plan (Priority: P1)

The top of report.md / report.html / brief is the test plan: "N scenarios cover M cases", each scenario on one or
two lines plus its checklist, and a flow picture (entry → … → changed function, changed node highlighted). The
long per-case text (when / evidence / corner / AI note) moves below, folded in the HTML, as the audit trail.

**Why this priority**: the reader must know in seconds which tests to run now.

**Independent Test**: render the pilot report.json; the plan section fits on one screen (≤ 40 lines of text for the pilot, diagram source excluded)
and the per-case detail is still present below with its evidence.

**Acceptance Scenarios**:

1. **Given** a report, **When** report.md is rendered, **Then** a "Test scenarios" section with a flow diagram comes
   before the per-case list, each scenario shows priority, how to run it (target/review), flow, covered TCs and ≤ 6
   checks (more are counted, not dropped from the case detail).
2. **Given** report.html, **Then** scenario cards show the flow as connected boxes (changed function highlighted),
   clicking a covered TC shows that case, and the per-case list stays available below.
3. **Given** the brief, **Then** SCENARIO lines come before the TC lines and the TC lines no longer repeat the
   corner cases already listed under their scenario.
4. **Given** `report_language: vi`, **Then** every new sentence is Vietnamese (catalog), tags stay English.
5. **Given** tester results recorded in the HTML, **Then** marking a scenario records the same verdict on each case
   it covers (per-case results stay the contract).

---

### User Story 3 - No include-guard noise (Priority: P2)

Header include guards are never reported as build-configuration uncertainty, also when the header starts with a
multi-line block comment, and they never make a case "needs the target".

**Independent Test**: a header `/* license \n * ... */ #ifndef X_H #define X_H ... #endif` changed inside the
guard: no `build_config_incomplete_macro` flag, the case is not routed to the target for that reason.

**Acceptance Scenarios**:

1. **Given** a header with a multi-line license comment then `#ifndef X_H / #define X_H`, **When** a line inside
   changes, **Then** no condition is recorded for it.
2. **Given** a real `#ifndef FEATURE_X` (not followed by `#define FEATURE_X`), **Then** it is still flagged.

### Edge Cases

- A case with no call relation and no group partner → a scenario of one case (nothing is lost).
- Cycles (recursion) in the call graph → paths never revisit a node.
- A caller reaching two changed functions → greedy cover picks the path covering most uncovered cases; leftovers
  get their own scenario.
- AI-closed cases are not in the main plan's scenarios; the AI-verified report gets its own scenarios.
- Cases moved to "not built" are not in any scenario.
- Old report.json without scenarios → scenarios are computed at render time from the cases and impact nodes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Scenarios MUST be computed deterministically from the emitted cases and the impact graph (no LLM);
  every case shown in a report part belongs to exactly one scenario of that part.
- **FR-002**: A flow scenario MUST be a single call path entry → … → changed symbol; it covers the cases whose
  node lies on that path. Paths are chosen by greedy set cover (most uncovered cases, then highest priority, then
  name order).
- **FR-003**: Cases reached through a non-call relation MUST be grouped per (changed symbol, relation);
  the representative is the highest-priority, then closest case.
- **FR-004**: A scenario MUST carry: id (`S1`…), priority (best of its cases), action (test on target if any case
  needs the target, else review), entry, flow steps, changed symbol(s), covered case ids/keys, a one-line reason
  and de-duplicated checks (AI corner cases first, then concrete rule corners, generic ones only if nothing else).
- **FR-005**: report.json MUST carry `test_scenarios` (English) for the cases still to test; case-level data and
  evidence are unchanged.
- **FR-006**: report.md, report.html, report.ai-verified.* and the brief MUST show scenarios first with a flow
  visual (mermaid in md, SVG/boxes in html, arrow text in brief) and keep the per-case detail below (folded in
  HTML).
- **FR-007**: New report sentences MUST have `vi` catalog entries.
- **FR-008**: Include guards MUST be recognised after leading block/line comments and blank lines (`#ifndef X` /
  `#if !defined(X)` whose next directive is `#define X`), in both the change ingest and the variant judge.

### Key Entities

- **Test scenario**: one runnable test; id, kind (`flow` | `group`), priority, action, entry, steps, changed,
  cases, reason, checks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the pilot report, the 7 cases to test become ≤ 4 scenarios; all 244 cases (without AI filter)
  become ≤ 40% as many scenarios as cases.
- **SC-002**: In the pilot test plan (md) every scenario takes ≤ 10 lines and the whole plan text (diagram source
  excluded) ≤ 40 lines; no check line appears twice within a scenario.
- **SC-003**: 0 include-guard uncertainty flags on a fixture header with a multi-line license comment.
- **SC-004**: Case emission, priorities and ranking are unchanged (same case ids/keys before/after) — the
  benchmark gates are not affected.

## Assumptions

- Scenarios are a presentation/grouping layer: the case list (the constitution's contract) is kept intact and
  every scenario points to its cases, so evidence stays resolvable.
- A call path is a reasonable proxy for "one test drives all these functions"; the tester still sees every covered
  case to confirm.
- Recording a result per scenario writes per-case results (the results format is not changed).
