"""The report's inline JavaScript must parse (a syntax error leaves the fillable form dead)."""
import re
import shutil
import subprocess

import pytest

from tcadvisor.report.html import _TEMPLATE


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_inline_script_parses(tmp_path):
    js = re.findall(r"<script>(.*?)</script>", _TEMPLATE, re.S)[-1]
    f = tmp_path / "report.js"
    f.write_text(js)
    res = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
