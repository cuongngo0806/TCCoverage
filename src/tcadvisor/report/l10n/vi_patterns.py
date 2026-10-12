"""Vietnamese entries for ``classify/patterns.py`` (lesson patterns, spec 009 coupling), ``graph/dataflow.py``
(data-path roles) and ``graph/sources.py`` (trigger-source guards and flags).

Follows the style guide in ``vi.py``.
"""
from __future__ import annotations

ENTRIES: list[tuple[str, str]] = [
    # ---- shared ------------------------------------------------------------------------------------------------
    ("(no CMake target owns this file)", "(không có CMake target nào sở hữu file này)"),
    ("Lesson {lesson_id} ({title}): {ask}", "Bài học {lesson_id} ({title}): {ask}"),

    # ---- symmetric_counterpart ---------------------------------------------------------------------------------
    ("`{counterpart}` is the counterpart of the changed `{root}`: check both sides still agree",
     "`{counterpart}` là hàm đối xứng của `{root}` đã thay đổi: kiểm tra hai phía vẫn khớp nhau"),
    ("Changed `{root}`; counterpart by name",
     "`{root}` đã thay đổi; hàm đối xứng theo tên"),
    ("Round trip: data produced by `{root}` is accepted by `{counterpart}` (and the reverse), including boundary "
     "and error values",
     "Round trip: dữ liệu do `{root}` tạo ra được `{counterpart}` chấp nhận (và ngược lại), kể cả giá trị biên và "
     "giá trị lỗi"),
    ("Data written by the old version is still handled (compatibility)",
     "Dữ liệu do phiên bản cũ ghi vẫn được xử lý (tương thích)"),
    ("Error / partial paths are symmetric (what one side allocates, locks or registers, the other releases)",
     "Đường đi lỗi / dở dang đối xứng nhau (phía này cấp phát, lock hay đăng ký gì thì phía kia giải phóng cái đó)"),

    # ---- same_code_elsewhere -----------------------------------------------------------------------------------
    ("`{func}` contains the same code the change rewrote in `{root}`: check whether it needs the same fix",
     "`{func}` chứa cùng đoạn code mà thay đổi đã viết lại trong `{root}`: kiểm tra xem nó có cần sửa tương tự "
     "không"),
    ("`{code}` ({loc})", "`{code}` ({loc})"),
    ("Apply the scenario that motivated the change in `{root}` to `{func}` and compare the behaviour",
     "Áp dụng kịch bản đã dẫn đến thay đổi trong `{root}` cho `{func}` và so sánh hành vi"),
    ("If the copy is intentionally different, record why in the test result",
     "Nếu bản sao cố ý khác, ghi lại lý do trong kết quả test"),

    # ---- return_meaning ----------------------------------------------------------------------------------------
    ("`{caller}` decides on the result of `{root}`, which can now also return {values}: check that outcome",
     "`{caller}` ra quyết định dựa trên kết quả của `{root}`, hàm này giờ còn có thể trả về {values}: kiểm tra "
     "kết quả đó"),
    ("New return value(s) in `{root}`: {values}", "Giá trị trả về mới trong `{root}`: {values}"),
    ("Make `{root}` return {value} and check the branch `{caller}` takes",
     "Cho `{root}` trả về {value} và kiểm tra nhánh mà `{caller}` đi vào"),
    ("No caller treats the new value as success by accident (e.g. `if (r)` on an error code)",
     "Không caller nào vô tình coi giá trị mới là thành công (vd. `if (r)` trên một mã lỗi)"),

    # ---- shared_state ------------------------------------------------------------------------------------------
    ("`{reader}` reads `{name}`, which the change now writes differently in `{root}`: check it tolerates the new "
     "value and timing",
     "`{reader}` đọc `{name}`, biến mà thay đổi giờ ghi khác đi trong `{root}`: kiểm tra nó chịu được giá trị và "
     "thời điểm ghi mới"),
    ("`{root}` writes `{name}` on a changed line", "`{root}` ghi `{name}` trên một dòng bị thay đổi"),
    ("Exercise `{reader}` after `{root}` stored each new value of `{name}`",
     "Chạy `{reader}` sau khi `{root}` đã lưu từng giá trị mới của `{name}`"),
    ("Concurrent access: is the read synchronised with the new write?",
     "Truy cập đồng thời: việc đọc có được đồng bộ với lần ghi mới không?"),

    # ---- new_early_exit ----------------------------------------------------------------------------------------
    ("New early exit in `{root}`: check resources and callers on that path",
     "Early exit mới trong `{root}`: kiểm tra tài nguyên và các caller trên đường đi đó"),
    ("Added exit at {loc}", "Điểm thoát được thêm tại {loc}"),
    ("Reach the new exit at line {line} (`{code}`) and check everything set up before it is undone",
     "Đi tới điểm thoát mới ở dòng {line} (`{code}`) và kiểm tra mọi thứ được thiết lập trước đó đều được hoàn tác"),
    ("Acquired before the exit: {items} — released on this path?",
     "Được lấy trước điểm thoát: {items} — có được giải phóng trên đường đi này không?"),
    ("Callers of `{root}` handle the new outcome (no half-initialised state, no missing callback / reply)",
     "Các caller của `{root}` xử lý kết quả mới (không có trạng thái khởi tạo dở dang, không thiếu callback / "
     "phản hồi)"),

    # ---- config_reader -----------------------------------------------------------------------------------------
    ("`{reader}` also reads setting `{name}` used by the changed `{root}`: check both behave consistently for "
     "every value",
     "`{reader}` cũng đọc thiết lập `{name}` mà `{root}` đã thay đổi dùng: kiểm tra cả hai hoạt động nhất quán với "
     "mọi giá trị"),
    ("`{root}` reads `{name}` on a changed line", "`{root}` đọc `{name}` trên một dòng bị thay đổi"),
    ("Run with `{name}` at each value (default, on/off, min/max, unset) and compare `{root}` with `{reader}`",
     "Chạy với `{name}` ở từng giá trị (mặc định, bật/tắt, min/max, không đặt) và so sánh `{root}` với `{reader}`"),
    ("Changing the setting at runtime: both readers see the same value",
     "Đổi thiết lập lúc chạy: cả hai nơi đọc thấy cùng một giá trị"),

    # ---- new_enum_value ----------------------------------------------------------------------------------------
    ("`{func}` switches over `{enum}`, which gained {values}: check the new value is handled",
     "`{func}` switch trên `{enum}`, enum này có thêm {values}: kiểm tra giá trị mới được xử lý"),
    ("New enumerator(s) in `{root}`", "Enumerator mới trong `{root}`"),
    ("Pass {value} to `{func}`: handled explicitly, not by a silent `default:`",
     "Truyền {value} vào `{func}`: phải được xử lý tường minh, không rơi lặng lẽ vào `default:`"),
    ("Serialized / persisted values and tables indexed by the enum still line up",
     "Các giá trị đã serialize / lưu trữ và các bảng đánh index theo enum vẫn khớp nhau"),

    # ---- spec 009 coupling: suffixes added by emit() -----------------------------------------------------------
    ("{t_desc}, through the accessor `{accessor}` that returns `{name}`",
     "{t_desc}, thông qua accessor `{accessor}` trả về `{name}`"),
    ("{t_desc}, through the accessor `{accessor}` that returns `{name}` (+{n} more caller(s) of it not listed)",
     "{t_desc}, thông qua accessor `{accessor}` trả về `{name}` (+{n} caller khác của nó không được liệt kê)"),
    ("{t_desc} (+{n} more reader(s) not listed)", "{t_desc} (+{n} nơi đọc khác không được liệt kê)"),
    ("{t_desc}, through the accessor `{accessor}` that returns `{name}` (+{n} more caller(s) of it not listed) "
     "(+{m} more reader(s) not listed)",
     "{t_desc}, thông qua accessor `{accessor}` trả về `{name}` (+{n} caller khác của nó không được liệt kê) "
     "(+{m} nơi đọc khác không được liệt kê)"),
    ("{t_act} (read at {loc})", "{t_act} (đọc tại {loc})"),

    # ---- removed_write -----------------------------------------------------------------------------------------
    ("`{reader}` reads `{name}`, which `{root}` no longer writes: check it still behaves when the old update does "
     "not happen",
     "`{reader}` đọc `{name}`, biến mà `{root}` không còn ghi nữa: kiểm tra nó vẫn hoạt động đúng khi lần cập nhật "
     "cũ không xảy ra"),
    ("`{reader}` reads `{name}`, which `{root}` now writes differently: check it still behaves when the old update "
     "does not happen",
     "`{reader}` đọc `{name}`, biến mà `{root}` giờ ghi khác đi: kiểm tra nó vẫn hoạt động đúng khi lần cập nhật cũ "
     "không xảy ra"),
    ("`{root}`: `{old}` → `{new}`", "`{root}`: `{old}` → `{new}`"),
    ("`{root}`: `{old}` removed", "`{root}`: `{old}` bị xoá"),
    ("Run `{reader}` after `{root}` on the changed path and check the value of `{name}` it sees",
     "Chạy `{reader}` sau `{root}` trên đường đi đã thay đổi và kiểm tra giá trị của `{name}` mà nó thấy"),
    ("Concurrent / repeated calls: two calls in a row, interleaved with the reader",
     "Gọi đồng thời / lặp lại: hai lần gọi liên tiếp, xen kẽ với nơi đọc"),

    # ---- setter_readers ----------------------------------------------------------------------------------------
    ("`{reader}` reads `{getter}`, but `{root}` no longer calls `{setter}`: check the value it now sees",
     "`{reader}` đọc `{getter}`, nhưng `{root}` không còn gọi `{setter}`: kiểm tra giá trị nó thấy bây giờ"),
    ("`{root}` no longer calls `{setter}`", "`{root}` không còn gọi `{setter}`"),
    ("Drive `{root}` on the changed path, then `{reader}`: `{getter}` must still be what it expects (counts, sizes, "
     "state flags)",
     "Chạy `{root}` trên đường đi đã thay đổi, rồi `{reader}`: `{getter}` vẫn phải đúng như nó mong đợi (số đếm, "
     "kích thước, flag trạng thái)"),
    ("Mismatch checks / asserts on that value in the reader",
     "Các kiểm tra không khớp / assert trên giá trị đó ở nơi đọc"),

    # ---- lock_coupling -----------------------------------------------------------------------------------------
    ("`{reader}` also accesses `{member}`, which `{root}` uses with the lock on `{lock}` removed: check concurrent "
     "access",
     "`{reader}` cũng truy cập `{member}`, thành viên mà `{root}` dùng với lock trên `{lock}` đã bị xoá: kiểm tra "
     "truy cập đồng thời"),
    ("`{reader}` also accesses `{member}`, which `{root}` uses with the lock on `{lock}` added: check concurrent "
     "access",
     "`{reader}` cũng truy cập `{member}`, thành viên mà `{root}` dùng với lock trên `{lock}` được thêm: kiểm tra "
     "truy cập đồng thời"),
    ("`{root}`: `{stmt}` added", "`{root}`: `{stmt}` được thêm"),
    ("Call `{root}` and `{reader}` from two threads at once (data race on `{member}`)",
     "Gọi `{root}` và `{reader}` từ hai thread cùng lúc (data race trên `{member}`)"),
    ("Lock order: does the reader hold another lock while taking `{lock}`?",
     "Thứ tự lock: nơi đọc có đang giữ một lock khác khi lấy `{lock}` không?"),

    # ---- changed_default ---------------------------------------------------------------------------------------
    ("`{reader}` reads `{name}`, whose initial value changed in `{root}`: check it with the new default",
     "`{reader}` đọc `{name}`, giá trị khởi tạo của nó đã thay đổi trong `{root}`: kiểm tra nó với giá trị mặc định "
     "mới"),
    ("Run `{reader}` with the new default of `{name}` and with the old one (configs that set it explicitly)",
     "Chạy `{reader}` với giá trị mặc định mới của `{name}` và với giá trị cũ (các config đặt nó tường minh)"),
    ("Limits derived from `{name}` (minimum, maximum, clipping, division)",
     "Các giới hạn suy ra từ `{name}` (tối thiểu, tối đa, cắt ngưỡng, phép chia)"),

    # ---- conditional_write -------------------------------------------------------------------------------------
    ("`{reader}` reads `{name}`, which `{root}` writes only under the changed condition `{cond}`: check it in the "
     "states where the write now happens or no longer happens",
     "`{reader}` đọc `{name}`, biến mà `{root}` chỉ ghi dưới điều kiện đã thay đổi `{cond}`: kiểm tra nó trong các "
     "trạng thái mà lần ghi giờ xảy ra hoặc không còn xảy ra"),
    ("`{root}`: condition `{old}` → `{new}` guards a write to `{field}`",
     "`{root}`: điều kiện `{old}` → `{new}` chặn (guard) một lần ghi vào `{field}`"),
    ("Drive `{root}` with inputs on both sides of the changed condition, then `{reader}`: the value of `{name}` it "
     "sees must stay valid",
     "Chạy `{root}` với đầu vào ở cả hai phía của điều kiện đã thay đổi, rồi `{reader}`: giá trị của `{name}` mà nó "
     "thấy phải luôn hợp lệ"),
    ("Boundary value of the condition (exactly at the limit)", "Giá trị biên của điều kiện (đúng tại giới hạn)"),

    # ---- guard_removed_callee ----------------------------------------------------------------------------------
    ("`{callee}` is now called from `{root}` also when `{cond}` holds: check it handles that state",
     "`{callee}` giờ được gọi từ `{root}` cả khi `{cond}` đúng: kiểm tra nó xử lý được trạng thái đó"),
    ("`{callee}` is now called from `{root}` also when `{cond}` is false: check it handles that state",
     "`{callee}` giờ được gọi từ `{root}` cả khi `{cond}` sai: kiểm tra nó xử lý được trạng thái đó"),
    ("Condition removed in `{root}`: `{cond}` (call at {loc})",
     "Điều kiện bị xoá trong `{root}`: `{cond}` (lời gọi tại {loc})"),
    ("Call `{root}` so that `{cond}` holds and check `{callee}` (no crash, no corrupted state, correct result)",
     "Gọi `{root}` sao cho `{cond}` đúng và kiểm tra `{callee}` (không crash, không hỏng trạng thái, kết quả đúng)"),
    ("Call `{root}` so that `{cond}` is false and check `{callee}` (no crash, no corrupted state, correct result)",
     "Gọi `{root}` sao cho `{cond}` sai và kiểm tra `{callee}` (không crash, không hỏng trạng thái, kết quả đúng)"),
    ("`{callee}`'s own preconditions (asserts, documented assumptions) still hold",
     "Các điều kiện tiên quyết của chính `{callee}` (assert, giả định đã ghi trong tài liệu) vẫn đúng"),

    # ---- class_consumer ----------------------------------------------------------------------------------------
    ("`{reader}` reads `{member}`, which the modified `{root}` writes: check it still understands what is stored "
     "there",
     "`{reader}` đọc `{member}`, thành viên mà `{root}` đã sửa ghi vào: kiểm tra nó vẫn hiểu đúng dữ liệu được lưu "
     "ở đó"),
    ("`{root}` writes `{member}`", "`{root}` ghi `{member}`"),
    ("Round trip: store through `{root}`, read back through `{reader}` (boundary and empty values)",
     "Round trip: lưu qua `{root}`, đọc lại qua `{reader}` (giá trị biên và giá trị rỗng)"),
    ("Data stored by the old version (compatibility)", "Dữ liệu do phiên bản cũ lưu (tương thích)"),

    # ---- graph/dataflow.py: path roles ------------------------------------------------------------------------
    ("producer", "nơi tạo"),
    ("forwarder", "nơi chuyển tiếp"),
    ("emitter", "nơi gửi ra"),
    # trace break reasons and the flag pipeline.py builds from them are in vi_notes.py

    # ---- graph/sources.py: trigger-source guards and flags ------------------------------------------------------
    ("present", "có"),
    ("absent", "không có"),
    ("unknown", "không rõ"),
    ("n/a", "không áp dụng"),
    ("`{target}` is also used as a callback / function pointer ({loc}); calls made through it are trigger sources "
     "the guard added in {covered} does not cover",
     "`{target}` còn được dùng làm callback / con trỏ hàm ({loc}); các lời gọi qua nó là nguồn kích hoạt mà điều "
     "kiện chặn (guard) được thêm trong {covered} không bao phủ"),
    ("`{target}` is virtual: calls through a base-class pointer reach it from sources that cannot be listed "
     "statically; check them against the guard added in {covered}",
     "`{target}` là virtual: các lời gọi qua con trỏ class cơ sở tới nó từ những nguồn không liệt kê tĩnh được; "
     "kiểm tra chúng với điều kiện chặn (guard) được thêm trong {covered}"),
]
