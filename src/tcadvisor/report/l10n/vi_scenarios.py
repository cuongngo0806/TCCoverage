"""Vietnamese wording of the test-scenario plan (spec 013, ``render.scenarios_markdown`` / brief / HTML labels)."""
from __future__ import annotations

ENTRIES: list[tuple[str, str]] = [
    ("## Test scenarios — what to test now", "## Kịch bản test — cần test ngay"),
    ("## Test scenarios of these cases", "## Kịch bản test của các case này"),
    ("## Test case details", "## Chi tiết từng test case"),
    ("The evidence behind each scenario, one entry per case (`[S<n>]` = the scenario that covers it).",
     "Bằng chứng phía sau mỗi kịch bản, mỗi case một mục (`[S<n>]` = kịch bản bao phủ case đó)."),
    ("{n} scenario(s) cover {m} case(s): run one test per scenario, entering at the first function of its flow; the "
     "changed code is marked *(changed)*.",
     "{n} kịch bản bao phủ {m} case: mỗi kịch bản chạy một test, bắt đầu từ hàm đầu tiên của luồng; code bị thay đổi "
     "được đánh dấu *(đã thay đổi)*."),
    ("(diagram: first {n} scenarios)", "(sơ đồ: {n} kịch bản đầu tiên)"),
    ("### {id} · {prio} · {action} · {n} case(s)", "### {id} · {prio} · {action} · {n} case"),
    ("- [ ] **Run**: {flow}", "- [ ] **Chạy**: {flow}"),
    (" *(changed)*", " *(đã thay đổi)*"),
    ("- **Stands for**: {n} symbol(s) with the same link to the change: {names}",
     "- **Đại diện cho**: {n} symbol có cùng liên kết tới thay đổi: {names}"),
    ("- **Covers**: {cases} — {why}", "- **Bao phủ**: {cases} — {why}"),
    ("- **Check**:", "- **Kiểm tra**:"),
    ("  - … {n} more check(s) under the covered cases", "  - … còn {n} điểm kiểm tra nữa trong các case được bao phủ"),
    # relation labels (render.REL_LABEL)
    ("calls", "gọi"),
    ("member of", "thành viên của"),
    ("includes", "include"),
    ("derives / overrides", "kế thừa / override"),
    ("uses the type", "dùng kiểu"),
    ("instantiates", "khởi tạo template"),
    ("expands the macro", "mở rộng macro"),
]
