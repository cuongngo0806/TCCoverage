"""Spec 012 US1: one immutable run folder per analysis, `latest` pointer."""
import os
from datetime import datetime

import pytest

from tcadvisor.models import UsageError
from tcadvisor.report.runs import change_label, latest_run, new_run_folder, report_file, update_latest

NOW = datetime(2026, 10, 12, 10, 15, 30)


def test_change_label():
    assert change_label("HEAD~1..HEAD", False, "a1b2c3d4e5", "e4f5a6b7c8") == "a1b2c3d_e4f5a6b"
    assert change_label("v1.0..main", False) == "v1.0_main"
    assert change_label(None, True) == "working-tree"
    assert change_label(None, False) == "symbols"


def test_name_and_collision_suffix(tmp_path):
    a = new_run_folder(tmp_path, "working-tree", NOW)
    b = new_run_folder(tmp_path, "working-tree", NOW)
    c = new_run_folder(tmp_path, "working-tree", NOW)
    assert [x.name for x in (a, b, c)] == ["20261012-101530-working-tree", "20261012-101530-working-tree-2",
                                         "20261012-101530-working-tree-3"]
    assert all(x.is_dir() for x in (a, b, c))


def test_latest_symlink_is_replaced(tmp_path):
    a = new_run_folder(tmp_path, "symbols", NOW)
    update_latest(tmp_path, a)
    assert latest_run(tmp_path) == a.resolve()
    b = new_run_folder(tmp_path, "symbols", NOW)
    update_latest(tmp_path, b)
    assert latest_run(tmp_path) == b.resolve()
    assert not list(tmp_path.glob(".latest.*"))
    (b / "report.json").write_text("{}")
    assert report_file(tmp_path) == b.resolve() / "report.json"


def test_latest_txt_when_symlinks_fail(tmp_path, monkeypatch):
    a = new_run_folder(tmp_path, "symbols", NOW)

    def no_symlink(*_a, **_k):
        raise OSError("symlinks not supported")
    monkeypatch.setattr(os, "symlink", no_symlink)
    p = update_latest(tmp_path, a)
    assert p.name == "latest.txt" and p.read_text().strip() == a.name
    assert latest_run(tmp_path) == a


def test_unwritable_root_is_a_usage_error(tmp_path):
    if os.geteuid() == 0:
        blocker = tmp_path / "file"
        blocker.write_text("x")
        root = blocker / "reports"  # a path under a regular file can never be created
    else:
        ro = tmp_path / "ro"
        ro.mkdir()
        ro.chmod(0o500)
        root = ro / "reports"
    with pytest.raises(UsageError, match="output_dir"):
        new_run_folder(root, "symbols", NOW)
