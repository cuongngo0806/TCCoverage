from tcadvisor.evidence.uncertainty import _line_active, _pp_eval

M = {"__linux__": "1", "__GNUC__": "13", "FOO": "BAR", "BAR": "0x10", "FN": "x(1)"}


def test_pp_eval():
    assert _pp_eval("defined(__linux__) && !defined _WIN32", M) is True
    assert _pp_eval("__GNUC__ >= 5 && FOO == 16", M) is True
    assert _pp_eval("defined(_WIN32) || UNDEFINED_NAME", M) is False
    assert _pp_eval("FN", M) is None and _pp_eval("G(1)", M) is None and _pp_eval("1 / 0", M) is None


def test_branch_position_in_stack():
    assert _line_active(["#ifdef _WIN32 / #else"], M) is True
    assert _line_active(["#if defined(__linux__) / #else"], M) is False
    assert _line_active(["#if defined(_WIN32) / #elif defined(__linux__)"], M) is True
    assert _line_active(["#ifdef __linux__", "#if __GNUC__ < 4"], M) is False
