"""Report language (constitution IX): vi by default, en on request; report.json text stays English."""
import json
import string

from tcadvisor.cli.main import main
from tcadvisor.report.l10n import Translator, localize, vi


def test_catalog_placeholders_match():
    for en, tr in vi.entries():
        names = {f for _t, f, _s, _c in string.Formatter().parse(en) if f}
        assert names == {f for _t, f, _s, _c in string.Formatter().parse(tr) if f}, en


def test_english_is_identity():
    r = {"test_case_candidates": [], "uncertainty_flags": [], "run_notes": ["x"]}
    assert localize(r, Translator("en")) is r


def test_default_report_is_vietnamese_and_json_stays_english(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n >= 5) return 5;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--language", "vi")
    assert r["report_language"] == "vi"
    assert r["test_case_candidates"][0]["description"].startswith("Verify")  # the contract stays English
    md = (project.out / "report.md").read_text(encoding="utf-8")
    assert "## Test case cần kiểm tra" in md and "## Test cases to check" not in md
    assert r["l10n"][r["test_case_candidates"][0]["description"]] in md
    brief = (project.out / "report.brief.txt").read_text(encoding="utf-8")
    assert "Kế hoạch test:" in brief
    html = (project.out / "report.html").read_text(encoding="utf-8")
    assert 'lang="vi"' in html
    assert main(["render", str(project.out / "report.json"), "--language", "en"]) == 0
    assert "## Test cases to check" in (project.out / "report.md").read_text(encoding="utf-8")
    assert "l10n" not in json.loads((project.out / "report.json").read_text())


def test_cli_default_language_is_vi(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    args = ["analyze", "--repo", str(project.repo), "--build-dir", str(project.build), "--output-dir",
            str(project.out), "--cache-dir", str(project.cache), "--commit-range", "HEAD~1..HEAD", "--graph", "clang",
            "-q"]
    assert main(args) == 0
    assert json.loads((project.out / "report.json").read_text())["report_language"] == "vi"
