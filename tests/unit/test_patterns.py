"""Lesson-pattern helpers (spec 006 US4)."""
from tcadvisor.classify.cases import merge_pattern_cases
from tcadvisor.classify.lessons import Lesson
from tcadvisor.classify.patterns import _CONST, counterpart_names
from tcadvisor.models import SymbolRef
from tcadvisor.models import TestCaseCandidate as Case


def test_counterpart_names_keep_the_naming_style():
    assert counterpart_names("encode_frame") == ["decode_frame"]
    assert counterpart_names("openChannel") == ["closeChannel"]
    assert counterpart_names("SerializeHeader") == ["DeserializeHeader"]
    assert "Stop" in counterpart_names("Start")
    assert counterpart_names("compute") == []
    assert counterpart_names("get") == []  # a lone get/set/to is too generic


def test_new_return_constants():
    for v in ("-2", "kTimeout", "ERR_BUSY", "Status::kBusy", "nullptr", "false", "EAGAIN"):
        assert _CONST.match(v), v
    for v in ("x+1", "value", "foo(bar)"):
        assert not _CONST.match(v), v


def _case(name, group="logic", pattern=None, desc="d", hints=()):
    return Case(id="", description=desc, activation_condition="a", evidence=[SymbolRef(name, "function", "a.cpp", 1)],
                priority="P2", risk_group=group, related_cmake_targets=["t"], pattern=pattern, hints=list(hints))


def test_merge_folds_same_symbol_and_group_only():
    base = [_case("f", hints=["h1"])]
    merge_pattern_cases(base, [_case("f", pattern="return_meaning", desc="ret", hints=["h2"]),
                               _case("f", group="thread_safety", pattern="shared_state"),
                               _case("g", pattern="symmetric_counterpart")])
    assert len(base) == 3 and base[0].pattern is None
    assert "Also (return_meaning): ret" in base[0].description and base[0].hints == ["h1", "h2"]


def test_lesson_matching():
    lesson = Lesson("L1", "t", "ask", tokens_any=["ms"], name_glob="*timer*", path_glob="src/*")
    assert lesson.matches("Conn::on_timer", "src/conn.cpp", {"ms", "x"}, None)
    assert not lesson.matches("Conn::on_timer", "src/conn.cpp", {"x"}, None)
    assert not lesson.matches("Conn::on_error", "src/conn.cpp", {"ms"}, None)
    assert not Lesson("L2", "t", "a", sub_reason="sibling_source").matches("f", "a", set(), "data_path_emitter")
