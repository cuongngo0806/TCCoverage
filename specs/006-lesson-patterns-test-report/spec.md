# Feature Specification: Lesson-learned impact patterns and a fillable test report

**Feature Branch**: `claude/tc-coverage-app-ww14wt`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Things I want the app to do, from lessons learned: (1) module A → module B →
module C; B and C did not change, but the data produced by A changed, so C trusted the data and sent it out
wrong. Sending correct data is C's responsibility, but because A used to send the right format, C only
forwarded it without checking. (2) One function is triggered from 4 sources. The fix covered only one source;
nobody knew the other 3 sources trigger it the same way, so they were not covered. And many other lessons —
infer which other cases a code change affects. (3) Every code change must be reported: for each TC we test
and record pass / fail / cannot be tested / TC cannot occur, and attach evidence such as screenshots and log
files. Integrate this into the report so we can fill it in directly."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Data that passes through unchanged modules (Priority: P1)

A developer changes how module A builds a piece of data (a field, a message, a returned value, an
out-parameter). Modules B and C are not touched, but C later sends that data outside the module (network,
IPC, file, another component). The advisor follows the changed data from A to every place that forwards it
and to every place that finally emits it, and produces a case on each emitting point: "C emits data that
originates in the changed A — check C validates it (range, format, length, mandatory fields) instead of
trusting A". Intermediate forwarders (B) get a lower-priority case "B passes A's data on without checking".

**Why this priority**: This is the first lesson the team paid for in production: the defect surfaced in an
unchanged module, so a review limited to changed code and its direct callers never looks there.

**Independent Test**: A fixture where A changes a value it writes, B only copies it, and C writes it to an
output call. The report contains a case on C naming the A → B → C path, and a case on B, while neither B
nor C is part of the diff.

**Acceptance Scenarios**:

1. **Given** a change to the value A returns or writes, **When** the advisor runs, **Then** every function
   that receives that value (directly or through intermediate functions, up to the configured depth) and
   passes it to an output point is listed with the full path A → … → C as evidence.
2. **Given** an emitting module C that already validates the data before emitting it, **When** the advisor
   runs, **Then** C's case still appears but states that a check exists on the path and asks to confirm the
   check covers the changed values (lower priority than an unchecked path).
3. **Given** a path the advisor cannot follow (data stored in a container, sent through a queue, callback,
   or a third-party API), **When** the advisor runs, **Then** the break in the path is reported as an
   uncertainty flag naming where tracing stopped, never silently dropped.

---

### User Story 2 - Every trigger source of a shared function (Priority: P1)

A function F is reached from several sources (callers, event handlers, timers, callbacks, message
handlers). A developer fixes a problem by changing one source S1 (for example, adds a guard before calling
F) or by changing F itself. The advisor lists every other source S2…Sn that reaches F, states whether each
one has the same protection as the fixed source, and produces one case per unprotected source: "F is also
triggered from S3 — check the scenario fixed for S1 cannot happen via S3".

**Why this priority**: Second production lesson: a fix covered one of four entry paths. Listing the sibling
sources is cheap for the tool and expensive to discover manually.

**Independent Test**: A fixture with four callers of F; the change adds a check in one caller. The report
contains three sibling-source cases, each naming its own call path, and marks the fixed caller as covered.

**Acceptance Scenarios**:

1. **Given** a change in one caller S1 that adds or alters a condition around its call to F, **When** the
   advisor runs, **Then** the report names F as a shared target and lists every other source reaching F,
   each as a separate case.
2. **Given** a change inside F, **When** the advisor runs, **Then** each distinct source reaching F appears
   as its own entry path (not one merged "callers of F" case), so each can be tested separately.
3. **Given** a source reached only at runtime (callback registration, virtual dispatch, message ID table),
   **When** the advisor runs, **Then** it is listed as a source when the registration is visible in code,
   and as an uncertainty flag otherwise.

---

### User Story 3 - Fillable verification report per change (Priority: P1)

After the advisor runs, the tester opens the generated report, and for every test case records a verdict
(Pass, Fail, Cannot be tested, Cannot occur), a short comment, who tested it and when, and attaches evidence
(screenshots, log files, other files). The completed report is then submitted as the change's verification
record. When the code changes again and the advisor re-runs, verdicts and evidence already recorded for
cases that still apply are carried over and marked "needs re-check" when the related code changed again.

**Why this priority**: The team must produce this record for every change today; doing it by copying the
case list into another document is slow and loses the link between case, code evidence and test evidence.

**Independent Test**: Generate a report for a small change, fill in verdicts and attach two files, export
it, re-run the advisor after a further edit, and confirm the earlier verdicts reappear on the matching cases.

**Acceptance Scenarios**:

1. **Given** a generated report, **When** the tester records a verdict for a case, **Then** the verdict, comment,
   tester name, date and attachments are stored with that case and shown in the exported report.
2. **Given** a verdict "Cannot be tested" or "Cannot occur", **When** the tester saves it, **Then** a
   justification comment is required.
3. **Given** a verdict "Fail", **When** the tester saves it, **Then** at least one evidence attachment or a
   defect reference is required.
4. **Given** a report with cases still unrecorded, **When** the tester exports it, **Then** the export shows
   a summary (counts per verdict, number not yet tested) and clearly marks the report as incomplete.
5. **Given** a re-run on a later revision, **When** a case matches a previously recorded one, **Then** its
   verdict and evidence are carried over; if the code behind that case changed since, the verdict is marked
   "needs re-check".

---

### User Story 4 - Further lesson-learned patterns and team lessons (Priority: P2)

Beyond the two reported lessons, the advisor recognises other recurring "the change was right but something
else broke" patterns and turns each into cases with its own explanation:

- **Symmetric counterpart**: a change to one side of a pair (encode/decode, serialize/deserialize,
  open/close, lock/unlock, register/unregister, start/stop, send/receive, save/load) → check the other side.
- **Same fix needed elsewhere**: the code removed or corrected by the change also exists, with the same
  shape, in other functions → check those copies.
- **New value of an enumeration or status code**: every switch/comparison over that type elsewhere → check
  the new value is handled (and not by a silent default).
- **Changed meaning of a return value or error code**: every caller that tests the result → check its
  decision still holds.
- **Shared state written by the change**: every reader of the same member/global variable → check it
  tolerates the new value and the new timing.
- **New early exit or error path**: resources acquired before it and the callers' clean-up → check nothing
  leaks and the caller handles the new outcome.
- **Configuration / feature flag read by the change**: every other reader of the same setting → check
  consistent behaviour for each value.

The team can also record its own lessons once (a title, the code signal that should trigger it, and the
question to ask), and the advisor adds those lessons to matching cases, labelled as team lessons.

**Why this priority**: Each pattern adds recall for a known class of regression, but the two reported
lessons and the report are the immediate need.

**Independent Test**: One fixture per pattern; each produces a case whose explanation names the pattern
and the counterpart / copy / reader / handler it points to.

**Acceptance Scenarios**:

1. **Given** a change to `encode_x`, **When** a function `decode_x` exists, **Then** a "symmetric
   counterpart" case points to `decode_x`.
2. **Given** a team lesson whose signal matches a changed function, **When** the advisor runs, **Then** the
   lesson's question appears on that function's case, labelled with the lesson title.

### Edge Cases

- A shared function with dozens of sources: sources are grouped (by module / file) and only the top ones by
  relevance are expanded into separate cases; the rest are listed in one case with their count.
- Data paths that loop or fan out widely: tracing stops at the configured depth and reports where it stopped.
- The same case found by two patterns (e.g. a sibling source that also forwards the changed data): one case,
  with both explanations.
- A previously recorded case no longer appears after a re-run: its verdict and evidence are kept in a
  "no longer reported" section, never discarded.
- Very large attachments (long logs, videos): still embedded; the report warns above the size limit and the
  tester may compress or trim the log before attaching.
- An attachment of a type the browser cannot preview: embedded and offered for download, not previewed.
- Report opened on a machine without network access: filling in and exporting must work offline.

## Requirements *(mandatory)*

### Functional Requirements

**Data passing through unchanged modules (US1)**

- **FR-601**: When a change alters a value a function returns, writes through a parameter, stores in a
  member/global, or puts into a message, the advisor MUST trace where that value goes next — into callers,
  callees, and readers — up to the configured depth, independent of whether those functions changed.
- **FR-602**: The advisor MUST identify *emitting points* on those paths (calls that send data out of the
  function's module: network, IPC, file, logging excluded, inter-component interfaces) using a built-in
  list that the team can extend.
- **FR-603**: For each emitting point reached, the advisor MUST produce a case on the emitting function,
  with the full path from the change to the emitting call as evidence, asking whether the emitter validates
  the data itself; forwarding functions in between MUST get a lower-priority case.
- **FR-604**: When a validation (comparison, range check, assertion, early return on the value) exists on
  the path before the emitting point, the case MUST say so and be ranked below unchecked paths.

**Multiple trigger sources (US2)**

- **FR-605**: For every changed function and every function whose call conditions a change altered, the
  advisor MUST list all distinct sources that reach it (direct callers, and the entry points behind them up
  to the configured depth, including callback / handler registrations visible in code).
- **FR-606**: When the change adds or alters a guard in one source, the advisor MUST produce one case per
  other source that lacks an equivalent guard, and mark the changed source as the one already covered.
- **FR-607**: Sources that cannot be resolved statically MUST be reported as uncertainty flags.

**Fillable verification report (US3)**

- **FR-608**: The report MUST provide, per case, fields for verdict (Pass, Fail, Cannot be tested, Cannot
  occur), comment, tester, date, defect reference, and evidence attachments (images, log files, any file).
- **FR-609**: The report MUST enforce: a justification for "Cannot be tested" / "Cannot occur"; evidence or
  a defect reference for "Fail".
- **FR-610**: The fillable report MUST be a single self-contained HTML file that works offline in a browser
  and in the VS Code report view: the tester fills it in place, and saving produces an updated copy of the
  same single file. It MUST also print / export to PDF. Both show a summary of verdict counts and an
  "incomplete" marker when cases remain untested.
- **FR-611**: Evidence attachments MUST be embedded inside the report file, so one file is submitted.
  Images are shown inline, logs and other files can be opened or saved back from the report. The report
  MUST show the total attachment size and warn when it exceeds a configurable limit (default 50 MB).
- **FR-612a**: A re-run of the advisor MUST accept a previously filled report file as input to carry over
  verdicts and evidence (FR-612).
- **FR-612**: Each case MUST keep a stable identity across re-runs (based on the code it points to and the
  reason, not on its list position), so recorded verdicts and evidence carry over; carried-over verdicts on
  code that changed again MUST be marked "needs re-check".
- **FR-613**: Recorded results MUST never alter which cases are generated or how they are ranked; the
  advisor itself never executes tests (constitution VIII).

**Further patterns and team lessons (US4)**

- **FR-614**: The advisor MUST detect the patterns listed in User Story 4 deterministically from code and
  the diff, and each resulting case MUST name its pattern and the counterpart it points to.
- **FR-615**: Teams MUST be able to define their own lessons (title, triggering code signal, question)
  locally; matching lessons are added to the related cases, labelled with the lesson title.

**Cross-cutting**

- **FR-616**: Every new case MUST carry resolvable code evidence; every point where tracing stops MUST
  become an uncertainty flag (constitution II, IV).
- **FR-617**: New cases MUST not lower the recall or the ranking quality measured on the regression
  benchmark (dev and holdout).

### Key Entities

- **Data path**: the chain from a changed producer to an emitting point (producer, forwarders, emitter,
  whether a validation exists, where tracing stopped).
- **Trigger source**: a distinct way to reach a function (caller chain or registration), with a "covered by
  this change" marker.
- **Lesson pattern**: a named reason a case exists (built-in or team-defined), with its explanation and the
  counterpart it points to.
- **Verification record**: per case — verdict, comment, tester, date, defect reference, evidence list,
  "needs re-check" marker, and the case's stable identity.
- **Evidence item**: an attached file (screenshot, log, other) with name, type, size and the case it belongs to.
- **Verification report**: the set of verification records for one change, with summary counts and
  completeness status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-601**: For a change in a producer module, 100% of emitting points reachable within the configured
  depth through unchanged modules appear as cases with their full path (fixture-verified).
- **SC-602**: For a function with N trigger sources, all N appear in the report, and N−1 cases are produced
  when the change protects one source (fixture-verified).
- **SC-603**: A tester can record a verdict with one attachment for a case in under 1 minute, and complete
  and export the report for a 20-case change in under 30 minutes of recording time (excluding test time).
- **SC-604**: After a re-run on a later revision, at least 95% of the verdicts for cases whose code did not
  change are carried over without re-entry.
- **SC-605**: On the regression benchmark, no regression that is surfaced today is lost, and the mean
  reciprocal rank of the later-fixed function does not drop on either the dev or the holdout half.
- **SC-606**: Each built-in lesson pattern produces at least one correct case on its fixture and no case on
  a fixture where the pattern does not apply.

## Assumptions

- Testers fill in the report on their own machines; nothing is uploaded by the advisor (local-first). The
  team submits the completed report (one HTML file, or its PDF print) through its existing process.
- Decided 2026-10-10: report format = self-contained HTML (+ PDF print); evidence = embedded in the file.
- "Cannot occur" means the scenario is impossible in the product as built (e.g. guarded elsewhere); the
  justification records why. It does not remove the case from future runs.
- Default list of emitting points covers common send/write/publish/serialize calls; projects extend it in
  a local configuration file, alongside the existing third-party contracts file.
- Team lessons are maintained by the team in the repository being analysed, in plain text that does not
  require programming.
- Data tracing is bounded by the same depth limit as impact tracing (default 2 hops, configurable), to keep
  run time comparable to today.
- Verdict values are fixed to the four named by the team; additional statuses are out of scope.
