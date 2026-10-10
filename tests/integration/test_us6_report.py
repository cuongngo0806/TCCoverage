"""Spec 006 US3: fillable report — results block, carry-over by key, `tcadvisor results`, the HTML form."""
import json
import re
import shutil
from pathlib import Path

import pytest

from tcadvisor.cli.main import main as cli_main
from tcadvisor.report.results import read_results

BLOCK = re.compile(r'(<script type="application/json" id="results">)(.*?)(</script>)', re.S)


def _fill(html: Path, out: Path, results: dict, attachments: dict | None = None) -> Path:
    text = html.read_text()
    block = json.loads(BLOCK.search(text).group(2))
    block["results"].update(results)
    block["attachments"].update(attachments or {})
    out.write_text(BLOCK.sub(lambda m: m.group(1) + json.dumps(block) + m.group(3), text, count=1))
    return out


def _change(project):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 9) return 9;")
    project.commit()


def test_results_round_trip_carry_over_and_recheck(project, tmp_path, capsys):
    _change(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    cases = r["test_case_candidates"]
    assert cases and all(re.match(r"^[0-9a-f]{12}(-\d+)?$", c["key"]) for c in cases)
    assert len({c["key"] for c in cases}) == len(cases)
    html = project.out / "report.html"
    assert read_results(html)["results"] == {}

    first, second = cases[0], cases[1]
    att = {"a1": {"name": "run.log", "type": "text/plain", "size": 3, "sha256": "0" * 64, "data": "YWJj"}}
    filled = _fill(html, tmp_path / "filled.html", {
        first["key"]: {"verdict": "pass", "tester": "an", "date": "2026-10-10", "attachments": [],
                       "fingerprint": first["code_fingerprint"], "description": first["description"]},
        second["key"]: {"verdict": "fail", "tester": "an", "date": "2026-10-10", "attachments": ["a1"],
                        "fingerprint": "000000000000", "description": second["description"]},
        "deadbeef0000": {"verdict": "cannot_occur", "tester": "an", "date": "2026-10-10", "comment": "guarded",
                         "attachments": [], "description": "old case"}}, att)

    assert cli_main(["results", str(filled)]) == 4  # incomplete (untested cases remain)
    assert "1 pass / 1 fail" in capsys.readouterr().out

    r2 = project.analyze("--commit-range", "HEAD~1..HEAD", "--previous-report", str(filled), "--no-run-cache")
    by_key = {c["key"]: c for c in r2["test_case_candidates"]}
    assert by_key[first["key"]]["test_result"]["verdict"] == "pass"
    assert not by_key[first["key"]]["test_result"].get("needs_recheck")
    assert by_key[second["key"]]["test_result"]["needs_recheck"] is True  # fingerprint differs
    assert by_key[second["key"]]["test_result"]["attachments"] == [{"id": "a1", "name": "run.log"}]
    assert "deadbeef0000" in r2["test_results"]["orphaned_results"]
    assert "test results: 1 pass / 1 fail" in (project.out / "report.md").read_text()
    js = json.loads((project.out / "report.json").read_text())
    assert "data" not in js["test_results"]["attachments"]["a1"]  # bytes only inside report.html
    assert read_results(project.out / "report.html")["attachments"]["a1"]["data"] == "YWJj"


def test_previous_report_must_be_a_tcadvisor_report(project, tmp_path):
    bad = tmp_path / "x.html"
    bad.write_text("<html></html>")
    project.analyze("--working-tree", "--previous-report", str(bad), expect=2)


def _chromium():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    exe = next(iter(sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))), None)
    return sync_playwright, (str(exe) if exe else None)


@pytest.mark.skipif(_chromium() is None, reason="playwright not installed")
def test_form_fill_attach_save_reopen(project, tmp_path):
    sync_playwright, exe = _chromium()
    _change(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    key = r["test_case_candidates"][0]["key"]
    shot = tmp_path / "shot.png"
    shot.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                                   "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082"))
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page(accept_downloads=True)
        pg.goto((project.out / "report.html").as_uri())
        tr = pg.locator(f'.tr[data-k="{key}"]')
        tr.locator('[data-act="tog"]').click()
        tr.locator('input[value="fail"]').check()
        tr.locator('[data-f="tester"]').fill("Tester A")
        assert "attachment or a defect reference" in tr.locator("[data-err]").inner_text()
        tr.locator('input[type="file"]').set_input_files(str(shot))
        pg.wait_for_selector(f'.tr[data-k="{key}"] img.thumb')
        assert tr.locator("[data-err]").inner_text().strip() == ""
        assert "Incomplete" in pg.locator("#trSec").inner_text()
        with pg.expect_download() as dl:
            pg.locator('#trSec [data-act="save"]').click()
        saved = tmp_path / "saved.html"
        dl.value.save_as(saved)
        pg.goto(saved.as_uri())
        assert pg.locator(f'.tr[data-k="{key}"] .vb.fail').count() == 1
        b.close()
    block = read_results(saved)
    rec = block["results"][key]
    assert rec["verdict"] == "fail" and rec["tester"] == "Tester A" and len(rec["attachments"]) == 1
    att = block["attachments"][rec["attachments"][0]]
    assert att["name"] == "shot.png" and att["type"] == "image/png" and len(att["sha256"]) == 64
    # the analysis data block is untouched by the form
    assert json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', saved.read_text(),
                                re.S).group(1))["test_case_candidates"][0]["key"] == key
    shutil.copy(saved, tmp_path / "keep.html")


def test_rerender_keeps_results_and_new_analysis_backs_them_up(project, tmp_path):
    _change(project)
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    key = r["test_case_candidates"][0]["key"]
    html = project.out / "report.html"
    _fill(html, html, {key: {"verdict": "pass", "tester": "an", "date": "2026-10-10", "attachments": []}})
    assert cli_main(["render", str(project.out / "report.json")]) == 0  # same analysis: kept
    assert read_results(html)["results"][key]["verdict"] == "pass"
    assert "[PASS]" in (project.out / "report.brief.txt").read_text()
    project.analyze("--commit-range", "HEAD~1..HEAD", "--no-run-cache")  # new analysis: backed up, not merged
    assert read_results(html)["results"] == {}
    backups = list(project.out.glob("report.results-backup-*.html"))
    assert len(backups) == 1 and read_results(backups[0])["results"][key]["verdict"] == "pass"
