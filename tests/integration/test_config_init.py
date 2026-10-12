"""Workspace config shared by the CLI and AI chat; `tcadvisor init` (tc-coverage skill for Claude Code / Copilot)."""
import json

from tcadvisor.cli.main import main
from tcadvisor.config import DEFAULTS, default_output_dir, resolve


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
    run = out.resolve() / "latest"
    assert f"REPORT {run.resolve()}" in stdout and stdout.rstrip().endswith(f"report: {run.resolve()}")
    rep = json.loads((run / "report.json").read_text())
    assert rep["run"]["name"] == run.resolve().name and rep["run"]["name"].endswith(
        rep["change_input"]["old_rev"][:7] + "_" + rep["change_input"]["new_rev"][:7])
    assert rep["graph_provider"] == "clang" and rep["report_language"] == "en"
    assert max(n["hop_distance"] for n in rep["impact_nodes"]) == 1
    assert main(["config", "--repo", str(project.repo), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["max_hop_depth"] == 1
    assert main(["config", "--repo", str(project.repo)]) == 0
    table = capsys.readouterr().out.splitlines()
    assert len(table) == len(DEFAULTS)
    assert any(line.split()[0] == "max_hop_depth" and line.split()[-1] == "config" for line in table)
    assert any(line.split()[0] == "verify_model" and line.split()[-1] == "default" for line in table)
    # verify-pack finds the report from the repository config
    assert main(["verify-pack", "--repo", str(project.repo)]) == 0
    m = json.loads(capsys.readouterr().out)
    assert m["report_language"] == "en" and m["verdicts"].endswith("verdicts.json")


def test_bad_config_value_is_a_usage_error(project):
    cfg = project.repo / ".tcadvisor" / "config.json"
    cfg.parent.mkdir(exist_ok=True)
    cfg.write_text('{"max_hop_depth": 0}')
    assert main(["config", "--repo", str(project.repo)]) == 2


def test_default_output_dir_is_in_the_workspace(project):
    assert default_output_dir(project.repo) == project.repo.resolve() / ".tcadvisor" / "reports"


def test_unknown_key_names_the_closest_one(project, capsys):
    cfg = project.repo / ".tcadvisor" / "config.json"
    cfg.parent.mkdir(exist_ok=True)
    cfg.write_text('{"verify_modle": "opus"}')
    assert main(["config", "--repo", str(project.repo)]) == 2
    assert "did you mean 'verify_model'" in capsys.readouterr().err


def test_init_writes_config_and_ai_front_ends_without_overwriting(project, capsys):
    assert main(["init", "--repo", str(project.repo), "--language", "en"]) == 0
    cfg = json.loads((project.repo / ".tcadvisor" / "config.json").read_text())
    assert set(cfg) == set(DEFAULTS)  # every key is listed with its default
    assert {k: cfg[k] for k in ("graph", "language", "build_dir", "include_tests", "ai_verify", "verify_model")} == {
        "graph": "codegraph", "language": "en", "build_dir": "build", "include_tests": False, "ai_verify": "chat",
        "verify_model": "haiku"}
    assert cfg["python"] and ".tcadvisor/reports/" in (project.repo / ".git" / "info" / "exclude").read_text()
    skill = (project.repo / ".claude" / "skills" / "tc-coverage" / "SKILL.md").read_text()
    assert skill.startswith("---\nname: tc-coverage") and "--print brief -q" in skill and "not_needed" in skill
    assert (project.repo / ".github" / "skills" / "tc-coverage" / "SKILL.md").read_text() == skill
    for agent in ("tc-case-verifier", "tc-verify-synthesizer", "tc-coverage-analyst"):
        assert (project.repo / ".claude" / "agents" / f"{agent}.md").read_text().startswith(f"---\nname: {agent}")
    prompts = project.repo / ".github" / "prompts"
    assert ".github/skills/tc-coverage/SKILL.md" in (prompts / "tc-coverage.prompt.md").read_text()
    assert "tcadvisor annotate" in (prompts / "tc-verify.prompt.md").read_text()
    (prompts / "tc-coverage.prompt.md").write_text("mine")
    capsys.readouterr()
    assert main(["init", "--repo", str(project.repo), "--ai", "copilot", "--language", "vi"]) == 0
    assert "kept" in capsys.readouterr().out
    assert (prompts / "tc-coverage.prompt.md").read_text() == "mine"
    assert json.loads((project.repo / ".tcadvisor" / "config.json").read_text())["language"] == "en"
    assert main(["init", "--repo", str(project.repo), "--ai", "cursor"]) == 2


def test_init_without_ai_and_the_ai_verify_marker(project, capsys):
    assert main(["init", "--repo", str(project.repo), "--ai", "none", "--graph", "clang", "--language", "en",
                 "--build-dir", str(project.build)]) == 0
    assert not (project.repo / ".claude").exists() and not (project.repo / ".github").exists()
    cfg_path = project.repo / ".tcadvisor" / "config.json"
    assert json.loads(cfg_path.read_text())["ai_verify"] == "off"
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    args = ["analyze", "--repo", str(project.repo), "--commit-range", "HEAD~1..HEAD", "--cache-dir",
            str(project.cache), "--output-dir", str(project.out), "--print", "brief", "-q"]
    capsys.readouterr()
    assert main(args) == 0
    assert "AI-VERIFY" not in capsys.readouterr().out
    assert main(args + ["--ai-verify", "chat"]) == 0
    assert "(ai_verify is 'chat')" in capsys.readouterr().out


def test_repo_copies_of_the_skill_match_the_packaged_ones():
    """This repository's own .claude/ uses the files `tcadvisor init` installs (one source of truth)."""
    from pathlib import Path
    from tcadvisor.integrations.init import files_for
    root = Path(__file__).resolve().parents[2]
    for rel, text in files_for("claude"):
        assert (root / rel).read_text(encoding="utf-8") == text, f"{rel}: run tcadvisor init --repo . --ai claude --force"


def test_ai_verify_claude_closes_cases_into_the_ai_report(project, tmp_path, monkeypatch, capsys):
    """config ai_verify = claude: analyze runs the headless verification; closed cases leave report.md."""
    import os
    import stat
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "claude"
    fake.write_text("#!/usr/bin/env python3\nimport json,re,sys\nprompt=sys.stdin.read()\n"
                    "ids=sorted(set(re.findall(r'TC-\\d{4}',prompt)))\n"
                    "res={'summary':'s','additional_checks':[]} if 'VERDICTS:' in prompt else "
                    "{'cases':{i:{'verdict':'not_needed','note':'a clean build settles it'} for i in ids}}\n"
                    "print(json.dumps({'result':json.dumps(res),'total_cost_usd':0,'usage':{}}))\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    cfg = project.repo / ".tcadvisor" / "config.json"
    cfg.parent.mkdir(exist_ok=True)
    cfg.write_text(json.dumps({"graph": "clang", "language": "en", "build_dir": str(project.build),
                               "ai_verify": "claude"}))
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    assert main(["analyze", "--repo", str(project.repo), "--commit-range", "HEAD~1..HEAD", "--cache-dir",
                 str(project.cache), "--output-dir", str(project.out), "--exact-output-dir", "--print", "brief",
                 "-q"]) == 0
    brief = capsys.readouterr().out
    r = json.loads((project.out / "report.json").read_text())
    n = len(r["test_case_candidates"])
    assert n and all(c["verification"]["verdict"] == "not_needed" for c in r["test_case_candidates"])
    assert f"AI-CLOSED {n}" in brief and "TC-0001" not in brief
    assert "TC-0001" not in (project.out / "report.md").read_text()
    ai = (project.out / "report.ai-verified.md").read_text()
    assert "TC-0001" in ai and "a clean build settles it" in ai
    assert (project.out / "report.ai-verified.html").is_file()


def test_restored_ai_and_analysis_settings_come_from_the_config(project, tmp_path, capsys):
    """Spec 012 US6: settings the removed VS Code extension held (Claude binary, models, budget, graph binary,
    analysis options) are config keys honoured by `analyze` and `verify`."""
    import stat
    log = tmp_path / "argv.log"
    fake = tmp_path / "my-claude"  # not on PATH: only claude_bin finds it
    fake.write_text("#!/usr/bin/env python3\nimport json,re,sys\n"
                    f"open({str(log)!r},'a').write(' '.join(sys.argv[1:])+'\\n')\nprompt=sys.stdin.read()\n"
                    "ids=sorted(set(re.findall(r'TC-\\d{4}',prompt)))\n"
                    "res={'summary':'s','additional_checks':[]} if 'VERDICTS:' in prompt else "
                    "{'cases':{i:{'verdict':'confirmed','note':'n'} for i in ids}}\n"
                    "print(json.dumps({'result':json.dumps(res),'total_cost_usd':0,'usage':{}}))\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    cfg = project.repo / ".tcadvisor" / "config.json"
    cfg.parent.mkdir(exist_ok=True)
    cfg.write_text(json.dumps({"graph": "clang", "language": "en", "build_dir": str(project.build),
                               "ai_verify": "claude", "claude_bin": str(fake), "verify_model": "model-a",
                               "synth_model": "model-b", "budget_usd": 0.25, "verify_priorities": "P1,P2,P3",
                               "attachment_warn_mb": 7, "history": False, "format": "all"}))
    project.edit("src/util.cpp", "if (n > 3) return 3;", "if (n > 4) return 4;")
    project.commit()
    assert main(["analyze", "--repo", str(project.repo), "--commit-range", "HEAD~1..HEAD", "--cache-dir",
                 str(project.cache), "-q"]) == 0
    calls = log.read_text().splitlines()
    assert calls and all("--max-budget-usd 0.25" in c for c in calls)
    assert any("--model model-a" in c for c in calls) and any("--model model-b" in c for c in calls)
    rep = json.loads((project.repo / ".tcadvisor" / "reports" / "latest" / "report.json").read_text())
    assert rep["metrics"]["attachment_warn_mb"] == 7
    # `verify` on an existing report: the report's repository config applies, a flag still wins
    log.write_text("")
    report = project.repo / ".tcadvisor" / "reports" / "latest" / "report.json"
    assert main(["verify", str(report), "--ai-external-approved", "--verify-model", "model-c"]) == 0
    calls = log.read_text().splitlines()
    assert any("--model model-c" in c for c in calls) and all("--max-budget-usd 0.25" in c for c in calls)
