"""Thin ``git`` subprocess wrapper (research.md §5). Read-only operations only."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from tcadvisor.models import UsageError

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    old_path: str | None  # None when added
    new_path: str | None  # None when deleted
    old_lines: set[int] = field(default_factory=set)  # removed/changed lines on the old side
    new_lines: set[int] = field(default_factory=set)  # added/changed lines on the new side
    removed_text: list[str] = field(default_factory=list)
    added_text: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""


def git(repo: Path, *args: str, check: bool = True) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        raise UsageError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout


def resolve_rev(repo: Path, rev: str) -> str:
    return git(repo, "rev-parse", "--verify", rev + "^{commit}").strip()


def head_or_none(repo: Path) -> str | None:
    out = git(repo, "rev-parse", "--verify", "HEAD", check=False).strip()
    return out or None


def show(repo: Path, rev: str, path: str) -> str | None:
    res = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True)
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", errors="replace")


def parse_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    old_ln = new_ln = 0
    for line in text.splitlines():
        if line.startswith("diff --git "):
            cur = FileDiff(None, None)
            files.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("--- "):
            p = line[4:]
            cur.old_path = None if p == "/dev/null" else p[2:] if p.startswith("a/") else p
            continue
        if line.startswith("+++ "):
            p = line[4:]
            cur.new_path = None if p == "/dev/null" else p[2:] if p.startswith("b/") else p
            continue
        m = _HUNK.match(line)
        if m:
            old_ln, new_ln = int(m.group(1)), int(m.group(3))
            continue
        if line.startswith("-") and not line.startswith("---"):
            cur.old_lines.add(old_ln)
            cur.removed_text.append(line[1:])
            old_ln += 1
        elif line.startswith("+") and not line.startswith("+++"):
            cur.new_lines.add(new_ln)
            cur.added_text.append(line[1:])
            new_ln += 1
        elif line.startswith(" "):
            old_ln += 1
            new_ln += 1
    return [f for f in files if f.path]


def diff_range(repo: Path, base: str, head: str) -> list[FileDiff]:
    return parse_diff(git(repo, "diff", "-U0", "--no-color", "--no-ext-diff", "-M", base, head))


def diff_working_tree(repo: Path, base: str | None) -> list[FileDiff]:
    """Staged + unstaged changes against ``base`` (HEAD), plus untracked files as additions."""
    diffs = parse_diff(git(repo, "diff", "-U0", "--no-color", "--no-ext-diff", "-M", base)) if base else []
    for rel in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        p = repo / rel
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        diffs.append(FileDiff(None, rel, set(), set(range(1, len(lines) + 1)), [], lines))
    return diffs


def working_tree_fingerprint(repo: Path, base: str | None) -> str:
    """Content-identifying string for the working-tree change (used as run cache key)."""
    parts = [git(repo, "diff", "--no-color", "--no-ext-diff", base) if base else ""]
    for rel in sorted(git(repo, "ls-files", "--others", "--exclude-standard").splitlines()):
        try:
            parts.append(rel + "\0" + (repo / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return "\n".join(parts)
