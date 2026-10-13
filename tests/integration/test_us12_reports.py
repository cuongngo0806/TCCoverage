"""Spec 012 US1: reports inside the workspace, one folder per run, nothing overwritten, git status clean."""
import hashlib
import json
import subprocess

from tcadvisor.cli.main import main


def _digest(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir()) if p.is_file()}


def test_three_runs_three_folders_latest_and_clean_status(project, capsys):
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    args = ["analyze", "--repo", str(project.repo), "--build-dir", str(project.build), "--cache-dir",
            str(project.cache), "--graph", "clang", "--language", "en", "-q"]
    root = project.repo / ".tcadvisor" / "reports"
    assert main(args + ["--commit-range", "HEAD~1..HEAD"]) == 0
    first = (root / "latest").resolve()
    before = _digest(first)
    # a filled report in the latest run is carried over by default
    html = first / "report.html"
    from tcadvisor.report.results import read_results
    block = read_results(html)
    rep = json.loads((first / "report.json").read_text())
    key = rep["test_case_candidates"][0]["key"]
    block["results"][key] = {"verdict": "pass", "comment": "ok", "tester": "t", "date": "2026-10-12",
                             "defect_ref": "", "attachments": [], "needs_recheck": False, "carried_from": None}
    from tcadvisor.report.render import write_outputs
    write_outputs({**rep, "test_results": block}, first, "all")
    before = _digest(first)
    assert main(args + ["--commit-range", "HEAD~1..HEAD"]) == 0
    assert main(args + ["--working-tree"]) == 0
    runs = sorted(d for d in root.iterdir() if d.is_dir() and not d.is_symlink())
    assert len(runs) == 3 and len({d.name for d in runs}) == 3
    assert _digest(first) == before  # earlier run untouched
    latest = (root / "latest").resolve()
    assert latest.name.endswith("working-tree")
    second = [d for d in runs if d not in (first, latest)][0]
    rep2 = json.loads((second / "report.json").read_text())
    assert rep2["test_results"]["results"][key]["verdict"] == "pass"
    assert any("carried over from the latest run" in n for n in rep2["run_notes"])
    status = subprocess.run(["git", "-C", str(project.repo), "status", "--porcelain"], capture_output=True,
                            text=True).stdout
    assert status == ""
    # verify-pack finds the latest run from the repository config
    capsys.readouterr()
    assert main(["verify-pack", "--repo", str(project.repo)]) == 0
    assert str(latest) in json.loads(capsys.readouterr().out)["verdicts"]
