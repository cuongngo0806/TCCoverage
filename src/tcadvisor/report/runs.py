"""Run folders (spec 012 US1): every analysis writes its own folder `<root>/<YYYYMMDD-HHMMSS>-<change>[-N]` under
the report root (default `<repo>/.tcadvisor/reports`), never touching an earlier one; `<root>/latest` (symlink, or
`latest.txt` where symlinks are not possible) names the newest completed run."""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

LATEST = "latest"
LATEST_TXT = "latest.txt"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def change_label(commit_range: str | None, working_tree: bool, old_rev: str | None = None,
                 new_rev: str | None = None) -> str:
    """`a1b2c3d_e4f5a6b` for a commit range, `working-tree`, else `symbols`."""
    if commit_range:
        if old_rev and new_rev:
            return f"{old_rev[:7]}_{new_rev[:7]}"
        a, _, b = commit_range.partition("..")
        return _UNSAFE.sub("-", f"{a or 'HEAD'}_{b or 'HEAD'}").strip("-")[:60] or "range"
    return "working-tree" if working_tree else "symbols"


def new_run_folder(root: Path, label: str, now: datetime | None = None) -> Path:
    """Create a new, empty run folder (exclusive mkdir: two concurrent runs never share one)."""
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        from tcadvisor.models import UsageError
        raise UsageError(f"cannot create the report folder '{root}': {exc.strerror or exc}. Set another report root "
                         "with --output-dir or 'output_dir' in .tcadvisor/config.json") from exc
    base = f"{(now or datetime.now()).strftime('%Y%m%d-%H%M%S')}-{_UNSAFE.sub('-', label) or 'run'}"
    n = 1
    while True:
        folder = root / (base if n == 1 else f"{base}-{n}")
        try:
            folder.mkdir()
            return folder
        except FileExistsError:
            n += 1
        except OSError as exc:
            from tcadvisor.models import UsageError
            raise UsageError(f"cannot create the run folder '{folder}': {exc.strerror or exc}. Set another report "
                             "root with --output-dir or 'output_dir' in .tcadvisor/config.json") from exc


def update_latest(root: Path, folder: Path) -> Path:
    """Point `<root>/latest` at `folder` atomically (temp symlink + rename); `latest.txt` when symlinks fail."""
    link = root / LATEST
    tmp = root / f".{LATEST}.{os.getpid()}"
    try:
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        os.symlink(folder.name, tmp, target_is_directory=True)
        os.replace(tmp, link)
        (root / LATEST_TXT).unlink(missing_ok=True)
        return link
    except OSError:
        tmp.unlink(missing_ok=True)
        p = root / LATEST_TXT
        p.write_text(folder.name + "\n", encoding="utf-8")
        return p


def latest_run(root: Path) -> Path | None:
    """The newest run folder under `root` (via `latest`, else `latest.txt`, else the newest folder name)."""
    link = root / LATEST
    if link.is_dir():
        return link.resolve()
    txt = root / LATEST_TXT
    if txt.is_file():
        p = root / txt.read_text(encoding="utf-8").strip()
        if p.is_dir():
            return p
    runs = sorted(d for d in root.glob("[0-9]" * 8 + "-*") if d.is_dir()) if root.is_dir() else []
    return runs[-1] if runs else None


def report_file(root: Path, name: str = "report.json") -> Path:
    """`<root>/<latest run>/<name>`, or `<root>/<name>` for a report root written without run folders."""
    run = latest_run(root)
    if run is not None and (run / name).is_file():
        return run / name
    return root / name
