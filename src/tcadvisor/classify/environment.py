"""Where a case must be verified: on the real target, or possibly by reading code (spec 007).

Deterministic (constitution III): a case is `verify_by = "target"` when its risk can only show up at run time on
the device — concurrency, memory lifetime, data layout of the target ABI, build configuration, runtime-routed
dependencies — or when the impacted code / the changed lines touch hardware, interrupts, timing, RTOS, buses
or byte order. Every reason cites a file:line. All other cases are `verify_by = "review"`: an AI (or human)
reviewer may close them by reading code (`pass_by_review`, see verify/annotate.py) — they are never removed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tcadvisor.models import TestCaseCandidate, UncertaintyFlag, UsageError

# risk group / sub-reason -> why only a run shows the problem
GROUP_REASONS: dict[tuple[str, str | None], str] = {
    ("thread_safety", None): "concurrency: interleavings and timing are only observable when running",
    ("ownership_lifetime", None): "memory lifetime: use-after-free / leaks / dangling references appear at run time",
    ("abi_layout", "member_change"): "data layout: sizeof / alignment / padding depend on the target compiler and ABI",
    ("build_config", None): "build configuration: behaviour depends on the macros / options of the target build",
}
# sub-reasons that never need the device by themselves (log text, the test itself)
REVIEW_SUBS = {"logging", "test_code"}
RUNTIME_FLAGS = {"dynamic_runtime_dependency", "di_config_routing", "build_config_incomplete_macro"}

PATTERNS: dict[str, str] = {
    "hardware access": r"\bvolatile\b|\b(?:__asm__|__asm|asm)\b|\(\s*\w+\s*\*\s*\)\s*0x[0-9a-fA-F]{4,}"
                       r"|reinterpret_cast\s*<[^>]*\*\s*>\s*\(\s*0x|\b(?:HAL|LL)_[A-Z]\w*"
                       r"|\b(?:GPIO|UART|USART|SPI|I2C|DMA|ADC|DAC|PWM|NVIC|SysTick|RCC|EEPROM)\w*"
                       r"|\b(?:ioctl|mmap|munmap)\s*\(|\"/dev/|\b\w*(?:reg_read|reg_write|read_reg|write_reg)\w*",
    "interrupt": r"\b\w*(?:IRQHandler|_isr|_ISR)\b|\bISR\s*\(|\b(?:__disable_irq|__enable_irq|local_irq_\w+"
                 r"|disable_irq|enable_irq|irq_\w+|portENTER_CRITICAL\w*|portEXIT_CRITICAL\w*|taskENTER_CRITICAL\w*"
                 r"|taskEXIT_CRITICAL\w*)\b|__attribute__\s*\(\(\s*(?:interrupt|isr)",
    "timing": r"\b(?:sleep|usleep|nanosleep|sleep_for|sleep_until|delay|delay_ms|delay_us|udelay|mdelay|msleep"
              r"|HAL_Delay|vTaskDelay|vTaskDelayUntil|osDelay|k_sleep|k_msleep|steady_clock|system_clock"
              r"|high_resolution_clock|clock_gettime|gettimeofday|setitimer|xTimer\w+|osTimer\w+|timerfd_\w+)\b"
              r"|\b\w*(?:[Tt]imeout|TIMEOUT|[Ww]atchdog|WATCHDOG|WDT|[Dd]eadline)\w*",
    "RTOS / threads": r"\b(?:xTask\w+|xQueue\w+|xSemaphore\w+|xEventGroup\w+|osThread\w+|osMutex\w+|osSemaphore\w+"
                      r"|osMessageQueue\w+|k_thread_\w+|k_sem_\w+|k_mutex_\w+|k_msgq_\w+|pthread_\w+"
                      r"|sem_(?:wait|post|timedwait)|__sync_\w+|__atomic_\w+|__DMB|__DSB|__ISB"
                      r"|atomic_thread_fence)\b|\bstd::(?:thread|async|atomic)\b",
    "bus / network I/O": r"\b(?:socket|recvfrom|sendto|sendmsg|recvmsg|setsockopt|epoll_\w+|tcsetattr|tcgetattr"
                         r"|cfsetispeed|cfsetospeed)\s*\(|\b(?:can|CAN|lin|LIN)_[A-Za-z]\w*",
    "memory layout / byte order": r"#\s*pragma\s+pack|__attribute__\s*\(\(\s*(?:packed|aligned|section)"
                                  r"|\balignas\s*\(|\b(?:htons|htonl|ntohs|ntohl|htobe\d+|be\d+toh|htole\d+"
                                  r"|le\d+toh|__builtin_bswap\d+|bswap_\d+)\b",
}
_COMMENT = re.compile(r"//.*$|/\*.*?\*/")
WINDOW_BEFORE, WINDOW_MAX = 3, 40
MAX_REASONS = 6


def load_patterns(path: Path | None) -> dict[str, re.Pattern[str]]:
    """Built-in patterns plus an optional project file `{"<category>": "<regex>", ...}` (e.g. own HAL names)."""
    pats = dict(PATTERNS)
    if path:
        try:
            extra = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(extra, dict):
                raise ValueError("expected a JSON object {category: regex}")
            for k, v in extra.items():
                pats[str(k)] = f"(?:{pats[str(k)]})|(?:{v})" if str(k) in pats else str(v)
            compiled = {k: re.compile(v) for k, v in pats.items()}
        except (OSError, ValueError, re.error) as exc:
            raise UsageError(f"cannot use --target-patterns {path}: {exc}") from exc
        return compiled
    return {k: re.compile(v) for k, v in pats.items()}


def _scan(lines: list[tuple[str, int, str]], patterns: dict[str, re.Pattern[str]], prefix: str = "") -> list[str]:
    """`category: <match> at file:line` for the first hit of each category."""
    out, seen = [], set()
    for rel, n, text in lines:
        code = _COMMENT.sub("", text)
        for cat, rx in patterns.items():
            if cat in seen:
                continue
            m = rx.search(code)
            if m:
                seen.add(cat)
                out.append(f"{prefix}{cat}: `{m.group(0).strip()[:40]}` at {rel}:{n}")
    return out


def _window(repo: Path, rel: str, line: int, cache: dict[str, list[str]]) -> list[tuple[str, int, str]]:
    """The symbol body (brace-matched, at most WINDOW_MAX lines) — same window the AI verifier sees."""
    if rel not in cache:
        try:
            cache[rel] = (repo / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            cache[rel] = []
    src = cache[rel]
    out, depth, opened = [], 0, False
    for n in range(max(1, line), min(len(src), line + WINDOW_MAX - 1) + 1):
        text = src[n - 1]
        out.append((rel, n, text))
        depth += text.count("{") - text.count("}")
        opened = opened or "{" in text
        if opened and depth <= 0:
            break
    return out


def assign(cases: list[TestCaseCandidate], repo: Path, root_lines: dict[str, list[tuple[str, int, str]]],
           node_roots: dict[str, set[str]], flags: list[UncertaintyFlag],
           patterns: dict[str, re.Pattern[str]]) -> None:
    """Set `verify_by` / `target_reasons` on every case (in place). `root_lines`: changed (added) lines per root."""
    cache: dict[str, list[str]] = {}
    root_hits = {rid: _scan(lines, patterns, "changed code — ") for rid, lines in root_lines.items()}
    flag_at = {}
    for f in flags:
        if f.category in RUNTIME_FLAGS and f.related_symbol:
            flag_at.setdefault((f.related_symbol.qualified_name, f.related_symbol.file_path), f)
    window_hits: dict[str, list[str]] = {}
    for c in cases:
        if c.sub_reason in REVIEW_SUBS:
            c.verify_by, c.target_reasons = "review", []
            continue
        reasons = []
        ev = c.evidence[0]
        g = GROUP_REASONS.get((c.risk_group, c.sub_reason)) or GROUP_REASONS.get((c.risk_group, None))
        if g:
            reasons.append(f"{g} ({c.risk_group}{'/' + c.sub_reason if c.sub_reason else ''} at {ev.file_path}:{ev.line})")
        sym = getattr(ev, "qualified_name", None)
        for rid in sorted({c.node_id} | node_roots.get(c.node_id, set())):
            f = flag_at.get((sym, ev.file_path)) if rid == c.node_id else None
            if f:
                reasons.append(f"runtime routing ({f.category}): {f.reason[:120]}")
            reasons += root_hits.get(rid, [])
        if getattr(ev, "kind", "file") != "file":
            key = f"{ev.file_path}:{ev.line}"
            if key not in window_hits:
                window_hits[key] = _scan(_window(repo, ev.file_path, ev.line, cache), patterns)
            reasons += window_hits[key]
        reasons = list(dict.fromkeys(reasons))[:MAX_REASONS]
        c.verify_by, c.target_reasons = ("target" if reasons else "review"), reasons


def action(case: dict[str, Any]) -> str:
    """Final bucket of a report case: `test_on_target` | `review` (not yet reviewed) | `closed_by_review`."""
    if case.get("verify_by", "target") == "target":
        return "test_on_target"
    v = case.get("verification")
    if v and v.get("verdict") == "pass_by_review":
        return "closed_by_review"
    return "test_on_target" if v else "review"  # an AI read it and could not close it -> run it
