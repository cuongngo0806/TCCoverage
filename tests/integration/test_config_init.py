"""Workspace config shared by the CLI, the VS Code extension and AI chat; `tcadvisor init` (Copilot prompts)."""
import json

from tcadvisor.cli.main import main
from tcadvisor.config import default_output_dir, resolve


def test_config_supplies_build_dir_output_dir_and_scope(project, capsys):
    cfg = project.repo / ".tcadvisor" / "config.json"
    cfg.parent.mkdir(exist_ok=True)
    out = project.root / "reports-from-config"
    cfg.write_text(json.dumps({"graph": "clang", "language": "en", "build_dir": str(project.build),
                               "output_dir": "../reports-from-config", "max_hop_depth": 1}))
    r = resolve(project.repo)
    assert (r["build_dir"], r["output_dir"].resolve(), r["max_hop_depth"]) == (project.build, out.resolve(), 1)
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    # no --build-dir / --output-dir / --graph / --language: all from the config (as an AI chat runs it)
    assert main(["analyze", "--repo", str(project.repo), "--commit-range", "HEAD~1..HEAD", "--cache-dir",
                 str(project.cache), "--print", "brief", "-q"]) == 0
    stdout = capsys.readouterr().out
    assert stdout.rstrip().endswith(f"REPORT {out.resolve()}")
    rep = json.loads((out / "report.json").read_text())
    assert rep["graph_provider"] == "clang" and rep["report_language"] == "en"
    assert max(n["hop_distance"] for n in rep["impact_nodes"]) == 1
    assert main(["config", "--repo", str(project.repo)]) == 0
    assert json.loads(capsys.readouterr().out)["max_hop_depth"] == 1
    # verify-pack finds the report from the repository config
    assert main(["verify-pack", "--repo", str(project.repo)]) == 0
    m = json.loads(capsys.readouterr().out)
    assert m["report_language"] == "en" and m["verdicts"].endswith("verdicts.json")


def test_bad_config_value_is_a_usage_error(project):
    cfg = project.repo / ".tcadvisor" / "config.json"
    cfg.parent.mkdir(exist_ok=True)
    cfg.write_text('{"max_hop_depth": 0}')
    assert main(["config", "--repo", str(project.repo)]) == 2


def test_default_output_dir_is_outside_the_repo(project):
    assert default_output_dir(project.repo) == project.repo.resolve().parent / "tcadvisor-report" / project.repo.name


def test_init_writes_config_and_copilot_prompts_without_overwriting(project, capsys):
    assert main(["init", "--repo", str(project.repo), "--copilot", "--language", "en"]) == 0
    cfg = json.loads((project.repo / ".tcadvisor" / "config.json").read_text())
    assert cfg == {"graph": "codegraph", "language": "en", "build_dir": "build"}
    prompts = project.repo / ".github" / "prompts"
    cov = (prompts / "tc-coverage.prompt.md").read_text()
    assert cov.startswith("---\n") and "python -m tcadvisor analyze --repo . <mode> --print brief -q" in cov
    assert "tcadvisor annotate" in (prompts / "tc-verify.prompt.md").read_text()
    (prompts / "tc-coverage.prompt.md").write_text("mine")
    capsys.readouterr()
    assert main(["init", "--repo", str(project.repo), "--copilot", "--language", "vi"]) == 0
    assert "kept" in capsys.readouterr().out
    assert (prompts / "tc-coverage.prompt.md").read_text() == "mine"
    assert json.loads((project.repo / ".tcadvisor" / "config.json").read_text())["language"] == "en"
