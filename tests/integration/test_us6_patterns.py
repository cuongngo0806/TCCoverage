"""Spec 006 US4: lesson-learned patterns (one positive scenario each, one negative) and team lessons."""
import pytest
from fixtures_us6 import add_pattern_fixture

SCENARIOS = {
    "symmetric_counterpart": (("src/codec.cpp", "    return v * 2 + 1;", "    return v * 2 + 3;"), "decode_frame"),
    "same_code_elsewhere": (("src/codec.cpp", "    for (int i = 0; i < n; ++i) sum = (sum + data[i] * 31) % 65521;\n"
                             "    return sum;\n}\nint checksum_fast",
                             "    for (int i = 0; i < n; ++i) sum = (sum + data[i] * 37) % 65521;\n"
                             "    return sum;\n}\nint checksum_fast"), "checksum_fast"),
    "new_enum_value": (("include/door/codec.h", "enum class State { Idle, Busy };",
                        "enum class State { Idle, Busy, Error };"), "state_name"),
    "return_meaning": (("src/codec.cpp", "    if (raw < 0)\n        return -1;\n    return raw;",
                        "    if (raw < 0)\n        return -1;\n    if (raw > 1000)\n        return -2;\n    return raw;"),
                       "use_parse"),
    "shared_state": (("src/codec.cpp", "    count_ += 1;", "    count_ += 2;"), "Counter::read"),
    "new_early_exit": (("src/codec.cpp", "    int* p = new int[4];\n    p[0] = buf[0];",
                        "    int* p = new int[4];\n    if (!buf)\n        return 0;\n    p[0] = buf[0];"), "process"),
    "config_reader": (("src/codec.cpp", "int run_a(int x) {\n    return x;",
                       "int run_a(int x) {\n    if (g_cfg.fast_mode_enabled)\n        return x + 1;\n    return x;"),
                      "run_b"),
}


def _patterns(r):
    """(pattern, symbol) -> case, for pattern cases and for existing cases a pattern was folded into."""
    import re
    out = {}
    for c in r["test_case_candidates"]:
        q = c["evidence"][0]["qualified_name"]
        name = q if q.startswith("Counter::") else q.split("::")[-1]
        for p in ([c["pattern"]] if c.get("pattern") else []) + re.findall(r"Also \((\w+)\)", c["description"]):
            out[(p, name)] = c
    return out


@pytest.mark.parametrize("pattern", sorted(SCENARIOS))
def test_pattern(project, pattern):
    add_pattern_fixture(project)
    (path, old, new), expect = SCENARIOS[pattern]
    project.edit(path, old, new)
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    found = _patterns(r)
    assert (pattern, expect) in found, sorted(found)
    c = found[(pattern, expect)]
    assert c["corner_cases"] and c["evidence"][0]["file_path"]


def test_no_pattern_for_a_plain_change(project):
    add_pattern_fixture(project)
    project.edit("src/codec.cpp", "int run_a(int x) {\n    return x;", "int run_a(int x) {\n    return x + 1;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD")
    assert not _patterns(r), sorted(_patterns(r))


def test_team_lesson_is_added_to_matching_cases(project, tmp_path):
    add_pattern_fixture(project)
    lessons = tmp_path / "lessons.json"
    lessons.write_text('{"lessons": [{"id": "L7", "title": "Counter overflow", "when": {"tokens_any": ["count_"]},'
                       ' "ask": "Check the counter cannot overflow at INT_MAX"}]}')
    project.edit("src/codec.cpp", "    count_ += 1;", "    count_ += 2;")
    project.commit()
    r = project.analyze("--commit-range", "HEAD~1..HEAD", "--lessons", str(lessons))
    hit = [c for c in r["test_case_candidates"] if "L7" in c["lessons"]]
    assert hit and all("Lesson L7 (Counter overflow): Check the counter" in " ".join(c["corner_cases"]) for c in hit)
    bad = tmp_path / "bad.json"
    bad.write_text('{"lessons": [{"id": "x", "title": "t", "when": {}, "ask": "a"}]}')
    project.analyze("--commit-range", "HEAD~1..HEAD", "--lessons", str(bad), expect=2)
