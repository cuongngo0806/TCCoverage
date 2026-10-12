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


def test_source_missing_from_compile_db_borrows_product_flags(autotools_project):
    """Field case: the Yocto build is another revision and does not compile a file the workspace's Makefile.am
    lists; its changes are still analysed with the flags of a sibling source of the same product."""
    pr = autotools_project
    log = pr.make_variant("basic", "--disable-feature-x")
    assert main(["compile-db", "--repo", str(pr.repo), "--from-log", str(log)]) == 0
    pr.write({"lib/extra.c": "#include \"remote.h\"\nint extra_level(int c) {\n    return remote_level(c) + 1;\n}\n"})
    pr.edit("lib/Makefile.am", "libremote_la_SOURCES = remote.c remote.h", "libremote_la_SOURCES = remote.c remote.h extra.c")
    pr.commit()
    pr.edit("lib/extra.c", "return remote_level(c) + 1;", "return remote_level(c) + 2;")
    pr.commit()
    r = pr.analyze("--commit-range", "HEAD~1..HEAD")
    assert any(c["evidence"][0].get("qualified_name") == "extra_level" for c in r["test_case_candidates"])
    assert not any(o["path"] == "lib/extra.c" for o in r["out_of_scope"])
    assert any("parsed with the flags of another source of the same product" in n for n in r["run_notes"])


def test_build_log_in_config_generates_the_compile_db(autotools_project, capsys, monkeypatch):
    """init writes a "build_log" key; once filled in, every analysis (re)generates the compile database from it."""
    pr = autotools_project
    monkeypatch.delenv("BUILDDIR", raising=False)
    assert main(["init", "--repo", str(pr.repo), "--ai", "none", "--graph", "clang", "--language", "en"]) == 0
    cfg_path = pr.repo / ".tcadvisor" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    assert "build_log" in cfg and cfg["build_log"] is None
    assert 'fill in "build_log"' in capsys.readouterr().out
    log = pr.make_variant("basic", "--disable-feature-x")
    cfg["build_log"] = str(log)
    cfg_path.write_text(json.dumps(cfg))
    pr.edit("lib/remote.c", "if (code > 3) return 3;", "if (code > 4) return 4;")
    pr.commit()
    args = ["analyze", "--repo", str(pr.repo), "--commit-range", "HEAD~1..HEAD", "--cache-dir", str(pr.cache), "-q",
            "--print", "json"]
    assert main(args) == 0
    r = json.loads(capsys.readouterr().out)
    assert any("compile database of variant default generated from" in n for n in r["run_notes"])
    assert r["build_model"]["products"] == 2 and not any("reduced accuracy" in n for n in r["run_notes"])
    assert (pr.repo / ".tcadvisor" / "build" / "default" / "compile_commands.json").is_file()
    assert main(args) == 0  # unchanged log: not regenerated
    assert not any("generated from" in n for n in json.loads(capsys.readouterr().out)["run_notes"])
    log.write_text(log.read_text() + "\n")  # a new bitbake -c compile wrote the log again
    assert main(args) == 0
    assert any("generated from" in n for n in json.loads(capsys.readouterr().out)["run_notes"])


def test_init_finds_the_yocto_log_under_builddir(autotools_project, tmp_path, monkeypatch, capsys):
    pr = autotools_project
    bb = tmp_path / "yocto-build"
    log = bb / "tmp-glibc" / "work" / "armv7at2hf-neon-oe-linux-gnueabi" / pr.repo.name / "0.0-r0" / "temp" / "log.do_compile"
    log.parent.mkdir(parents=True)
    log.write_text("NOTE: make -j 10\n")
    monkeypatch.setenv("BUILDDIR", str(bb))
    assert main(["init", "--repo", str(pr.repo), "--ai", "none"]) == 0
    cfg_path = pr.repo / ".tcadvisor" / "config.json"
    assert json.loads(cfg_path.read_text())["build_log"] == str(log)
    assert main(["init", "--repo", str(pr.repo), "--ai", "none", "--build-log", "/elsewhere/log.do_compile"]) == 0
    assert json.loads(cfg_path.read_text())["build_log"] == "/elsewhere/log.do_compile"  # explicit flag wins
