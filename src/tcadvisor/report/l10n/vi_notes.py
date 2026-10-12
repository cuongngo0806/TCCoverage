"""Vietnamese entries for run notes, uncertainty flags, test gaps, out-of-scope reasons and affected-target relations
emitted by the pipeline, ingest, index, impact graph, graph providers (codegraph / GitNexus) and LLM enrichment.

External data (exception text, tool stderr, paths, revisions) is always a verbatim placeholder. Raw third-party log
lines that leak into run notes are not translated.
"""
from __future__ import annotations

_REVIEW_DATA = " — review who reads it and whether they send it out"
_REVIEW_DATA_VI = " — cần review xem nơi nào đọc nó và có gửi nó ra ngoài hay không"
_GITNEXUS_DROPPED_VI = ("{count} nơi gọi `{name}` đã bị bỏ qua khi index vì không xác định được kiểu của đối tượng "
                        "nhận (ví dụ constructor chưa phân giải, factory hoặc biểu thức gọi nối chuỗi). Các caller đó "
                        "không có trong kết quả này — impact thực tế có thể cao hơn")


def _data_flag_entries() -> list[tuple[str, str]]:
    head = "data produced by the changed `{name}` leaves the traced paths: "
    head_vi = "dữ liệu do `{name}` đã thay đổi tạo ra đi ra khỏi các đường đi đã truy vết: "
    out = []
    for n in range(1, 6):
        slots = "; ".join(f"{{t_break{i}}}" for i in range(1, n + 1))
        out.append((head + slots + _REVIEW_DATA, head_vi + slots + _REVIEW_DATA_VI))
    out.append((head + slots + " and {more} more" + _REVIEW_DATA,
                head_vi + slots + " và {more} chỗ khác" + _REVIEW_DATA_VI))
    return out


ENTRIES: list[tuple[str, str]] = [
    # -- affected targets (pipeline.py) --------------------------------------------------------------------------
    ("compiles_affected_file", "biên dịch file bị ảnh hưởng"),
    ("link_to_target", "link tới target bị ảnh hưởng"),

    # -- out of scope (pipeline.py, ingest/changes.py) -----------------------------------------------------------
    ("not a C/C++ or CMake file; not analysed", "không phải file C/C++ hoặc CMake; không được phân tích"),
    ("file is not compiled by any target in the compile database (not part of the analysed module)",
     "file không được target nào trong compile database biên dịch (không thuộc module được phân tích)"),
    ("belongs only to target(s) {targets} outside the --targets scope",
     "chỉ thuộc (các) target {targets} nằm ngoài phạm vi --targets"),

    # -- test gaps (pipeline.py) ---------------------------------------------------------------------------------
    ("no existing test reaches it within {depth} hop(s)",
     "không có test hiện có nào chạm tới nó trong phạm vi {depth} hop"),

    # -- run notes: pipeline.py ----------------------------------------------------------------------------------
    ("reduced accuracy: {t_error} Change classification uses fallback compiler flags; impact comes from {provider}",
     "độ chính xác giảm: {t_error} Việc phân loại thay đổi dùng compiler flag dự phòng; ảnh hưởng (impact) lấy từ "
     "{provider}"),
    ("no CMake target mapping: {t_error}", "không có ánh xạ sang target CMake: {t_error}"),
    ("{provider} indexes the working tree, which is not identical to {rev}; check out the range end for exact "
     "provider impact",
     "{provider} index working tree, vốn không giống hệt {rev}; hãy checkout commit cuối của range để có impact "
     "chính xác từ provider"),
    ("range end {rev} is not the checked-out HEAD; the dependency index reflects the working tree, so unchanged-file "
     "line numbers may differ",
     "commit cuối của range {rev} không phải HEAD đang checkout; index phụ thuộc phản ánh working tree nên số dòng "
     "trong các file không thay đổi có thể bị lệch"),
    ("`{name}` was removed together with its file {path}; only its remaining dependents (if any) are reported",
     "`{name}` đã bị xoá cùng với file {path} của nó; chỉ báo cáo các phần phụ thuộc còn lại (nếu có)"),
    ("{count} files changed (> {threshold}); analysed as {units} per-target units",
     "{count} file thay đổi (> {threshold}); được phân tích thành {units} đơn vị theo từng target"),
    ("degraded (LLM unavailable): {error}; deterministic descriptions used",
     "chạy ở chế độ giảm cấp (LLM không khả dụng): {error}; dùng mô tả tất định"),
    ("libclang reported {count} error diagnostic(s) in {tus} translation unit(s); results for code that failed to "
     "parse may be incomplete",
     "libclang báo {count} diagnostic lỗi trong {tus} translation unit; kết quả cho phần code không parse được có "
     "thể không đầy đủ"),
    ("data paths not traced: no compile database",
     "không truy vết đường đi dữ liệu: không có compile database"),
    ("data paths traced over {count} translation unit(s) (--flow-max-tus); longer paths are flagged, not traced",
     "đường đi dữ liệu chỉ được truy vết trên {count} translation unit (--flow-max-tus); các đường đi dài hơn được "
     "gắn flag, không được truy vết"),
    ("{count} standard-library call(s) on changed lines are not traced into the library",
     "{count} lời gọi thư viện chuẩn trên các dòng thay đổi không được truy vết vào bên trong thư viện"),
    ("{count} third-party call(s) inside logging statements on changed lines are not analysed",
     "{count} lời gọi thư viện bên thứ ba bên trong câu lệnh logging trên các dòng thay đổi không được phân tích"),
    # older analyzer versions (provider fallback to a libclang sub-index)
    ("{count} root(s) unresolved by {provider}; their dependents come from a libclang index of the {tus} "
     "translation unit(s) that include them",
     "{count} root không được {provider} phân giải; các phần phụ thuộc của chúng lấy từ index libclang của {tus} "
     "translation unit include chúng"),
    ("libclang fallback skipped: {count} TUs include the unresolved roots (> --fallback-max-tus {limit}); they are "
     "flagged for manual review",
     "bỏ qua fallback libclang: {count} TU include các root chưa phân giải (> --fallback-max-tus {limit}); chúng "
     "được gắn flag để review thủ công"),

    # -- run notes: ingest/changes.py ----------------------------------------------------------------------------
    ("{path}: only #include directives changed (no semantic root; dependencies are re-indexed)",
     "{path}: chỉ các chỉ thị #include thay đổi (không có root ngữ nghĩa; các phụ thuộc được index lại)"),

    # -- prerequisite errors embedded in run notes (index/compile_db.py, index/cmake_targets.py) ------------------
    ("compile_commands.json not found in build dir '{build_dir}'. Configure the module with "
     "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON (see quickstart.md, Prerequisites).",
     "không tìm thấy compile_commands.json trong thư mục build '{build_dir}'. Hãy configure module với "
     "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON (xem quickstart.md, Prerequisites)."),
    ("compile_commands.json in '{build_dir}' is not valid JSON: {error}",
     "compile_commands.json trong '{build_dir}' không phải JSON hợp lệ: {error}"),
    ("compile_commands.json in '{build_dir}' is empty.", "compile_commands.json trong '{build_dir}' rỗng."),
    ("compile_commands.json in '{build_dir}' is stale: older than {files}. Re-run the CMake configure step (or pass "
     "--allow-stale-compile-db to accept reduced accuracy explicitly).",
     "compile_commands.json trong '{build_dir}' đã cũ: cũ hơn {files}. Chạy lại bước configure CMake (hoặc truyền "
     "--allow-stale-compile-db để chấp nhận rõ ràng độ chính xác giảm)."),
    ("CMake File API reply directory not found: '{reply}'. Create the query file "
     "'<build>/.cmake/api/v1/query/codemodel-v2' (empty file) and re-run the CMake configure step so the File API "
     "reply is generated.",
     "không tìm thấy thư mục reply của CMake File API: '{reply}'. Hãy tạo file query "
     "'<build>/.cmake/api/v1/query/codemodel-v2' (file rỗng) và chạy lại bước configure CMake để sinh reply của "
     "File API."),
    ("No CMake File API index file in '{reply}'. Create the query file '<build>/.cmake/api/v1/query/codemodel-v2' "
     "(empty file) and re-run the CMake configure step so the File API reply is generated.",
     "không có file index của CMake File API trong '{reply}'. Hãy tạo file query "
     "'<build>/.cmake/api/v1/query/codemodel-v2' (file rỗng) và chạy lại bước configure CMake để sinh reply của "
     "File API."),
    ("CMake File API reply in '{reply}' has no codemodel-v2 object. Create the query file "
     "'<build>/.cmake/api/v1/query/codemodel-v2' (empty file) and re-run the CMake configure step so the File API "
     "reply is generated.",
     "reply của CMake File API trong '{reply}' không có object codemodel-v2. Hãy tạo file query "
     "'<build>/.cmake/api/v1/query/codemodel-v2' (file rỗng) và chạy lại bước configure CMake để sinh reply của "
     "File API."),

    # -- run notes: graph providers (providers/base.py, codegraph.py, gitnexus.py) --------------------------------
    ("{count} provider node(s) without a source file are not on any impact path",
     "{count} node của provider không có file nguồn và không nằm trên đường đi impact nào"),
    ("codegraph index built in {path}", "đã build index codegraph tại {path}"),
    ("codegraph index synced in {path}", "đã đồng bộ index codegraph tại {path}"),
    ("codegraph impact failed for `{name}`: {error}", "codegraph impact thất bại cho `{name}`: {error}"),
    ("codegraph has no definition matching `{name}` ({location})",
     "codegraph không có định nghĩa nào khớp với `{name}` ({location})"),
    ("codegraph: `{name}` matched {count} definitions; their impact is merged",
     "codegraph: `{name}` khớp {count} định nghĩa; impact của chúng được gộp lại"),
    ("codegraph returned unexpected data for `{name}`: {error}",
     "codegraph trả về dữ liệu không như mong đợi cho `{name}`: {error}"),
    ("gitnexus index refreshed (--index-only). NOTE: GitNexus is PolyForm-Noncommercial licensed",
     "đã làm mới index gitnexus (--index-only). LƯU Ý: GitNexus dùng giấy phép PolyForm-Noncommercial"),
    ("gitnexus impact failed for `{name}`: {error}", "gitnexus impact thất bại cho `{name}`: {error}"),
    ("gitnexus returned unexpected data for `{name}`: {error}",
     "gitnexus trả về dữ liệu không như mong đợi cho `{name}`: {error}"),
    ("gitnexus: no node for `{name}`", "gitnexus: không có node cho `{name}`"),

    # -- uncertainty flags: pipeline.py / providers ---------------------------------------------------------------
    ("{provider} could not resolve `{name}`; its dependents are unknown — review manually",
     "{provider} không phân giải được `{name}`; chưa biết các phần phụ thuộc của nó — cần review thủ công"),
    ("{provider} could not resolve `{name}` and no compile-database graph is available; its dependents are unknown "
     "— review manually",
     "{provider} không phân giải được `{name}` và không có graph từ compile database; chưa biết các phần phụ thuộc "
     "của nó — cần review thủ công"),
    ("{count} dependent(s) of `{name}` reported by the graph provider have no source file in the repository "
     "({names}); they are outside the analysed code — review manually",
     "{count} phần phụ thuộc của `{name}` do graph provider báo cáo không có file nguồn trong repository ({names}); "
     "chúng nằm ngoài phần code được phân tích — cần review thủ công"),
    ("`{name}` calls code outside the repository on changed lines: {calls}; its behaviour is not in the static "
     "graph — check the call site for error/null returns, exceptions, ownership of passed/returned pointers and "
     "callbacks",
     "`{name}` gọi code nằm ngoài repository trên các dòng thay đổi: {calls}; hành vi của nó không có trong graph "
     "tĩnh — kiểm tra nơi gọi với giá trị trả về lỗi/null, exception, quyền sở hữu pointer được truyền vào/trả về "
     "và callback"),
    # data-path flag: one slot per "; "-joined break (at most 5 are listed), so that a break ending in a
    # placeholder never swallows the next one
    *_data_flag_entries(),
    # the "; "-joined parts of {t_breaks} (graph/dataflow.py break reason + " in " + where)
    ("passed to `{callee}`, not traced (translation-unit budget reached) in {where}",
     "được truyền cho `{callee}`, không được truy vết (đã hết ngân sách translation unit) tại {where}"),
    ("passed to `{callee}`, not traced (its definition is not in an indexed translation unit) in {where}",
     "được truyền cho `{callee}`, không được truy vết (định nghĩa của nó không nằm trong translation unit nào đã "
     "index) tại {where}"),
    ("stored into `{store}` via `{callee}` in {where}", "được lưu vào `{store}` qua `{callee}` tại {where}"),
    ("still passed on to `{callee}` when the depth limit ({depth} functions) was reached in {where}",
     "vẫn còn được truyền tiếp cho `{callee}` khi chạm giới hạn độ sâu ({depth} hàm) tại {where}"),
    ("stored in {stores} with no traced reader in {where}",
     "được lưu vào {stores} nhưng không truy vết được nơi đọc nào tại {where}"),
    ("returned to {count} caller(s) when the depth limit was reached in {where}",
     "được trả về cho {count} caller khi chạm giới hạn độ sâu tại {where}"),
    # GitNexus impact boundaries (gitnexus.py wraps the tool's own wording as "GitNexus: {boundary}")
    ("GitNexus: {t_boundary}", "GitNexus: {t_boundary}"),
    ("{count} call site invoking `{name}` was dropped at index time because the receiver's type could not be "
     "established (e.g. an unresolved constructor, factory or chained expression). Those callers are absent from "
     "this result — actual impact may be higher.", _GITNEXUS_DROPPED_VI + "."),
    ("{count} call sites invoking `{name}` were dropped at index time because the receiver's type could not be "
     "established (e.g. an unresolved constructor, factory or chained expression). Those callers are absent from "
     "this result — actual impact may be higher.", _GITNEXUS_DROPPED_VI + "."),
    ("{count} call site invoking `{name}` was dropped at index time because the receiver's type could not be "
     "established (e.g. an unresolved constructor, factory or chained expression). Those callers are absent from "
     "this result — actual impact may be higher", _GITNEXUS_DROPPED_VI),
    ("{count} call sites invoking `{name}` were dropped at index time because the receiver's type could not be "
     "established (e.g. an unresolved constructor, factory or chained expression). Those callers are absent from "
     "this result — actual impact may be higher", _GITNEXUS_DROPPED_VI),
    ("{name} is an interface with {count} implementations; callers that bind via the interface (e.g. a DI container "
     "or dynamic dispatch) are not traced to the concrete symbol — actual impact may be higher.",
     "{name} là interface có {count} implementation; các caller gắn qua interface (ví dụ DI container hoặc dynamic "
     "dispatch) không được truy vết tới symbol cụ thể — impact thực tế có thể cao hơn."),
    ("{name} is an interface with {count} implementations and {consumers} interface-level consumer; callers that "
     "bind via the interface (e.g. a DI container or dynamic dispatch) are not traced to the concrete symbol — actual "
     "impact may be higher.",
     "{name} là interface có {count} implementation và {consumers} nơi dùng ở mức interface; các caller gắn qua "
     "interface (ví dụ DI container hoặc dynamic dispatch) không được truy vết tới symbol cụ thể — impact thực tế có "
     "thể cao hơn."),
    ("{name} is an interface with {count} implementations and {consumers} interface-level consumers; callers that "
     "bind via the interface (e.g. a DI container or dynamic dispatch) are not traced to the concrete symbol — actual "
     "impact may be higher.",
     "{name} là interface có {count} implementation và {consumers} nơi dùng ở mức interface; các caller gắn qua "
     "interface (ví dụ DI container hoặc dynamic dispatch) không được truy vết tới symbol cụ thể — impact thực tế có "
     "thể cao hơn."),
    ("unit-test code left out (include_tests is off): {a} changed symbol(s), {b} impacted test function(s) / "
     "file(s)",
     "đã bỏ qua code unit test (include_tests đang tắt): {a} symbol thay đổi, {b} hàm / file test bị ảnh hưởng"),
    ("unit-test code: not analysed (include_tests is off)", "code unit test: không phân tích (include_tests đang tắt)"),
    # -- spec 012: run folders, build profile ------------------------------------------------------------------
    ("no confirmed build profile: nothing filtered; run 'tcadvisor profile' to confirm the build variants",
     "chưa có build profile đã xác nhận: không lọc gì; chạy 'tcadvisor profile' để xác nhận các biến thể build"),
    ("build profile ignored for this run (--no-variant-filter): nothing filtered",
     "lần chạy này bỏ qua build profile (--no-variant-filter): không lọc gì"),
    ("unknown variant(s) {names} ignored (profile: {known})",
     "bỏ qua (các) biến thể không có trong profile: {names} (profile: {known})"),
    ("test results carried over from the latest run {run} (by case key); pass --previous-report to choose another "
     "filled report",
     "kết quả test được chuyển từ lần chạy gần nhất {run} (theo key của case); dùng --previous-report để chọn report "
     "đã điền khác"),
    ("compile_commands.json not found in '{build_dir}'. Create it from the build log of this module: tcadvisor "
     "compile-db --repo . --from-log <log.do_compile or make V=1 log> (docs/linux-yocto.md).",
     "không tìm thấy compile_commands.json trong '{build_dir}'. Tạo nó từ log build của module này: tcadvisor "
     "compile-db --repo . --from-log <log.do_compile hoặc log của make V=1> (docs/linux-yocto.md)."),
    ("no compile database for this autotools module: compile flags, include paths and defines are unknown, so "
     "preprocessor branches and header parsing use fallback flags",
     "module autotools này chưa có compile database: không biết compile flag, include path và define, nên các nhánh "
     "tiền xử lý và việc parse header dùng flag dự phòng"),
    ("{where}: `{construct}` cannot be resolved without running automake / configure; products or sources it adds "
     "are not mapped",
     "{where}: không phân giải được `{construct}` nếu không chạy automake / configure; sản phẩm hoặc source mà nó thêm "
     "vào không được ánh xạ"),
    ("not built by any product: no Makefile.am lists this source",
     "không được build bởi sản phẩm nào: không Makefile.am nào liệt kê source này"),
    ("unknown build target(s): {names} (known: {known})", "target build không tồn tại: {names} (có: {known})"),
    ("{n} case(s) moved to 'not built in the confirmed variants' (variants: {variants})",
     "{n} case đã chuyển sang 'không được build trong các biến thể đã xác nhận' (biến thể: {variants})"),
    ("the build description changed since the build profile was confirmed: filtering still uses the saved variants; "
     "re-run 'tcadvisor profile' to update them",
     "mô tả build đã thay đổi từ khi build profile được xác nhận: việc lọc vẫn dùng các biến thể đã lưu; chạy lại "
     "'tcadvisor profile' để cập nhật"),
    ("{where} is guarded by `{cond}`, which cannot be evaluated for variant(s) {names} (macro values unknown); the "
     "case is kept",
     "{where} nằm trong `{cond}`, điều kiện không đánh giá được cho (các) biến thể {names} (không biết giá trị "
     "macro); case vẫn được giữ"),
]
