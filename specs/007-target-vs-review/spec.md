# Spec 007 — Test on target vs. close by code review

**Status**: implemented (first version) · **Constitution**: 1.1.0 (Principle III amendment)

## Problem

The tool is used on embedded C++ code. A large change yields many cases; reviewing and testing all of them
costs too much time. Many risks can only be judged by running on the real device, but some cases can be
settled by reading the code. Users need the tool to separate the cases that **must be tested on the target**
from those an AI reviewer can **close by reading code**, without losing auditability or recall.

## Requirements

- **FR-701** Every case carries a deterministic `verify_by` (`target` | `review`) and, for `target`,
  `target_reasons` — each reason is a risk-group rule or a code pattern hit citing `file:line`.
- **FR-702** `target` when: risk group `thread_safety`, `ownership_lifetime`, `build_config`, or
  `abi_layout/member_change`; a runtime-routing uncertainty flag on the impacted symbol; or the impacted symbol's
  code window / the changed lines of a root it is reached from match a runtime pattern (hardware access,
  interrupt, timing, RTOS / threads, bus / network I/O, memory layout / byte order). `logging` / `test_code`
  cases are always `review`.
- **FR-703** Projects add their own patterns with `analyze --target-patterns FILE` (`{category: regex}`); the file
  content is part of the run-cache key.
- **FR-704** AI verifiers may answer `pass_by_review` with a note and 1-3 `proof` `file:line`. `annotate`
  accepts it only on `verify_by: review` cases whose proof resolves inside the repository; otherwise it is
  downgraded (`weak` for target cases, `needs_info` for missing proof) and a warning is printed.
- **FR-705** Report buckets (md / html / brief / VS Code): **Test on target** (target cases and review cases an
  AI could not close), **Review code** (not reviewed yet), **Closed by code review** (with proof). No case is
  removed, renumbered or re-prioritised; relevance order is kept inside each bucket.
- **FR-706** `verify-pack` / `verify` take `--scope review|all`; `all` packs review cases first.
- **FR-707** Reports without `verify_by` (older versions) treat every case as `target`.

## Success criteria

- **SC-701** Unit tests: reasons cite resolvable lines; gate rejects pass on target cases and without proof.
- **SC-702** Before release, run `scripts/eval_real_project.py` and report the share of cases per bucket;
  recall (miss rate) is unchanged because no case leaves the list.
- **SC-703** Pilot on a real embedded change: the AI-closed cases are spot-checked by a human; any wrong pass
  is recorded as a miss and fixed in the deterministic patterns or the verifier prompt.

## Out of scope

Running tests on the device (constitution VIII); deciding *how* to test on target.
