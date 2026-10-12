"""Spec 012 US2: a Yocto-style autotools module (configure.ac + Makefile.am) analysed with its products."""
import json
from pathlib import Path

from tcadvisor.cli.main import main


def _targets(report, name):
    return {t for c in report["test_case_candidates"] for e in c["evidence"]
            if e.get("qualified_name") == name for t in c.get("targets", [])} | {
        t for n in report["impact_nodes"] if n["symbol"]["qualified_name"] == name for t in n.get("targets", [])}


def test_compile_db_from_log_and_products_as_targets(autotools_project, capsys):
    pr = autotools_project
    log = pr.make_variant("basic", "--disable-feature-x")
    assert main(["compile-db", "--repo", str(pr.repo), "--from-log", str(log), "--variant", "basic"]) == 0
    out = capsys.readouterr().out
    assert "compile command(s)" in out
    db = json.loads((pr.repo / ".tcadvisor" / "build" / "basic" / "compile_commands.json").read_text())
    files = {e["file"] for e in db}
    assert str(pr.repo / "lib" / "remote.c") in files and str(pr.repo / "app" / "main.c") in files
    cfg = json.loads((pr.repo / ".tcadvisor" / "config.json").read_text())
    v = cfg["build"]["variants"][0]
    assert v["name"] == "basic" and v["compile_db"] == ".tcadvisor/build/basic/compile_commands.json"
    assert v["build_dir"].endswith("b-basic")

    pr.edit("lib/remote.c", "if (code > 3) return 3;", "if (code > 4) return 4;")
    pr.commit()
    r = pr.analyze("--commit-range", "HEAD~1..HEAD")
    assert r["build_model"]["system"] == "autotools" and r["build_model"]["products"] == 2
    assert "libremote" in _targets(r, "remote_level")
    assert "remoteapp" in _targets(r, "dispatch")
    assert not any("reduced accuracy" in n for n in r["run_notes"])
    assert {t["name"] for t in r["affected_targets"]} >= {"libremote", "remoteapp"}


def test_without_compile_db_the_command_is_named(autotools_project, capsys):
    pr = autotools_project
    pr.edit("lib/remote.c", "if (code > 3) return 3;", "if (code > 4) return 4;")
    pr.commit()
    assert pr.analyze("--commit-range", "HEAD~1..HEAD", expect=1) == {}  # libclang graph needs compile flags
    assert "tcadvisor compile-db --repo . --from-log" in capsys.readouterr().err


def test_source_in_no_product_and_build_file_change(autotools_project):
    pr = autotools_project
    log = pr.make_variant("basic", "--disable-feature-x")
    assert main(["compile-db", "--repo", str(pr.repo), "--from-log", str(log)]) == 0
    pr.edit("lib/orphan.c", "return x + 1;", "return x + 2;")
    pr.edit("lib/Makefile.am", "libremote_la_SOURCES = remote.c remote.h", "libremote_la_SOURCES = remote.c remote.h\n")
    pr.commit()
    r = pr.analyze("--commit-range", "HEAD~1..HEAD")
    oos = {o["path"]: o["reason"] for o in r["out_of_scope"]}
    assert "not built by any product" in oos["lib/orphan.c"]
    assert any(s["symbol"]["file_path"] == "lib/Makefile.am" and
               any("autotools / Yocto build definition" in x["detail"] for x in s["risks"])
               for s in r["changed_symbols"])


def test_readme_flow_init_compile_db_analyze(autotools_project, capsys):
    """README / docs/linux-yocto.md order: init (writes build_dir "build"), compile-db, analyze without flags."""
    pr = autotools_project
    log = pr.make_variant("basic", "--disable-feature-x")
    assert main(["init", "--repo", str(pr.repo), "--ai", "none", "--graph", "clang", "--language", "en"]) == 0
    assert main(["compile-db", "--repo", str(pr.repo), "--from-log", str(log), "--variant", "basic"]) == 0
    pr.edit("lib/remote.c", "if (code > 3) return 3;", "if (code > 4) return 4;")
    capsys.readouterr()
    assert main(["analyze", "--repo", str(pr.repo), "--working-tree", "--cache-dir", str(pr.cache), "--print", "brief",
                 "-q"]) == 0
    out = capsys.readouterr().out
    assert "remote_level" in out and "reduced accuracy" not in out


def test_compile_db_from_make_dry_run_without_building(autotools_project, capsys):
    """Target-only headers missing on the host: `make -n V=1` after configure lists every compile command."""
    import subprocess
    pr = autotools_project
    b = pr.root / "b-dry"
    b.mkdir()
    subprocess.run([str(pr.repo / "configure")], cwd=b, check=True, capture_output=True)
    dry = subprocess.run(["make", "-n", "V=1"], cwd=b, capture_output=True, text=True)
    log = pr.root / "dry.log"
    log.write_text(dry.stdout)
    assert not list(b.rglob("*.o"))  # nothing was compiled
    assert main(["compile-db", "--repo", str(pr.repo), "--from-log", str(log), "--variant", "dry"]) == 0
    db = json.loads((pr.repo / ".tcadvisor" / "build" / "dry" / "compile_commands.json").read_text())
    assert {Path(e["file"]).name for e in db} == {"remote.c", "main.c"}
