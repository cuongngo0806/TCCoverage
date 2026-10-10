# Research: Lesson-learned impact patterns and a fillable test report

## R1 — How to follow changed data from A through B to C (US1)

- **Decision**: per-function def-use facts from libclang (new `index/flow.py`), chained across call edges
  that the impact graph already has. Facts per function: parameters; for every call site — the callee, and
  for each argument the set of *sources* it is built from (parameter `p`, local `v`, member `this->m`,
  result of call `X`, literal); return statements with their sources; assignments to members/globals; the
  conditions (if/while/switch/assert/early return) that read each source, with line numbers. Locals are
  resolved by a single forward pass over the function body (`v = expr` adds expr's sources to `v`;
  member access `msg.f` and address-of keep the base's sources).
- **Chaining**: a value is *tainted* when it is (a) the return value or an out-parameter written by a
  changed function, (b) an argument expression on a changed line, or (c) a member written on a changed
  line. Taint moves: caller-side via "result of call to tainted function" and "out-arg after call";
  callee-side via "argument built from taint → callee parameter k". Depth bound = `--max-hop-depth`
  function boundaries (default 2, same as impact), extended by +1 for flow only when the next function is
  an emitter wrapper (keeps cost bounded while still reaching "C sends" in A → B → C).
- **Emitting points**: built-in name catalogue (`send`, `sendto`, `sendmsg`, `write`, `writev`, `fwrite`,
  `publish`, `post`, `notify`, `emit`, `transmit`, `dispatch`, `enqueue`, `serialize`, `deliver`,
  `forward`, case-insensitive substring on the last name component, logging excluded via the existing log
  pattern) + every third-party call (spec 005 `ExternalCall`) + project additions from
  `.tcadvisor/lessons.json` `"sinks"` (exact names or fnmatch patterns).
- **Validation on the path**: a condition reading a tainted source before the emitter call (by line) in
  the emitter or any forwarder → the path is "checked" (case says where; ranked after unchecked).
- **Breaks → flags** (`dynamic_runtime_dependency`): taint stored into a container / queue / member read
  elsewhere, passed to a callback or function pointer, passed to an unresolved callee, or depth reached
  before any emitter while still being forwarded.
- **Rationale**: the needed precision is "does this value reach that send call", not full alias analysis;
  libclang cursors give exact call/argument structure; per-function facts cache well.
- **Alternatives considered**: full interprocedural SSA / clang static analyzer (too slow, not
  incremental, heavy dependency); textual regex over call arguments (misses assignments and member
  chains, too many false paths); asking an LLM (forbidden by constitution III).

## R2 — Flow facts in graph-provider (lite index) mode

- **Decision**: flow facts are extracted on demand only for the TUs that define functions already present
  in the impact graph (roots + nodes up to depth), bounded by `--flow-max-tus` (default 60), cached in a
  new `flow_facts` table keyed by the same TU content hash as `tu_facts` (schema version 1 → 2 drops old
  caches once). Above the bound: no flow cases for the remainder, one run note + one flag per root
  ("data path not traced beyond N translation units").
- **Rationale**: same pattern as the existing libclang fallback for roots missed by codegraph
  (`fallback_max_tus`); keeps the ~1M LOC case fast.
- **Alternatives**: extracting flow facts in the full index for every TU (2–3× index time for all users,
  rejected); codegraph data-flow (not available).

## R3 — Distinct trigger sources and guard comparison (US2)

- **Decision**: sources of F = every caller chain in the graph that reaches F within depth, collapsed to the
  *first* function of the chain (entry) plus the immediate caller (via); address-taken registrations
  (`IndexFacts.address_taken`, codegraph refs) are sources of kind `registration` with their file:line.
  Guard comparison is textual and deterministic: identifiers read in conditions *added* by the change
  around/before the call to F in source S1 (from `SymbolChange.added_lines` + `conditional`
  tokens) form a guard signature; each sibling source body (located with `textual_functions`) is
  scanned for a condition containing ≥ 1 of those identifiers before its call to F. Siblings without it →
  one case each (`sub_reason: sibling_source`); with it → listed as "guard present, confirm equivalent".
- **Dozens of sources**: top 8 by relevance (same module as S1 first, then fan-in, then name) expanded,
  the rest summarised in one case with the count (edge case in spec).
- **Rationale**: the lesson is about *coverage of sources*; listing them is the high-value, low-risk part;
  the guard check only orders and annotates.
- **Alternatives**: semantic equivalence of guards (undecidable in general); treating all callers as one
  case (status quo — exactly what failed).

## R4 — Built-in lesson patterns (US4)

| Pattern (`sub_reason`) | Signal (deterministic) | Counterparts found by |
|---|---|---|
| `symmetric_counterpart` | changed function name contains one side of a pair (encode/decode, serialize/deserialize, pack/unpack, marshal/unmarshal, open/close, lock/unlock, acquire/release, register/unregister, subscribe/unsubscribe, start/stop, init/deinit, connect/disconnect, send/receive, read/write, save/load, push/pop, add/remove, create/destroy) | symbols with the swapped name in the same class/namespace (index or provider refs), else same file stem |
| `same_code_elsewhere` | a removed/changed line of ≥ 25 non-space chars (or ≥ 3 consecutive lines) | `git grep -F -n` of the old normalised text in C++ files; enclosing function via `textual_functions`; max 10 |
| `new_enum_value` | enumerator added (existing `abi_layout` rule) or new status/error constant returned | `uses_type` edges to the enum + `git grep` of `case <Enum>::` / enumerator names; functions with `switch`/`==` on it |
| `return_meaning` | added/changed `return <literal or constant>` in a changed function | callers (graph) whose body compares or branches on the call result (text) |
| `shared_state` | changed line assigns a member / global (`this->m =`, `m_ =`, `g_x =`) | readers: functions in the class's files (and `uses_type` users for globals) that read the same name |
| `new_early_exit` | added `return` / `break` / `throw` / `goto` before the end of a changed function | acquisitions before it in the same function (lock/new/open/alloc tokens) + callers handling the result |
| `config_reader` | changed line reads a setting (`FLAGS_x`, `get_config(...)`, `cfg.x`, `is_*_enabled()`, `*_enabled_`, members of classes named `*Config*/*Options*/*Settings*`) | other readers via `git grep -w` of the setting name; max 10 |

- **Team lessons**: `.tcadvisor/lessons.json` → `lessons: [{id, title, when: {tokens_any, name_glob,
  path_glob, sub_reason}, ask}]`; matching adds `Lesson <id>: <ask>` to the case's corner cases (like
  contracts in spec 005). No code, no model.
- **Rationale**: each signal is cheap and auditable; counterparts are concrete symbols → evidence gate
  passes; text scans are bounded.
- **Alternatives**: clone detection with suffix trees (dependency + cost); semantic config models
  (project-specific → left to team lessons).

## R5 — Case placement in the ranked list

- **Decision**: new cases are hop ≥ 1 by nature (they are about *other* code). They join the existing
  order with their hop and a `low` flag decided by the offline rank lab (as in spec 005): candidates
  (a) like any impacted case, (b) after substantive cases of the same hop, (c) block after hop-1. The
  slot that keeps dev and holdout MRR ≥ base is kept, then confirmed by a full benchmark run. Priority
  labels (P1/P2/P3) follow FR-004a unchanged; data-path emitter cases unchecked = high-severity group
  `logic`→P2 at hop ≥ 2 unless the group is high-severity.
- **Rationale**: CLAUDE.md rule; the spec 005 experience showed that new hop-0 cases cost MRR when placed
  first.

## R6 — Stable case identity and carry-over (FR-612)

- **Decision**: `key = sha1(evidence symbol qualified name | evidence file | risk_group | sub_reason |
  sorted root qualified names | pattern counterpart)[:12]`, independent of list position. A
  `code_fingerprint` per case = sha1 of the comment-stripped text of the evidence function(s) at analysis
  time. Carry-over: results from `--previous-report` copied by `key`; if the fingerprint differs →
  `needs_recheck: true`; results whose key no longer exists go to `orphaned_results` (shown in a
  "No longer reported" section, never discarded). `TC-####` display ids stay positional.
- **Rationale**: positional ids change with every ranking tweak; qualified names + reason are stable
  across unrelated edits; fingerprint answers "did the code behind this case change?" cheaply.
- **Alternatives**: USR-based keys (USRs change with signature changes, not available in provider mode);
  line-based keys (move with every edit above).

## R7 — Fillable single-file HTML with embedded evidence (FR-608…611)

- **Decision**: extend the existing self-contained `report.html` (data in `<script type=application/json
  id=data>`). Add `<script type=application/json id=results>` holding `{schema, report_key, results:{key:
  record}, attachments:{id: {name, type, size, sha256, data(base64)}}}`. UI: per case a collapsible form
  (verdict radio, comment, tester, date default today, defect ref, file input — FileReader → base64,
  drag & drop). *Save*: serialise the current document with the updated results block into a new HTML
  string → `Blob` download `report-<change>-<date>.html` (browser) or `postMessage` → extension
  `showSaveDialog` + `fs.writeFile` (VS Code webview, where downloads are blocked). Tester name remembered
  in `localStorage` (convenience only). Print: `@media print` layout — summary table, every case with
  verdict, comment, inline images, attachment list (name, size, sha256) and first 40 lines of text logs.
- **Validation**: client-side rules of FR-609 block marking a case complete; the summary counts
  incomplete records; Python `report/results.py` re-validates on `--previous-report` read (bad records
  kept, flagged in run notes).
- **Size**: total attachment bytes shown; warning above `--attachment-warn-mb` (default 50, stored in the
  report); no hard limit (FR-611 says embed).
- **Rationale**: one file to submit (Q1: B, Q2: A); works offline; no new dependency; reuses the current
  report.
- **Alternatives**: IndexedDB-only storage (not submittable); separate evidence folder (rejected by Q2);
  PDF generation in Python (needs a dependency; browser print covers it).

## R8 — Validating the HTML form in tests

- **Decision**: unit-test the results reader/writer in Python; one integration test drives the form with
  Playwright + the pre-installed Chromium (`/opt/pw-browsers`) when importable (fill verdict, attach a
  file, save, re-load the saved file, check JSON) and is skipped otherwise; no npm build step for the
  report.
- **Rationale**: keeps the core suite dependency-free while still exercising the real UI where possible.
