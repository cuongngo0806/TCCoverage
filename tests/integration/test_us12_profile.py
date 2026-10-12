"""Spec 012 US3: confirmed build variants; cases on code not built in any of them leave the main list."""
import io
import json

from tcadvisor.cli.main import main


def _setup(pr, capsys, variants=("basic", "pro")):
    args = {"basic": ("--disable-feature-x",), "pro": ("--enable-feature-x",)}
    for v in variants:
        log = pr.logs.get(v) or pr.make_variant(v, *args[v])
        assert main(["compile-db", "--repo", str(pr.repo), "--from-log", str(log), "--variant", v]) == 0
    capsys.readouterr()
    assert main(["profile", "--repo", str(pr.repo), "--detect", "--json"]) == 0
    proposal = json.loads(capsys.readouterr().out)
    return proposal


def _save(pr, proposal, monkeypatch, names):
    data = {**proposal, "variants": [v for v in proposal["variants"] if v["name"] in names]}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    assert main(["profile", "--repo", str(pr.repo), "--save", "-"]) == 0


def _names(cases):
    return {e.get("qualified_name") or e.get("from_symbol", {}).get("qualified_name")
            for c in cases for e in c["evidence"][:1]}


def test_detect_reads_switch_values_from_the_builds(autotools_project, capsys):
    p = _setup(autotools_project, capsys)
    assert p["system"] == "autotools" and {s["name"] for s in p["switches"]} >= {"AM:FEATURE_X", "HAVE_FEATURE_X",
                                                                                 "--enable-feature-x"}
    v = {x["name"]: x["values"] for x in p["variants"]}
    assert v["basic"]["AM:FEATURE_X"] is False and v["pro"]["AM:FEATURE_X"] is True
    assert v["basic"]["HAVE_FEATURE_X"] is False and v["pro"]["HAVE_FEATURE_X"] == "1"


def test_filter_by_variant_union_and_unknown(autotools_project, capsys, monkeypatch):
    pr = autotools_project
    proposal = _setup(pr, capsys)
    _save(pr, proposal, monkeypatch, {"basic", "pro"})
    pr.edit("lib/pro.c", "return code * 2;", "return code * 3;")  # only built with FEATURE_X
    pr.edit("lib/remote.c", "level += pro_boost(level);", "level += pro_boost(level) + 1;")  # under #ifdef
    pr.commit()
    both = pr.analyze("--commit-range", "HEAD~1..HEAD")
    assert both["build_profile"] == {"state": "confirmed", "variants": ["basic", "pro"], "filtering": True}
    assert both["not_built"] == []  # union: pro builds everything
    basic = pr.analyze("--commit-range", "HEAD~1..HEAD", "--variants", "basic")
    assert basic["build_profile"]["state"] == "overridden"
    moved = basic["not_built"]
    assert moved, "pro-only code must leave the main list for the basic variant"
    reasons = {x["reason"] for m in moved for x in m["excluded_by"]}
    assert reasons == {"preprocessor"}
    assert {m["case"]["evidence"][0].get("file_path") for m in moved} >= {"lib/remote.c"}
    assert basic["test_case_candidates"] == []  # dispatch / main only reach the change through the #ifdef branch
    pro_c = [n for n in basic["not_built_changes"] if n["path"] == "lib/pro.c"][0]
    assert {x["reason"] for x in pro_c["excluded_by"]} & {"source_not_in_product", "source_not_in_compile_db"}
    assert any("HAVE_FEATURE_X" in (x["condition"] or "") for m in moved for x in m["excluded_by"])
    kept_ids = {c["id"] for c in basic["test_case_candidates"]}
    assert not kept_ids & {m["case"]["id"] for m in moved}
    assert {n["path"] for n in basic["not_built_changes"]} >= {"lib/pro.c", "lib/remote.c"}
    assert {c["evidence"][0].get("file_path") for c in both["test_case_candidates"]} >= {"lib/pro.c", "lib/remote.c"}
    off = pr.analyze("--commit-range", "HEAD~1..HEAD", "--variants", "basic", "--no-variant-filter")
    assert off["not_built"] == [] and off["build_profile"]["filtering"] is False
    assert len(off["test_case_candidates"]) == len(moved)
    # a change under `#if UNKNOWN_LIMIT > 2` cannot be evaluated: kept + flagged
    pr.edit("lib/remote.c", "level -= 1;", "level -= 2;")
    pr.commit()
    unk = pr.analyze("--commit-range", "HEAD~1..HEAD", "--variants", "basic")
    assert unk["not_built"] == [] and unk["test_case_candidates"]
    assert any("UNKNOWN_LIMIT" in f["reason"] and "cannot be evaluated" in f["reason"]
               for f in unk["uncertainty_flags"])


def test_no_profile_and_stale_profile(autotools_project, capsys, monkeypatch):
    pr = autotools_project
    pr.edit("lib/pro.c", "return code * 2;", "return code * 3;")
    pr.commit()
    log = pr.make_variant("basic", "--disable-feature-x")
    assert main(["compile-db", "--repo", str(pr.repo), "--from-log", str(log)]) == 0
    r = pr.analyze("--commit-range", "HEAD~1..HEAD")
    assert r["not_built"] == [] and any("no confirmed build profile" in n for n in r["run_notes"])
    proposal = _setup(pr, capsys, ("basic",))
    _save(pr, proposal, monkeypatch, {"basic"})
    pr.edit("lib/Makefile.am", "libremote_la_CPPFLAGS = -I$(top_builddir)", "libremote_la_CPPFLAGS = -I$(top_builddir) -DX")
    pr.commit()
    r = pr.analyze("--commit-range", "HEAD~1..HEAD")
    assert r["build_profile"]["state"] == "stale"
    assert main(["profile", "--repo", str(pr.repo), "--show"]) == 0
    assert "build profile: stale" in capsys.readouterr().out


def test_cmake_variant_filter_uses_user_values(project, monkeypatch):
    """CMake projects: a variant = a compile database + switch values; `DOOR_TRACE` is off in the shipped build."""
    project.edit("src/util.cpp", "    if (n > 3) return 3;", "#ifdef DOOR_TRACE\n    n += 0;\n#endif\n    if (n > 3) return 3;")
    project.commit()
    project.edit("src/util.cpp", "    n += 0;", "    n += 1;")
    project.commit()
    data = {"system": "cmake", "variants": [{"name": "release", "compile_db": str(project.build / "compile_commands.json"),
                                             "values": {"DOOR_TRACE": False}, "value_source": {"DOOR_TRACE": "user"}}]}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(data)))
    assert main(["profile", "--repo", str(project.repo), "--save", "-"]) == 0
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert r["test_case_candidates"] == [] and r["not_built"]
    assert all(x["reason"] == "preprocessor" and "DOOR_TRACE" in x["condition"]
               for n in r["not_built"] for x in n["excluded_by"])
    off = project.analyze("--commit-range", "HEAD~1..HEAD", "--no-variant-filter")
    assert len(off["test_case_candidates"]) == len(r["not_built"])


def test_interactive_confirmation_saves_the_profile(autotools_project, capsys, monkeypatch):
    from tcadvisor.config import load_config
    from tcadvisor.index.variants import confirm_interactively
    pr = autotools_project
    _setup(pr, capsys, ("basic", "pro"))
    # basic: keep, rename to "base"; pro: drop; then save. Unknown switches stay unknown (empty answers).
    answers = iter(["y", "base", *[""] * 20])
    monkeypatch.setattr("tcadvisor.index.variants._ask",
                        lambda prompt, default="": (lambda a: a or default)(
                            "n" if "built and shipped" in prompt and "'pro'" in _last.get("v", "") else next(answers)))
    _last = {}
    orig_write = __import__("sys").stderr.write

    def spy(text):
        if text.startswith("\nVariant '"):
            _last["v"] = text
        return orig_write(text)
    monkeypatch.setattr("sys.stderr.write", spy, raising=False)
    prof = confirm_interactively(pr.repo, load_config(pr.repo))
    assert prof is not None and [v["name"] for v in prof["variants"]] == ["base"]
    assert load_config(pr.repo)["build"]["confirmed"] is True
