# Plan: Test cases at third-party API boundaries (cycle 5)

## Touch points

| File | Change |
|---|---|
| `src/tcadvisor/ingest/changes.py` | `_FileSymbols._calls` also records, per call, the callee's declaration facts (`CalleeSig`) and whether the result is discarded; stored on `SymInfo.call_sigs` |
| `src/tcadvisor/classify/external.py` (new) | `is_standard(qn, header)`, `signals(sig)` → `(group, hint)` list, `external_risk(calls, contracts)` → one `RiskClassification` |
| `src/tcadvisor/pipeline.py` | `_add_changed_calls` collects third-party calls per root → `root_external`; loads contracts |
| `src/tcadvisor/classify/cases.py` | hop-0 cases also from `root_external` |
| `src/tcadvisor/cli/main.py` | `--contracts FILE` |
| `tests/integration/test_us1_impact.py`, `tests/unit/test_external.py` | fixtures + signal unit tests |
| `README.md`, `.claude/skills/tc-coverage/SKILL.md` | document the contract file |

## Decisions

- Signature facts come from the libclang cursor of the callee (`result_type`, `get_arguments()`,
  `exception_specification_kind`, `mangled_name` for C vs C++ linkage) — no header text parsing.
- "Result discarded": the nearest non-transparent parent of the `CALL_EXPR` is a compound statement.
- Severity order for the case's group: exception_safety > ownership_lifetime > thread_safety > logic.
- JSON (not YAML) for the contract file: no new dependency.
- Ranking: the case sorts like any hop-0 case (key unchanged). If the benchmark drops, the case is ranked as
  low (`LOW_SUBS`) instead.
