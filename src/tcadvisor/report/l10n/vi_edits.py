"""Vietnamese entries for ``classify/edits.py``: corner-case hints derived from the shape of an edit (operator /
constant / return value changed, removed guard / assert / call / assignment / term, reorder, lock added / removed)
and the parameter input classes. Style: see ``vi.py``.
"""
from __future__ import annotations

_CONST = "Constant changed `{old}` → `{new}` in `{line}`: test values "
_CONST_VI = "Hằng số đổi `{old}` → `{new}` trong `{line}`: kiểm tra các giá trị "
_LIMIT = " (new and old limit)"
_LIMIT_VI = " (giới hạn mới và cũ)"

_RET = "Return value changed `{old}` → `{new}`: drive "
_RET_VI = "Giá trị trả về đổi `{old}` → `{new}`: "
_RET_ERR = ("the error / invalid input that used to produce it (malformed, missing, out of range) and check every caller "
            "handles the new error result / value")
_RET_ERR_VI = ("đưa vào lỗi / đầu vào không hợp lệ từng sinh ra giá trị cũ (sai định dạng, thiếu, ngoài khoảng) và "
               "kiểm tra mọi caller xử lý được kết quả lỗi / giá trị mới")
_RET_REACH = "the input that reaches this return and check every caller handles the new error result / value"
_RET_REACH_VI = "đưa vào đầu vào đi tới lệnh return này và kiểm tra mọi caller xử lý được kết quả lỗi / giá trị mới"

_INPUT = "Input `{name}` ({type}): "
_INPUT_VI = "Đầu vào `{name}` ({type}): "

ENTRIES: list[tuple[str, str]] = [
    # ---- comparison operator changed (_op_hint) ------------------------------------------------------------
    ("`{cmp}` now also holds when `{eq}` (was `{op_old}`): test {eq_plain}, and one step below and above (`{line}`)",
     "`{cmp}` giờ cũng đúng khi `{eq}` (trước là `{op_old}`): kiểm tra {eq_plain}, cùng một bước dưới và trên "
     "(`{line}`)"),
    ("`{cmp}` no longer holds when `{eq}` (was `{op_old}`): test {eq_plain}, and one step below and above (`{line}`)",
     "`{cmp}` không còn đúng khi `{eq}` (trước là `{op_old}`): kiểm tra {eq_plain}, cùng một bước dưới và trên "
     "(`{line}`)"),
    ("Condition inverted `{old_cmp}` → `{new_cmp}`: test `{eq}` and `{ne}` (both branches swap)",
     "Điều kiện bị đảo `{old_cmp}` → `{new_cmp}`: kiểm tra `{eq}` và `{ne}` (hai nhánh đổi chỗ cho nhau)"),
    ("Comparison changed `{old_cmp}` → `{new_cmp}`: test `{a}` below, equal to and above `{b}`",
     "Phép so sánh đổi `{old_cmp}` → `{new_cmp}`: kiểm tra `{a}` nhỏ hơn, bằng và lớn hơn `{b}`"),
    # ---- logical operator / negation -------------------------------------------------------------------------
    ("`{old_op}` became `{new_op}` in `{line}`: test each operand true alone and false alone",
     "`{old_op}` đã thành `{new_op}` trong `{line}`: kiểm tra từng toán hạng khi chỉ riêng nó true và khi chỉ "
     "riêng nó false"),
    ("Negation removed in `{line}`: the branch now runs for the opposite inputs — test both",
     "Phép phủ định bị xoá trong `{line}`: nhánh này giờ chạy với các đầu vào ngược lại — kiểm tra cả hai"),
    ("Negation added in `{line}`: the branch now runs for the opposite inputs — test both",
     "Phép phủ định được thêm trong `{line}`: nhánh này giờ chạy với các đầu vào ngược lại — kiểm tra cả hai"),
    # ---- constant changed (values: integers verbatim; non-integer literals get "just below / above") ----------
    (_CONST + "{values}" + _LIMIT, _CONST_VI + "{values}" + _LIMIT_VI),
    (_CONST + "just below {a}, {b}, just above {c}" + _LIMIT,
     _CONST_VI + "ngay dưới {a}, {b}, ngay trên {c}" + _LIMIT_VI),
    (_CONST + "just below {a}, {b}, just above {c}, just below {d}, {e}, just above {f}" + _LIMIT,
     _CONST_VI + "ngay dưới {a}, {b}, ngay trên {c}, ngay dưới {d}, {e}, ngay trên {f}" + _LIMIT_VI),
    (_CONST + "just below {a}, {b}, just above {c}, {ints}" + _LIMIT,
     _CONST_VI + "ngay dưới {a}, {b}, ngay trên {c}, {ints}" + _LIMIT_VI),
    (_CONST + "{ints}, just below {a}, {b}, just above {c}" + _LIMIT,
     _CONST_VI + "{ints}, ngay dưới {a}, {b}, ngay trên {c}" + _LIMIT_VI),
    # ---- return value changed (old or new value may be empty: `return;`) --------------------------------------
    (_RET + _RET_ERR, _RET_VI + _RET_ERR_VI),
    (_RET + _RET_REACH, _RET_VI + _RET_REACH_VI),
    (_RET.replace("`{old}`", "``") + _RET_REACH, _RET_VI.replace("`{old}`", "``") + _RET_REACH_VI),
    (_RET.replace("`{new}`", "``") + _RET_ERR, _RET_VI.replace("`{new}`", "``") + _RET_ERR_VI),
    (_RET.replace("`{new}`", "``") + _RET_REACH, _RET_VI.replace("`{new}`", "``") + _RET_REACH_VI),
    # ---- value assigned changed / term removed ---------------------------------------------------------------
    ("`{name}` now gets `{new}` (was `{old}`): test code that relies on the old value of `{name_again}` (limits, "
     "sizes, timeouts, flags)",
     "`{name}` giờ nhận `{new}` (trước là `{old}`): kiểm tra code dựa vào giá trị cũ của `{name_again}` (giới hạn, "
     "kích thước, timeout, flag)"),
    ("`{term}` was removed from `{line}`: the computed value changes whenever that term is non-zero — check every "
     "reader of the result (sizes, offsets, decoding / round trip)",
     "`{term}` đã bị xoá khỏi `{line}`: giá trị tính ra thay đổi mỗi khi số hạng đó khác 0 — kiểm tra mọi nơi đọc "
     "kết quả (kích thước, offset, giải mã / round trip)"),
    # ---- removed guard / early exit / assert (t_input: one of the input phrases below) ------------------------
    ("Removed check `{cond}`: a violation is no longer detected here — {t_input} and check what happens downstream",
     "Đã bỏ kiểm tra `{cond}`: vi phạm không còn bị phát hiện ở đây — {t_input} và kiểm tra điều gì xảy ra phía "
     "sau"),
    ("Removed early exit on `{cond}`: the code after it now also runs when it holds — {t_input}",
     "Đã bỏ lệnh thoát sớm khi `{cond}`: code phía sau giờ cũng chạy khi điều kiện đó đúng — {t_input}"),
    ("Removed condition `{cond}`: the code it protected now also runs when it is false — {t_input}",
     "Đã bỏ điều kiện `{cond}`: code mà nó bảo vệ giờ cũng chạy khi điều kiện đó sai — {t_input}"),
    ("call with `{var}` == nullptr / 0", "gọi với `{var}` == nullptr / 0"),
    ("make `{expr}` false / null / zero", "làm cho `{expr}` là false / null / 0"),
    ("make `{expr}` true / non-null", "làm cho `{expr}` là true / khác null"),
    ("make `{expr}` hold (including the equality edge)", "làm cho `{expr}` đúng (kể cả biên bằng)"),
    ("make `{expr}` hold (and test the equality edge just outside it)",
     "làm cho `{expr}` đúng (và kiểm tra biên bằng nằm ngay ngoài nó)"),
    ("make `{expr}` hold", "làm cho `{expr}` đúng"),
    # ---- reorder ---------------------------------------------------------------------------------------------
    ("Order changed: `{first}` now runs before `{later}` — the later statement must not use what the earlier one "
     "released, reset, moved or overwrote (use after free / stale value)",
     "Thứ tự đã đổi: `{first}` giờ chạy trước `{later}` — câu lệnh chạy sau không được dùng thứ mà câu lệnh chạy "
     "trước đã giải phóng, reset, move hoặc ghi đè (use after free / giá trị cũ)"),
    # ---- locks -----------------------------------------------------------------------------------------------
    ("Lock on `{lock}` added (`{line}`): callers already holding it, callbacks invoked under it and lock order with "
     "other locks (deadlock)",
     "Đã thêm lock trên `{lock}` (`{line}`): các caller đang giữ sẵn lock này, các callback được gọi khi đang giữ "
     "nó và thứ tự lock với các lock khác (deadlock)"),
    ("Lock on `{lock}` removed (`{line}`): run this function concurrently with the other users of the data "
     "`{lock_again}` protected (data race, torn reads)",
     "Đã bỏ lock trên `{lock}` (`{line}`): chạy hàm này đồng thời với các nơi khác dùng dữ liệu mà `{lock_again}` "
     "bảo vệ (data race, torn read)"),
    # ---- removed statements ----------------------------------------------------------------------------------
    ("`{stmt}` is no longer done here: readers of `{target}` must not rely on it being updated on this path",
     "`{stmt}` không còn được thực hiện ở đây: các nơi đọc `{target}` không được dựa vào việc nó được cập nhật "
     "trên đường đi này"),
    ("`{name}(…)` is no longer called here (`{line}`): whatever depended on its effect (state, counters, "
     "notifications, cleanup) must still be correct",
     "`{name}(…)` không còn được gọi ở đây (`{line}`): mọi thứ phụ thuộc vào tác dụng của nó (trạng thái, bộ đếm, "
     "thông báo, dọn dẹp) vẫn phải đúng"),
    # ---- parameter input classes (input_classes) -------------------------------------------------------------
    (_INPUT + "nullptr", _INPUT_VI + "nullptr"),
    (_INPUT + "nullptr, empty string, very long string", _INPUT_VI + "nullptr, chuỗi rỗng, chuỗi rất dài"),
    (_INPUT + "empty, one element, very large", _INPUT_VI + "rỗng, một phần tử, rất lớn"),
    (_INPUT + "true and false", _INPUT_VI + "true và false"),
    (_INPUT + "0, 1 and the maximum value (wrap-around)", _INPUT_VI + "0, 1 và giá trị lớn nhất (wrap-around)"),
    (_INPUT + "negative, 0 and the maximum value", _INPUT_VI + "số âm, 0 và giá trị lớn nhất"),
    (_INPUT + "0, negative, very large and NaN", _INPUT_VI + "0, số âm, rất lớn và NaN"),
]
