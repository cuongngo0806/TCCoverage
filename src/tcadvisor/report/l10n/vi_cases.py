"""Vietnamese catalog for the case / risk / evidence text of ``classify/rules.py``, ``classify/cases.py``,
``classify/environment.py``, ``classify/external.py``, ``classify/lessons.py``, ``evidence/uncertainty.py`` and
``evidence/gate.py`` (risk details and hints, case descriptions and activation conditions, target reasons,
third-party API corner cases, uncertainty flag reasons). Style guide and glossary: see ``vi.py``.

Sub-reason tags in descriptions (``— mutex``, ``(modified, header change)``) stay as is: they are category tags.
"""
from __future__ import annotations

ENTRIES: list[tuple[str, str]] = [
    # ---- cases.py: labels -----------------------------------------------------------------------
    ("functional behaviour", "hành vi chức năng"),
    ("binary / layout compatibility", "tương thích nhị phân / layout"),
    ("object ownership and lifetime", "quyền sở hữu và vòng đời đối tượng"),
    ("thread safety", "an toàn thread"),
    ("exception safety", "an toàn exception"),
    ("behaviour across build configurations", "hành vi trên các cấu hình build"),
    # change kinds (root_kind / SymbolChange.change_kind)
    ("modified", "bị thay đổi"),
    ("added", "được thêm"),
    ("removed", "bị xoá"),
    ("file", "file"),
    ("explicit", "được chỉ định trực tiếp"),
    # hop words
    ("direct", "trực tiếp"),
    ("indirect, {n} hops", "gián tiếp, {n} hop"),
    # relation phrases (REL_PHRASE + "`{symbol}`")
    ("calls `{sym}`", "gọi `{sym}`"),
    ("inherits from / overrides `{sym}`", "kế thừa từ / override `{sym}`"),
    ("uses `{sym}`", "dùng `{sym}`"),
    ("instantiates `{sym}`", "khởi tạo (instantiate) `{sym}`"),
    ("expands macro `{sym}`", "mở rộng macro `{sym}`"),
    ("includes `{sym}`", "include `{sym}`"),
    ("links `{sym}`", "link tới `{sym}`"),
    ("is a member of `{sym}`", "là thành viên của `{sym}`"),
    ("is now called differently by `{sym}`", "giờ được gọi theo cách khác bởi `{sym}`"),
    ("depends on the change", "phụ thuộc vào thay đổi"),
    # path roles of sibling-source cases
    ("source", "nguồn"),
    ("target", "hàm đích"),
    ("(no CMake target owns this file)", "(không có CMake target nào sở hữu file này)"),

    # ---- cases.py: descriptions -----------------------------------------------------------------
    ("Verify the {t_group} of `{sym}` ({t_kind}, {sub})", "Kiểm tra {t_group} của `{sym}` ({t_kind}, {sub})"),
    ("Verify the {t_group} of `{sym}` ({t_kind})", "Kiểm tra {t_group} của `{sym}` ({t_kind})"),
    ("Verify how `{sym}` handles failures and unusual behaviour of the third-party API it now calls ({t_group} first)",
     "Kiểm tra cách `{sym}` xử lý lỗi và hành vi bất thường của API bên thứ ba mà nó giờ gọi tới (ưu tiên {t_group})"),
    ("Re-run existing test `{test}` and check it still covers the {t_group} of the change (it {t_via}; {t_hop}) — {subs}",
     "Chạy lại test hiện có `{test}` và kiểm tra nó vẫn bao phủ {t_group} của thay đổi (nó {t_via}; {t_hop}) — {subs}"),
    ("Re-run existing test `{test}` and check it still covers the {t_group} of the change (it {t_via}; {t_hop})",
     "Chạy lại test hiện có `{test}` và kiểm tra nó vẫn bao phủ {t_group} của thay đổi (nó {t_via}; {t_hop})"),
    ("Recompile and re-test all code including header `{path}` ({t_hop}; it {t_via}) — {subs}",
     "Biên dịch lại và test lại toàn bộ code include header `{path}` ({t_hop}; nó {t_via}) — {subs}"),
    ("Recompile and re-test all code including header `{path}` ({t_hop}; it {t_via})",
     "Biên dịch lại và test lại toàn bộ code include header `{path}` ({t_hop}; nó {t_via})"),
    ("Rebuild and smoke-test translation unit `{path}` ({t_hop}; it {t_via}) — {subs}",
     "Build lại và smoke-test translation unit `{path}` ({t_hop}; nó {t_via}) — {subs}"),
    ("Rebuild and smoke-test translation unit `{path}` ({t_hop}; it {t_via})",
     "Build lại và smoke-test translation unit `{path}` ({t_hop}; nó {t_via})"),
    ("Re-verify the {t_group} of `{sym}`, which {t_via} ({t_hop}) — {subs}",
     "Kiểm tra lại {t_group} của `{sym}`, vì nó {t_via} ({t_hop}) — {subs}"),
    ("Re-verify the {t_group} of `{sym}`, which {t_via} ({t_hop})",
     "Kiểm tra lại {t_group} của `{sym}`, vì nó {t_via} ({t_hop})"),
    # merge_pattern_cases: the same code found by two reasons
    ("{t_first} Also ({pattern}): {t_second}", "{t_first} Ngoài ra ({pattern}): {t_second}"),
    # activation conditions
    ("Changed directly: {t_detail}", "Thay đổi trực tiếp: {t_detail}"),
    ("Reachable from changed {roots} and others: {t_detail}",
     "Đi tới được từ {roots} và các phần khác đã thay đổi: {t_detail}"),
    ("Reachable from changed {roots}: {t_detail}", "Đi tới được từ {roots} đã thay đổi: {t_detail}"),

    # ---- cases.py: sibling trigger sources (spec 006 US2) -----------------------------------------
    ("`{target}` has {n} more trigger source(s) not protected like {covered}: {sources}",
     "`{target}` còn {n} nguồn kích hoạt khác không được bảo vệ như {covered}: {sources}"),
    ("Guard added in {covered}: {guard}", "Điều kiện chặn (guard) được thêm trong {covered}: {guard}"),
    ("Check each listed source reaches `{target}` only in states the new guard allows",
     "Kiểm tra mỗi nguồn được liệt kê chỉ đi tới `{target}` trong các trạng thái mà guard mới cho phép"),
    ("Confirm the existing check in `{source}` (a callback registered at {registered}) is equivalent to the guard "
     "added in {covered} before calling `{target}`",
     "Xác nhận phần kiểm tra hiện có trong `{source}` (một callback được đăng ký tại {registered}) tương đương với "
     "guard được thêm trong {covered} trước khi gọi `{target}`"),
    ("Confirm the existing check in `{source}` is equivalent to the guard added in {covered} before calling `{target}`",
     "Xác nhận phần kiểm tra hiện có trong `{source}` tương đương với guard được thêm trong {covered} trước khi gọi "
     "`{target}`"),
    ("`{target}` is also triggered from `{source}` (a callback registered at {registered}): check that the situation "
     "now guarded in {covered} cannot reach it this way",
     "`{target}` cũng được kích hoạt từ `{source}` (một callback được đăng ký tại {registered}): kiểm tra rằng tình "
     "huống giờ được chặn trong {covered} không thể đi tới nó theo đường này"),
    ("`{target}` is also triggered from `{source}`: check that the situation now guarded in {covered} cannot reach it "
     "this way",
     "`{target}` cũng được kích hoạt từ `{source}`: kiểm tra rằng tình huống giờ được chặn trong {covered} không thể "
     "đi tới nó theo đường này"),
    ("Drive `{source}` into the state the new guard rejects ({ids}) and check `{target}` is not reached or handles it",
     "Đưa `{source}` vào trạng thái mà guard mới từ chối ({ids}) và kiểm tra `{target}` không được gọi tới hoặc xử "
     "lý được trạng thái đó"),
    ("Compare with {covered}: same condition, same error handling / logging, same return value",
     "So sánh với {covered}: cùng điều kiện, cùng cách xử lý lỗi / log, cùng giá trị trả về"),
    ("The callback can fire at any time after registration at {registered}: trigger it while the guarded condition "
     "holds",
     "Callback có thể chạy bất cứ lúc nào sau khi đăng ký tại {registered}: kích hoạt nó trong khi điều kiện bị chặn "
     "đang đúng"),
    ("The call is not visible in the source text (macro / indirection): confirm the path manually",
     "Lời gọi không thấy được trong mã nguồn (macro / gián tiếp): cần xác nhận đường đi thủ công"),

    # ---- cases.py: data paths (spec 006 US1) ------------------------------------------------------
    ("`{emitter}` sends data that originates in the changed `{producer}` ({chain}) through `{call}`: confirm the check "
     "in {where} covers the values `{producer2}` can now produce",
     "`{emitter}` gửi dữ liệu bắt nguồn từ `{producer}` đã thay đổi ({chain}) qua `{call}`: xác nhận phần kiểm tra "
     "trong {where} bao phủ các giá trị mà `{producer2}` giờ có thể tạo ra"),
    ("`{emitter}` sends data that originates in the changed `{producer}` ({chain}) through `{call}`: check it "
     "validates the data itself instead of trusting the producer",
     "`{emitter}` gửi dữ liệu bắt nguồn từ `{producer}` đã thay đổi ({chain}) qua `{call}`: kiểm tra nó tự xác thực "
     "dữ liệu thay vì tin vào nơi tạo ra dữ liệu"),
    ("Feed `{emitter}` with every value `{producer}` can now produce (boundary, invalid, empty, maximum length) and "
     "check what goes out through `{call}`",
     "Đưa vào `{emitter}` mọi giá trị mà `{producer}` giờ có thể tạo ra (biên, không hợp lệ, rỗng, độ dài tối đa) và "
     "kiểm tra những gì được gửi ra qua `{call}`"),
    ("`{emitter}` owns what it sends: malformed input must be rejected or corrected, not forwarded",
     "`{emitter}` chịu trách nhiệm cho những gì nó gửi: đầu vào sai định dạng phải bị từ chối hoặc sửa lại, không "
     "được chuyển tiếp"),
    ("Compare the outgoing data with the interface specification of the receiver (format, ranges, mandatory fields)",
     "So sánh dữ liệu gửi ra với đặc tả interface của bên nhận (định dạng, khoảng giá trị, các trường bắt buộc)"),
    ("Existing check: {where} — confirm it rejects the new values, not only the old ones",
     "Kiểm tra hiện có: {where} — xác nhận nó từ chối các giá trị mới, không chỉ các giá trị cũ"),
    ("Data path from the changed `{producer}` (line {line}): {chain}",
     "Đường đi dữ liệu từ `{producer}` đã thay đổi (dòng {line}): {chain}"),
    ("Data path: {chain}", "Đường đi dữ liệu: {chain}"),
    ("`{name}` passes data from the changed `{producer}` on to `{emitter}` after checking it",
     "`{name}` chuyển dữ liệu từ `{producer}` đã thay đổi sang `{emitter}` sau khi kiểm tra nó"),
    ("`{name}` passes data from the changed `{producer}` on to `{emitter}` without checking it",
     "`{name}` chuyển dữ liệu từ `{producer}` đã thay đổi sang `{emitter}` mà không kiểm tra nó"),
    ("Pass the values `{producer}` can now produce through `{name}` and check nothing it does (copy, conversion, "
     "truncation) changes their meaning",
     "Cho các giá trị mà `{producer}` giờ có thể tạo ra đi qua `{name}` và kiểm tra không thao tác nào của nó (sao "
     "chép, chuyển đổi, cắt bớt) làm thay đổi ý nghĩa của chúng"),

    # ---- rules.py: risk details -------------------------------------------------------------------
    ("test code changed: {where}", "code test bị thay đổi: {where}"),
    ("only logging statements changed in {where}", "chỉ các câu lệnh log trong {where} bị thay đổi"),
    ("CMake build definition {path} changed", "định nghĩa build CMake {path} bị thay đổi"),
    ("macro `{name}` ({loc}) definition {t_kind}", "định nghĩa macro `{name}` ({loc}) {t_kind}"),
    ("change in {where} is inside `{condition}`", "thay đổi trong {where} nằm bên trong `{condition}`"),
    ("preprocessor directives changed near {where}: {lines}", "các chỉ thị tiền xử lý gần {where} bị thay đổi: {lines}"),
    ("`{tokens}` changed in {where}", "`{tokens}` bị thay đổi trong {where}"),
    ("members reordered", "thứ tự các thành viên bị thay đổi"),
    ("member types changed: {members}", "kiểu của thành viên bị thay đổi: {members}"),
    ("members added {added}, removed {removed}", "thêm thành viên {added}, xoá thành viên {removed}"),
    ("members added {added}", "thêm thành viên {added}"),
    ("members removed {removed}", "xoá thành viên {removed}"),
    ("data layout of {where} changed ({t_what})", "layout dữ liệu của {where} bị thay đổi ({t_what})"),
    ("virtual function table of {where} changed; new pure virtual {names}",
     "bảng hàm ảo (vtable) của {where} bị thay đổi; hàm pure virtual mới {names}"),
    ("virtual function table of {where} changed", "bảng hàm ảo (vtable) của {where} bị thay đổi"),
    ("base classes of {where} changed", "các class cơ sở của {where} bị thay đổi"),
    ("enumerators of {where} changed (switch coverage, serialized values)",
     "các giá trị enum của {where} bị thay đổi (độ bao phủ của switch, giá trị được serialize)"),
    ("signature of {where} changed: `{old}` -> `{new}`", "chữ ký của {where} bị thay đổi: `{old}` -> `{new}`"),
    ("{where} was removed; remaining users must be updated", "{where} đã bị xoá; các nơi còn dùng phải được cập nhật"),
    ("inline body of {where} changed (compiled into every includer)",
     "thân inline của {where} bị thay đổi (được biên dịch vào mọi nơi include)"),
    ("header {path} changed at file scope (includes: {includes})",
     "header {path} bị thay đổi ở phạm vi file (include: {includes})"),
    ("header {path} changed at file scope", "header {path} bị thay đổi ở phạm vi file"),
    ("{where} declared in a header changed; every includer recompiles",
     "{where} được khai báo trong header đã thay đổi; mọi nơi include đều phải biên dịch lại"),
    ("pointer ownership changed in {where}: {tokens}", "quyền sở hữu pointer bị thay đổi trong {where}: {tokens}"),
    ("non-const reference parameter / reference return or member changed in {where}",
     "tham số reference không const / giá trị trả về reference hoặc thành viên reference bị thay đổi trong {where}"),
    ("move semantics changed in {where}: {tokens}", "ngữ nghĩa move bị thay đổi trong {where}: {tokens}"),
    ("locking/threading primitives changed in {where}: {tokens}",
     "các primitive lock/thread bị thay đổi trong {where}: {tokens}"),
    ("atomic/volatile usage changed in {where}: {tokens}", "cách dùng atomic/volatile bị thay đổi trong {where}: {tokens}"),
    ("lock acquisition order in {where} changed: {old} became {new}",
     "thứ tự lấy lock trong {where} bị thay đổi: {old} thành {new}"),
    ("synchronisation member changed in {where}", "thành viên đồng bộ hoá bị thay đổi trong {where}"),
    ("exception specification of {where} changed ({old} -> {new})",
     "đặc tả exception của {where} bị thay đổi ({old} -> {new})"),
    ("exception specification of {where} changed", "đặc tả exception của {where} bị thay đổi"),
    ("exception flow changed in {where}: {tokens}", "luồng exception bị thay đổi trong {where}: {tokens}"),
    ("lock removed in {where}: `{code}`", "lock bị xoá trong {where}: `{code}`"),
    ("lock added in {where}: `{code}`", "lock được thêm trong {where}: `{code}`"),
    ("control flow / computation changed in {where}: {tokens}",
     "luồng điều khiển / phép tính bị thay đổi trong {where}: {tokens}"),
    ("behaviour of `{name}` ({loc}) {t_kind}", "hành vi của `{name}` ({loc}) {t_kind}"),
    ("condition removed in {where}: {conditions}", "điều kiện bị xoá trong {where}: {conditions}"),

    # ---- rules.py: hints --------------------------------------------------------------------------
    ("Run the changed test and confirm it fails without the product change (it really covers it)",
     "Chạy test đã thay đổi và xác nhận nó fail khi không có thay đổi của sản phẩm (nó thật sự bao phủ thay đổi)"),
    ("Log text/format still matches what tests, monitoring or log parsers expect",
     "Nội dung/định dạng log vẫn khớp với những gì test, hệ thống giám sát hoặc bộ phân tích log mong đợi"),
    ("No side effects or expensive calls inside the log arguments; log level filtering still works",
     "Không có side effect hay lời gọi tốn kém trong các đối số log; việc lọc theo log level vẫn hoạt động"),
    ("Exercise every branch whose condition changed (true and false paths)",
     "Chạy qua mọi nhánh có điều kiện bị thay đổi (cả nhánh true và false)"),
    ("Boundary values around changed comparisons and loop limits (min, max, off-by-one)",
     "Giá trị biên quanh các phép so sánh và giới hạn vòng lặp đã thay đổi (min, max, lệch một)"),
    ("Error / early-return paths and default switch case",
     "Các đường đi lỗi / return sớm và case default của switch"),
    ("Rebuild every target that includes the header (no stale objects / prebuilt libs)",
     "Build lại mọi target include header này (không còn object cũ / thư viện build sẵn)"),
    ("Callers compiled against the old header still link and behave",
     "Các caller được biên dịch với header cũ vẫn link được và hoạt động đúng"),
    ("sizeof / alignment / field offsets used by serialization, IPC or memcpy",
     "sizeof / alignment / offset của trường được dùng bởi serialization, IPC hoặc memcpy"),
    ("Aggregate / designated initialisation and default member values",
     "Khởi tạo aggregate / designated và giá trị mặc định của thành viên"),
    ("Copy / move / comparison operators still cover all members",
     "Các toán tử copy / move / so sánh vẫn bao phủ tất cả thành viên"),
    ("Virtual dispatch through base pointers (vtable change) in all derived classes",
     "Virtual dispatch qua pointer kiểu cơ sở (vtable thay đổi) trong mọi class dẫn xuất"),
    ("All call sites pass the new parameters correctly (implicit conversions, default args)",
     "Mọi nơi gọi truyền đúng các tham số mới (chuyển đổi ngầm định, đối số mặc định)"),
    ("Overload resolution does not silently pick a different overload",
     "Việc phân giải overload không âm thầm chọn một overload khác"),
    ("Function pointers / callbacks / mocks bound to the old signature",
     "Function pointer / callback / mock gắn với chữ ký cũ"),
    ("Every translation unit inlining the old body is rebuilt (ODR, mixed old/new objects)",
     "Mọi translation unit đã inline thân cũ đều được build lại (ODR, lẫn object cũ/mới)"),
    ("Null pointer input and allocation failure", "Đầu vào là null pointer và cấp phát bộ nhớ thất bại"),
    ("No double delete / leak on every exit path (including early return and exceptions)",
     "Không double delete / leak trên mọi đường thoát (kể cả return sớm và exception)"),
    ("Object still alive when accessed asynchronously (callbacks, timers, other threads)",
     "Đối tượng vẫn còn sống khi được truy cập bất đồng bộ (callback, timer, thread khác)"),
    ("Referenced object outlives the reference (no dangling reference to temporaries/locals)",
     "Đối tượng được tham chiếu sống lâu hơn reference (không có reference treo tới đối tượng tạm/biến cục bộ)"),
    ("Aliasing: same object passed for two reference parameters",
     "Aliasing: cùng một đối tượng được truyền cho hai tham số reference"),
    ("No use of an object after it was moved from", "Không dùng một đối tượng sau khi nó đã bị move"),
    ("Self-move / moved-from state is valid and destructible",
     "Self-move / trạng thái sau khi bị move hợp lệ và hủy được"),
    ("Concurrent calls from two or more threads (data race on shared state)",
     "Gọi đồng thời từ hai thread trở lên (data race trên trạng thái dùng chung)"),
    ("Re-entrancy: callback invoked while the lock is held (self-deadlock)",
     "Re-entrancy: callback được gọi khi đang giữ lock (tự deadlock)"),
    ("Lock released on every exit path, including exceptions",
     "Lock được nhả trên mọi đường thoát, kể cả khi có exception"),
    ("Concurrent read-modify-write sequences are not split into separate atomic ops",
     "Các chuỗi đọc-sửa-ghi đồng thời không bị tách thành các thao tác atomic riêng lẻ"),
    ("Memory ordering between the atomic and the data it guards",
     "Thứ tự bộ nhớ (memory ordering) giữa biến atomic và dữ liệu mà nó bảo vệ"),
    ("Two threads acquiring the same locks in opposite order (deadlock)",
     "Hai thread lấy cùng các lock theo thứ tự ngược nhau (deadlock)"),
    ("Lock hierarchy documented/observed by every caller",
     "Thứ bậc lock được mọi caller ghi nhận/tuân thủ"),
    ("A throw escaping a noexcept function calls std::terminate",
     "Một throw thoát ra khỏi hàm noexcept sẽ gọi std::terminate"),
    ("Containers (std::vector reallocation) choose copy vs move based on noexcept",
     "Các container (cấp phát lại của std::vector) chọn copy hay move dựa trên noexcept"),
    ("Every caller handles (or deliberately propagates) the new exception",
     "Mọi caller đều xử lý (hoặc chủ ý lan truyền) exception mới"),
    ("State stays consistent when an exception is thrown midway (strong/basic guarantee)",
     "Trạng thái vẫn nhất quán khi exception được ném giữa chừng (strong/basic guarantee)"),
    ("Exceptions crossing C / thread / callback boundaries",
     "Exception vượt qua ranh giới C / thread / callback"),
    ("Build and run with the macro defined and undefined",
     "Build và chạy cả khi macro được định nghĩa và không được định nghĩa"),
    ("All #if/#else branches compile on every configuration/platform",
     "Mọi nhánh #if/#else đều biên dịch được trên mọi cấu hình/nền tảng"),
    ("Behaviour in both Debug and Release (asserts compiled out under NDEBUG)",
     "Hành vi ở cả Debug và Release (assert bị loại bỏ khi có NDEBUG)"),
    ("Clean configure + build of every affected target",
     "Configure + build sạch cho mọi target bị ảnh hưởng"),
    ("Link order / new or removed dependencies / compile definitions",
     "Thứ tự link / dependency được thêm hoặc bị xoá / compile definition"),
    ("Every implementation of `{name}` (also outside this repo, e.g. mocks, plugins, downstream projects) must now "
     "override {names} or it fails to compile",
     "Mọi bản hiện thực của `{name}` (kể cả ngoài repo này, ví dụ mock, plugin, dự án downstream) giờ phải override "
     "{names}, nếu không sẽ không biên dịch được"),
    ("Objects created by old binaries / plugins used with the new vtable layout",
     "Đối tượng được tạo bởi binary / plugin cũ được dùng với layout vtable mới"),
    ("Every switch over the enum handles the new/removed enumerators",
     "Mọi switch trên enum này xử lý các giá trị enum mới/bị xoá"),
    ("Persisted / transmitted numeric values stay compatible",
     "Các giá trị số được lưu trữ / truyền đi vẫn tương thích"),
    # boundary_hints
    ("Boundary: `{expr}` with {var} = {values}", "Biên: `{expr}` với {var} = {values}"),
    ("Previous boundary: `{expr}` with {var} = {values}", "Biên trước đây: `{expr}` với {var} = {values}"),
    ("Boundary: `{expr}` just below, at and just above {lit}",
     "Biên: `{expr}` ngay dưới, bằng và ngay trên {lit}"),
    ("Previous boundary: `{expr}` just below, at and just above {lit}",
     "Biên trước đây: `{expr}` ngay dưới, bằng và ngay trên {lit}"),

    # ---- environment.py: why a case needs the target ----------------------------------------------
    ("concurrency: interleavings and timing are only observable when running ({loc})",
     "đồng thời: thứ tự xen kẽ và timing chỉ quan sát được khi chạy ({loc})"),
    ("memory lifetime: use-after-free / leaks / dangling references appear at run time ({loc})",
     "vòng đời bộ nhớ: use-after-free / leak / reference treo chỉ xuất hiện khi chạy ({loc})"),
    ("data layout: sizeof / alignment / padding depend on the target compiler and ABI ({loc})",
     "layout dữ liệu: sizeof / alignment / padding phụ thuộc vào compiler và ABI của target ({loc})"),
    ("build configuration: behaviour depends on the macros / options of the target build ({loc})",
     "cấu hình build: hành vi phụ thuộc vào các macro / option của bản build cho target ({loc})"),
    ("runtime routing ({category}): {t_reason}", "phụ thuộc chỉ xác định lúc chạy ({category}): {t_reason}"),
    ("hardware access", "truy cập phần cứng"),
    ("interrupt", "interrupt"),
    ("timing", "timing"),
    ("RTOS / threads", "RTOS / thread"),
    ("bus / network I/O", "I/O bus / mạng"),
    ("memory layout / byte order", "layout bộ nhớ / thứ tự byte"),
    ("changed code — hardware access: `{match}` at {loc}", "code đã thay đổi — truy cập phần cứng: `{match}` tại {loc}"),
    ("changed code — interrupt: `{match}` at {loc}", "code đã thay đổi — interrupt: `{match}` tại {loc}"),
    ("changed code — timing: `{match}` at {loc}", "code đã thay đổi — timing: `{match}` tại {loc}"),
    ("changed code — RTOS / threads: `{match}` at {loc}", "code đã thay đổi — RTOS / thread: `{match}` tại {loc}"),
    ("changed code — bus / network I/O: `{match}` at {loc}", "code đã thay đổi — I/O bus / mạng: `{match}` tại {loc}"),
    ("changed code — memory layout / byte order: `{match}` at {loc}",
     "code đã thay đổi — layout bộ nhớ / thứ tự byte: `{match}` tại {loc}"),
    ("changed code — {category}: `{match}` at {loc}", "code đã thay đổi — {category}: `{match}` tại {loc}"),
    ("hardware access: `{match}` at {loc}", "truy cập phần cứng: `{match}` tại {loc}"),
    ("interrupt: `{match}` at {loc}", "interrupt: `{match}` tại {loc}"),
    ("timing: `{match}` at {loc}", "timing: `{match}` tại {loc}"),
    ("RTOS / threads: `{match}` at {loc}", "RTOS / thread: `{match}` tại {loc}"),
    ("bus / network I/O: `{match}` at {loc}", "I/O bus / mạng: `{match}` tại {loc}"),
    ("memory layout / byte order: `{match}` at {loc}", "layout bộ nhớ / thứ tự byte: `{match}` tại {loc}"),

    # ---- external.py: third-party API boundaries (spec 005) ---------------------------------------
    ("`{api}` returns `{type}`: check `{caller}` handles nullptr and does not keep the pointer beyond the owner's "
     "lifetime",
     "`{api}` trả về `{type}`: kiểm tra `{caller}` xử lý nullptr và không giữ pointer lâu hơn vòng đời của đối tượng "
     "sở hữu"),
    ("`{api}` takes callback `{param}`: check it may run later, on another thread or re-entrantly, and that state it "
     "captures from `{caller}` is still alive",
     "`{api}` nhận callback `{param}`: kiểm tra trường hợp nó chạy muộn hơn, trên thread khác hoặc re-entrant, và "
     "trạng thái nó capture từ `{caller}` vẫn còn sống"),
    ("`{api}` returns `{type}`: make it return nullptr and check `{caller}` does not dereference it; check who "
     "owns/frees the returned object",
     "`{api}` trả về `{type}`: cho nó trả về nullptr và kiểm tra `{caller}` không dereference nó; kiểm tra ai sở "
     "hữu/giải phóng đối tượng được trả về"),
    ("the `{type}` result of `{api}` is ignored at line {line}: make the call fail and check the failure is not lost "
     "in `{caller}`",
     "kết quả `{type}` của `{api}` bị bỏ qua tại dòng {line}: cho lời gọi thất bại và kiểm tra lỗi không bị mất "
     "trong `{caller}`"),
    ("make `{api}` return its failure / sentinel `{type}` value and check the error path of `{caller}`",
     "cho `{api}` trả về giá trị lỗi / sentinel `{type}` và kiểm tra đường đi lỗi của `{caller}`"),
    ("`{api}` writes through `{param}`: check the value `{caller}` uses when the call fails or returns early "
     "(out-parameter left unset)",
     "`{api}` ghi qua `{param}`: kiểm tra giá trị mà `{caller}` dùng khi lời gọi thất bại hoặc return sớm "
     "(out-parameter chưa được gán)"),
    ("`{api}`(`{buf}`, `{len}`): boundary lengths 0, 1, exact capacity and capacity + 1",
     "`{api}`(`{buf}`, `{len}`): các độ dài biên 0, 1, đúng bằng capacity và capacity + 1"),
    ("`{api}` has no checkable contract in its declaration: replace it with a stub that fails, blocks or returns "
     "unusual data and check `{caller}`",
     "`{api}` không có contract kiểm tra được trong khai báo: thay nó bằng một stub thất bại, bị block hoặc trả về "
     "dữ liệu bất thường và kiểm tra `{caller}`"),
    ("{names} and {n} more are not noexcept: make each throw in turn and check `{caller}` leaves no partial state, "
     "held lock or leaked resource",
     "{names} và {n} hàm khác không phải noexcept: lần lượt cho từng hàm throw và kiểm tra `{caller}` không để lại "
     "trạng thái dở dang, lock đang giữ hay tài nguyên bị leak"),
    ("{names} are not noexcept: make each throw in turn and check `{caller}` leaves no partial state, held lock or "
     "leaked resource",
     "{names} không phải noexcept: lần lượt cho từng hàm throw và kiểm tra `{caller}` không để lại trạng thái dở "
     "dang, lock đang giữ hay tài nguyên bị leak"),
    ("{name} is not noexcept: make each throw in turn and check `{caller}` leaves no partial state, held lock or "
     "leaked resource",
     "{name} không phải noexcept: cho nó throw và kiểm tra `{caller}` không để lại trạng thái dở dang, lock đang giữ "
     "hay tài nguyên bị leak"),
    ("Contract: {api}: {hint}", "Contract: {api}: {hint}"),
    ("`{caller}` now calls third-party code outside the repository: {calls} and {n} more",
     "`{caller}` giờ gọi code bên thứ ba nằm ngoài repository: {calls} và {n} lời gọi khác"),
    ("`{caller}` now calls third-party code outside the repository: {calls}",
     "`{caller}` giờ gọi code bên thứ ba nằm ngoài repository: {calls}"),

    # ---- uncertainty.py: flag reasons -------------------------------------------------------------
    ("template `{name}` has no visible instantiation or use in the indexed translation units; its behaviour for "
     "concrete type arguments cannot be traced statically",
     "template `{name}` không có instantiation hay nơi dùng nào thấy được trong các translation unit đã index; hành "
     "vi của nó với các đối số kiểu cụ thể không truy vết tĩnh được"),
    ("virtual method `{name}` has no statically resolvable caller (neither it nor the methods it overrides are called "
     "directly); it is presumably reached through an interface pointer injected at runtime (DI / factory / "
     "configuration)",
     "phương thức ảo `{name}` không có caller nào phân giải tĩnh được (cả nó lẫn các phương thức nó override đều "
     "không được gọi trực tiếp); có lẽ nó được gọi tới qua một interface pointer được inject lúc chạy (DI / factory "
     "/ config)"),
    ("`{name}` is used as a function pointer / callback ({loc}); the code that finally invokes it at runtime cannot be "
     "resolved statically",
     "`{name}` được dùng làm function pointer / callback ({loc}); code thực sự gọi nó lúc chạy không phân giải tĩnh "
     "được"),
    ("`{name}` loads or dispatches code dynamically ({tokens}); runtime targets are not in the static graph",
     "`{name}` nạp hoặc điều phối code động ({tokens}); các đích lúc chạy không có trong graph tĩnh"),
    ("change in {loc} is guarded by `{condition}`; the condition is undefined in every compile command, so this "
     "branch was never parsed (configurations in compile_commands.json: {configs})",
     "thay đổi trong {loc} được bao bởi `{condition}`; điều kiện này không được định nghĩa ở bất kỳ lệnh biên dịch "
     "nào, nên nhánh này chưa bao giờ được phân tích (các cấu hình trong compile_commands.json: {configs})"),
    ("change in {loc} is guarded by `{condition}`; the condition has the same value in every compile command, so the "
     "other branch was never parsed (configurations in compile_commands.json: {configs})",
     "thay đổi trong {loc} được bao bởi `{condition}`; điều kiện này có cùng giá trị trong mọi lệnh biên dịch, nên "
     "nhánh còn lại chưa bao giờ được phân tích (các cấu hình trong compile_commands.json: {configs})"),
    ("change in {loc} is guarded by `{condition}`; {names} is undefined in every compile command, so this branch was "
     "never parsed (configurations in compile_commands.json: {configs})",
     "thay đổi trong {loc} được bao bởi `{condition}`; {names} không được định nghĩa ở bất kỳ lệnh biên dịch nào, nên "
     "nhánh này chưa bao giờ được phân tích (các cấu hình trong compile_commands.json: {configs})"),
    ("change in {loc} is guarded by `{condition}`; {names} has the same value in every compile command, so the other "
     "branch was never parsed (configurations in compile_commands.json: {configs})",
     "thay đổi trong {loc} được bao bởi `{condition}`; {names} có cùng giá trị trong mọi lệnh biên dịch, nên nhánh "
     "còn lại chưa bao giờ được phân tích (các cấu hình trong compile_commands.json: {configs})"),
    ("`{name}` depends on {words} but compile_commands.json only contains the {configs} configuration",
     "`{name}` phụ thuộc vào {words} nhưng compile_commands.json chỉ chứa cấu hình {configs}"),
]

# merge_pattern_cases appends " Also (<pattern>): <description>" to a case description. A template ending in a
# placeholder or ")" would swallow that tail, so each such description also gets an explicit merged variant (its
# longer literal text is matched first).
ENTRIES += [(en + " Also ({pattern}): {t_more}", tr + " Ngoài ra ({pattern}): {t_more}") for en, tr in list(ENTRIES)
            if en.startswith(("Verify the {t_group}", "Re-verify the", "Re-run existing", "Recompile and", "Rebuild and",
                              "`{target}` has {n} more trigger"))]
