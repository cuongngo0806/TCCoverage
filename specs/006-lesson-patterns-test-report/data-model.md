# Data Model: Lesson-learned impact patterns and a fillable test report

Extends `specs/001-change-impact-test-advisor/data-model.md`; existing entities keep their fields.

## TestCaseCandidate (extended)

| Field | Type | Notes |
|---|---|---|
| `key` | string (12 hex) | Stable identity (research R6). Unique within a report. |
| `code_fingerprint` | string (12 hex) | Hash of the evidence function text at analysis time. |
| `pattern` | string \| null | Lesson pattern behind the case: `data_path_emitter`, `data_path_forwarder`, `sibling_source`, `symmetric_counterpart`, `same_code_elsewhere`, `new_enum_value`, `return_meaning`, `shared_state`, `new_early_exit`, `config_reader`; null for existing case kinds. Also stored as `sub_reason`. |
| `path` | list[PathStep] \| null | Data path (US1) or source chain (US2) shown as evidence. |
| `lessons` | list[string] | Team lesson ids matched (US4). |
| `test_result` | VerificationRecord \| null | Tester's record, present only when results exist. Distinct from `verification` (AI verdict of spec 002), which keeps its name and meaning. |

Validation: `evidence` non-empty and gated (unchanged); `key` unique; `pattern` ∈ list above or null.

## PathStep

| Field | Type | Notes |
|---|---|---|
| `symbol` | SymbolRef | Function at this step. |
| `role` | `producer` \| `forwarder` \| `emitter` \| `source` \| `via` \| `target` | |
| `line` | int | Line of the call / write that moves the value on. |
| `checked` | bool | A condition reads the value in this function before passing it on (US1 FR-604). |
| `detail` | string | e.g. "arg 2 of `send_frame` built from param `msg`". |

## DataPath (US1, internal → cases)

`producer: SymbolRef`, `steps: list[PathStep]`, `emitter_call: str` (callee name), `checked_at:
list[SymbolRef]`, `break: str | null` (reason tracing stopped → uncertainty flag).

## TriggerSource (US2, internal → cases)

`target: SymbolRef` (F), `entry: SymbolRef`, `via: SymbolRef` (immediate caller), `kind: call |
registration`, `covered_by_change: bool`, `guard: present | absent | unknown`, `guard_identifiers:
list[str]`.

## FlowFacts (cache, per TU and function USR)

`params: [name]`, `calls: [{callee_usr, callee_name, line, args: [[source]]}]`, `returns: [{line,
sources}]`, `stores: [{target (member/global name), line, sources}]`, `conditions: [{line, sources}]`,
where `source` = `param:<name>` | `local:<name>` | `member:<name>` | `call:<usr>` | `outarg:<usr>:<k>` |
`literal`. Cached in `flow_facts(tu, args_key, data)`; schema version 2.

## LessonsConfig (`.tcadvisor/lessons.json`, optional)

`sinks: [string]` (names / fnmatch patterns added to the emitter catalogue);
`lessons: [{id, title, when: {tokens_any?: [string], name_glob?: string, path_glob?: string,
sub_reason?: string}, ask: string}]`. Schema: `contracts/lessons-config.schema.json`. Invalid → exit 2.

## VerificationRecord (per case, in the report results block)

| Field | Type | Rules |
|---|---|---|
| `verdict` | `pass` \| `fail` \| `not_testable` \| `cannot_occur` \| null | null = not yet tested |
| `comment` | string | required (non-empty) for `not_testable`, `cannot_occur` |
| `tester` | string | required when `verdict` set |
| `date` | ISO date | required when `verdict` set |
| `defect_ref` | string | `fail` requires `defect_ref` or ≥ 1 attachment |
| `attachments` | list[attachment id] | ids in the report's attachment store |
| `needs_recheck` | bool | set on carry-over when `code_fingerprint` changed |
| `carried_from` | string \| null | `report_key` of the report it came from |
| `updated_at` | ISO datetime | last edit |

State transitions: `untested → {pass, fail, not_testable, cannot_occur}` (any → any by the tester);
carry-over keeps the verdict and sets `needs_recheck` when the fingerprint differs; clearing the verdict
returns to `untested`. Complete = verdict set and rules satisfied.

## EvidenceItem (attachment store)

`id` (sha256 prefix), `name`, `type` (MIME), `size` (bytes), `sha256`, `data` (base64), `added_at`. Same
file attached twice → stored once.

## VerificationReport (results block of `report.html`)

`schema: 1`, `report_key` (hash of commit range + analyzer version), `generated_at`, `results: {case key →
VerificationRecord}`, `orphaned_results: {key → VerificationRecord + last known description}`,
`attachments: {id → EvidenceItem}`, `attachment_warn_mb`, `summary` (derived: counts per verdict,
untested, needs_recheck, incomplete, total attachment bytes). Schema:
`contracts/report-results.schema.json`.
