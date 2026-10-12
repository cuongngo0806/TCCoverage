"""Vietnamese wording of the Markdown / brief report frame (render.py) and of the fixed labels it uses."""
from __future__ import annotations

ENTRIES: list[tuple[str, str]] = [
    # summary / plan lines (also printed by the CLI and the VS Code notification)
    ("{head}; {flags} uncertainty flag(s); {tests}{files} changed file(s); targets: {targets}; cache_hit: {cache}; "
     "LLM: {llm}; {secs}s",
     "{head}; {flags} điểm chưa chắc chắn; {tests}{files} file thay đổi; target: {targets}; cache_hit: {cache}; "
     "LLM: {llm}; {secs}s"),
    ("Test plan: {target} to test on target, {review} to review (code reading may close them), {closed} closed by "
     "code review",
     "Kế hoạch test: {target} test trên target, {review} cần review (đọc code có thể đóng), {closed} đã đóng bằng "
     "review code"),
    ("test results: {ok} pass / {bad} fail / {nt} n/t / {no} n/o / {untested} untested{recheck}; ",
     "kết quả test: {ok} đạt / {bad} không đạt / {nt} không thể test / {no} không thể xảy ra / {untested} chưa test"
     "{recheck}; "),
    (" / {n} re-check", " / {n} cần kiểm tra lại"),
    (" (+{n} more)", " (+{n} nữa)"),
    ("degraded (LLM unavailable)", "suy giảm (LLM không khả dụng)"),
    ("enabled", "bật"),
    ("disabled", "tắt"),
    ("No detected impact", "Không phát hiện ảnh hưởng"),
    ("{n} test case(s) [P1 {p1} / P2 {p2} / P3 {p3}]", "{n} test case [P1 {p1} / P2 {p2} / P3 {p3}]"),
    (" (re-check)", " (kiểm tra lại)"),
    (" — re-check", " — kiểm tra lại"),
    ("working tree", "thay đổi chưa commit"),
    # Markdown frame
    ("# Change Impact & Test Case Report", "# Báo cáo ảnh hưởng thay đổi & test case"),
    ("- **Change**: {mode} — {src}", "- **Thay đổi**: {mode} — {src}"),
    ("- **Repository**: `{repo}`", "- **Repository**: `{repo}`"),
    ("- **Summary**: {s}", "- **Tóm tắt**: {s}"),
    ("> **No detected impact.** The change touches no indexed symbol semantically (e.g. comments, whitespace or "
     "non-C++ files only). This is a positive result, not a tool failure.",
     "> **Không phát hiện ảnh hưởng.** Thay đổi không chạm tới ngữ nghĩa của symbol nào đã được index (ví dụ chỉ "
     "sửa comment, khoảng trắng hoặc file không phải C++). Đây là kết quả hợp lệ, không phải lỗi của tool."),
    ("## Changed symbols", "## Symbol bị thay đổi"),
    ("| Symbol | Change | Risk groups |", "| Symbol | Thay đổi | Nhóm rủi ro |"),
    ("## Impact flow", "## Luồng ảnh hưởng"),
    ("Arrows point from the affected code to what it depends on (red = changed, orange = direct, blue = indirect).",
     "Mũi tên đi từ code bị ảnh hưởng tới phần nó phụ thuộc (đỏ = bị thay đổi, cam = trực tiếp, xanh = gián tiếp)."),
    ("+{n} more nodes (see report.html)", "+{n} node nữa (xem report.html)"),
    ("## Test cases to check", "## Test case cần kiểm tra"),
    ("- **Test on target**: the risk only shows up when running on the device (concurrency, lifetime, data layout, "
     "build configuration, hardware / interrupt / timing / RTOS / bus code), or an AI reviewer read the code and "
     "could not close it.",
     "- **Test trên target**: rủi ro chỉ lộ ra khi chạy trên thiết bị (đồng thời, vòng đời bộ nhớ, layout dữ liệu, "
     "cấu hình build, code phần cứng / interrupt / timing / RTOS / bus), hoặc AI reviewer đã đọc code mà không đóng "
     "được."),
    ("- **Review code**: no runtime signal — reading the code may close it without a run (`tcadvisor verify --scope "
     "review`); test it on the target if nobody can.",
     "- **Review code**: không có tín hiệu lúc chạy — đọc code có thể đóng case mà không cần chạy (`tcadvisor verify "
     "--scope review`); nếu không ai đóng được thì test trên target."),
    ("- **Closed by code review**: an AI reviewer proved from the code that it cannot fail (proof file:line); listed "
     "so the decision stays auditable.",
     "- **Đã đóng bằng review code**: AI reviewer đã chứng minh từ code rằng case không thể lỗi (bằng chứng "
     "file:dòng); vẫn liệt kê để quyết định có thể kiểm tra lại."),
    ("Inside each group: relevance order (closest to the change, substantive before recompile-only, larger changes "
     "first); the P1/P2/P3 label is the deterministic priority.",
     "Trong mỗi nhóm: xếp theo độ liên quan (gần thay đổi nhất, thay đổi thực chất trước thay đổi chỉ cần biên dịch "
     "lại, thay đổi lớn trước); nhãn P1/P2/P3 là mức ưu tiên tất định."),
    ("Test on target", "Test trên target"),
    ("Review code", "Review code"),
    ("Closed by code review", "Đã đóng bằng review code"),
    ("changed code", "code bị thay đổi"),
    ("direct impact", "ảnh hưởng trực tiếp"),
    ("indirect impact", "ảnh hưởng gián tiếp"),
    ("  - *When*: {text}", "  - *Khi nào*: {text}"),
    ("  - *Evidence*: {text}", "  - *Bằng chứng*: {text}"),
    ("  - *Path*: {text}", "  - *Đường đi*: {text}"),
    (", checked", ", có kiểm tra"),
    ("  - *Corner cases*: {text}", "  - *Corner case*: {text}"),
    ("  - *Targets*: {text}", "  - *Target*: {text}"),
    ("  - *Needs the target*: {text}", "  - *Cần target vì*: {text}"),
    ("  - *Test result*: {verdict} by {tester} on {date}", "  - *Kết quả test*: {verdict} bởi {tester} ngày {date}"),
    ("; defect {ref}", "; defect {ref}"),
    ("; evidence: {names}", "; bằng chứng: {names}"),
    ("  - *AI verification*: **{verdict}**", "  - *AI kiểm tra*: **{verdict}**"),
    ("  - *Proof*: {text}", "  - *Chứng minh*: {text}"),
    ("  - *AI corner cases*: {text}", "  - *Corner case từ AI*: {text}"),
    ("## AI verification (annotations only — cases are never removed)",
     "## AI kiểm tra (chỉ chú thích — không bao giờ xoá case)"),
    ("- verified cases: {n}; models: {models}", "- số case đã kiểm tra: {n}; model: {models}"),
    ("- [ ] **Also check** (AI): {title} — {why}{ev}", "- [ ] **Kiểm tra thêm** (AI): {title} — {why}{ev}"),
    (" (unverified AI suggestion: no resolvable file:line)", " (gợi ý AI chưa xác minh: không có file:dòng hợp lệ)"),
    ("## Existing tests to re-run", "## Test hiện có cần chạy lại"),
    ("- `{test}` ({file}:{line}, hop {hop})", "- `{test}` ({file}:{line}, hop {hop})"),
    ("## Test gaps (no existing test reaches the change)", "## Chỗ thiếu test (chưa test nào chạm tới thay đổi)"),
    ("- [ ] `{sym}` ({file}:{line}) — {reason}: a new test is likely needed",
     "- [ ] `{sym}` ({file}:{line}) — {reason}: nhiều khả năng cần viết test mới"),
    ("## Trigger sources of `{sym}`", "## Nguồn kích hoạt của `{sym}`"),
    ("Guard added in {where}: `{guard}`", "Guard được thêm trong {where}: `{guard}`"),
    ("| Source | Kind | Guard | |", "| Nguồn | Loại | Guard | |"),
    ("callback registered at {file}:{line}", "callback đăng ký tại {file}:{line}"),
    (" (callback registered at {file}:{line})", " (callback đăng ký tại {file}:{line})"),
    ("call", "lời gọi"),
    ("covered by this change", "đã được thay đổi này xử lý"),
    ("check (see cases)", "cần kiểm tra (xem các case)"),
    ("## Where each changed function is triggered from", "## Mỗi hàm bị thay đổi được kích hoạt từ đâu"),
    ("Every source should be exercised: a fix verified from one source only is the classic miss.",
     "Cần chạy qua mọi nguồn: một bản sửa chỉ được kiểm tra từ một nguồn là lỗi bỏ sót kinh điển."),
    ("| Changed function | Source (caller) | Entry points behind it |",
     "| Hàm bị thay đổi | Nguồn (caller) | Điểm vào phía sau |"),
    ("… {n} more", "… {n} nữa"),
    ("## Uncertain — needs manual review", "## Chưa chắc chắn — cần review thủ công"),
    ("| Category | Symbol | Reason |", "| Loại | Symbol | Lý do |"),
    ("## Build / test scope to rerun", "## Phạm vi build / test cần chạy lại"),
    (" (links {via})", " (link {via})"),
    ("## Skipped (out of scope)", "## Bỏ qua (ngoài phạm vi)"),
    ("## Run notes", "## Ghi chú lần chạy"),
    ("## Metrics", "## Số liệu"),
    ("- duration: {s}s", "- thời gian chạy: {s}s"),
    # brief
    ("... {n} more in report.json", "... {n} case nữa trong report.json"),
    ("covered", "đã xử lý"),
    ("guard", "guard"),
    # labels
    ("Logic", "Logic"),
    ("ABI / layout", "ABI / layout"),
    ("Ownership / lifetime", "Sở hữu / vòng đời"),
    ("Thread safety", "An toàn thread"),
    ("Exception safety", "An toàn exception"),
    ("Build config", "Cấu hình build"),
    ("modified", "sửa đổi"),
    ("added", "thêm mới"),
    ("removed", "bị xoá"),
    ("PASS", "ĐẠT"),
    ("FAIL", "KHÔNG ĐẠT"),
    ("N/T", "KHÔNG THỂ TEST"),
    ("N/O", "KHÔNG THỂ XẢY RA"),
]
