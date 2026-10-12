"""Vietnamese chrome of the interactive HTML report (``report/html.py``).

``HTML`` is an ordered list of ``(english_fragment, vietnamese_fragment)`` pairs applied with ``str.replace`` to the
English template (every occurrence, in list order). Fragments carry enough surrounding quotes / tags to be unique and
never touch CSS, identifiers, JSON keys or the machine-read blocks (``#data``, ``#results``). ``html.py`` fails loudly
when an English fragment is no longer in the template, so a template edit cannot silently drop a translation.
Machine values shown as is (edge relations, uncertainty categories, change mode) stay in English; sub-reason tags
and AI verdicts are shown through labels translated in Python (``render.case_labels``).
"""
from __future__ import annotations

ENTRIES: list[tuple[str, str]] = []  # sentence catalog (none: the page chrome is in HTML below)

HTML: list[tuple[str, str]] = [
    # ---------- static page ----------
    ('<html lang="en">', '<html lang="vi">'),
    ('<title>TC Coverage Report</title>', '<title>Báo cáo TC Coverage</title>'),
    ('<h1>TC Coverage — change impact &amp; test cases</h1>',
     '<h1>TC Coverage — ảnh hưởng của thay đổi &amp; test case</h1>'),
    ('<h2 class="noprint">Impact flow</h2>', '<h2 class="noprint">Luồng ảnh hưởng (impact)</h2>'),
    ('</i>changed</span>', '</i>đã thay đổi</span>'),
    ('</i>direct (1 hop)</span>', '</i>trực tiếp (1 hop)</span>'),
    ('</i>indirect</span>', '</i>gián tiếp</span>'),
    ('</i>uncertain</span>', '</i>chưa chắc chắn</span>'),
    ('<span>click a node to filter the cases · hover to trace the path</span>',
     '<span>bấm vào một node để lọc test case · rê chuột để xem đường đi</span>'),
    ('aria-label="impact graph"', 'aria-label="graph ảnh hưởng"'),
    ('<h2 id="casesTitle">Test cases to check</h2>', '<h2 id="casesTitle">Test case cần kiểm tra</h2>'),
    ('placeholder="Filter by symbol, file, text…"', 'placeholder="Lọc theo symbol, file, nội dung…"'),
    ('title="List order"', 'title="Thứ tự danh sách"'),
    ('>Order: relevance</option>', '>Thứ tự: mức liên quan</option>'),
    ('>Order: AI-triaged</option>', '>Thứ tự: theo phân loại của AI</option>'),
    # ---------- labels ----------
    ("const GL={logic:'Logic',abi_layout:'ABI / layout',ownership_lifetime:'Ownership / lifetime',"
     "thread_safety:'Thread safety',exception_safety:'Exception safety',build_config:'Build config'};",
     "const GL={logic:'Logic',abi_layout:'ABI / layout',ownership_lifetime:'Sở hữu / vòng đời',"
     "thread_safety:'An toàn thread',exception_safety:'An toàn exception',build_config:'Cấu hình build'};"),
    ("const AL={test_on_target:'Test on target',review:'Review code',closed_by_review:'Closed by code review',"
     "not_needed:'No real test needed (AI)'};",
     "const AL={test_on_target:'Test trên target',review:'Review code',closed_by_review:'Đã đóng bằng review code',"
     "not_needed:'Không cần test thực tế (AI)'};"),
    ("'Cases closed by AI (no real test needed)'", "'Các case AI đã đóng (không cần test thực tế)'"),
    ("`${R.ai_closed} case(s) closed by AI are listed separately in report.ai-verified.html.`",
     "`${R.ai_closed} case đã được AI đóng, liệt kê riêng trong report.ai-verified.html.`"),
    ("const llm=R.llm_degraded?'degraded':R.llm_enabled?'on':'off';",
     "const llm=R.llm_degraded?'suy giảm':R.llm_enabled?'bật':'tắt';"),
    ("(ci.working_tree?'working tree':", "(ci.working_tree?'working tree (chưa commit)':"),
    ("const tiles=[[C.length,'test cases'],[nA('test_on_target'),'test on target'],[nA('review'),'review code'],"
     "[nA('closed_by_review')+nA('not_needed')+(R.ai_closed||0),'closed by AI'],[by('P1'),'P1'],[by('P2'),'P2'],[by('P3'),'P3'],"
     "[R.uncertainty_flags.length,'uncertain'],\n"
     "[(R.changed_symbols||[]).length,'changed symbols'],[(R.affected_targets||[]).length,'targets'],"
     "[R.cache_hit?'hit':'miss','cache'],[llm,'LLM']];",
     "const tiles=[[C.length,'test case'],[nA('test_on_target'),'test trên target'],[nA('review'),'review code'],"
     "[nA('closed_by_review')+nA('not_needed')+(R.ai_closed||0),'AI đã đóng'],[by('P1'),'P1'],[by('P2'),'P2'],[by('P3'),'P3'],"
     "[R.uncertainty_flags.length,'chưa chắc chắn'],\n"
     "[(R.changed_symbols||[]).length,'symbol đã thay đổi'],[(R.affected_targets||[]).length,'target'],"
     "[R.cache_hit?'hit':'miss','cache'],[llm,'LLM']];"),
    ("<b>No detected impact.</b><br>The change touches no indexed symbol semantically (comments, whitespace, "
     "non-C++ files). This is a result, not a failure.",
     "<b>Không phát hiện ảnh hưởng.</b><br>Về mặt ngữ nghĩa, thay đổi không chạm tới symbol nào đã được index "
     "(comment, khoảng trắng, file không phải C++). Đây là một kết quả, không phải lỗi."),
    # ---------- test results form ----------
    ("const VL={pass:'Pass',fail:'Fail',not_testable:'Cannot be tested',cannot_occur:'Cannot occur'};",
     "const VL={pass:'Đạt',fail:'Không đạt',not_testable:'Không thể test',cannot_occur:'Không thể xảy ra'};"),
    ("'Tester is required.'", "'Cần nhập người test.'"),
    ("'Date is required.'", "'Cần nhập ngày.'"),
    ("'A justification comment is required.'", "'Cần ghi chú giải thích lý do.'"),
    ("'A failed case needs an attachment or a defect reference.'",
     "'Case không đạt cần có file đính kèm hoặc mã lỗi (defect).'"),
    ('<span class="vb">Not tested</span>', '<span class="vb">Chưa test</span>'),
    ('title="carried over from an earlier report; the code behind this case changed since">needs re-check</span>',
     'title="chuyển từ báo cáo trước; code của case này đã thay đổi kể từ đó">cần kiểm tra lại</span>'),
    ('title="carried over from an earlier report">carried over</span>',
     'title="chuyển từ báo cáo trước">chuyển từ báo cáo trước</span>'),
    ('>Save file</button>', '>Lưu file</button>'),
    ('>Remove</button>', '>Xoá</button>'),
    ("'Close':'Record result'", "'Đóng':'Ghi kết quả'"),
    ('<div>Comment: ', '<div>Ghi chú: '),
    ('<div>Defect: ', '<div>Mã lỗi (defect): '),
    ('<label>Result</label>', '<label>Kết quả</label>'),
    ('>Clear</button>', '>Bỏ chọn</button>'),
    ('<label>Comment</label>', '<label>Ghi chú</label>'),
    ('placeholder="What was tested, how, observed result; required for Cannot be tested / Cannot occur"',
     'placeholder="Đã test gì, test thế nào, kết quả quan sát được; bắt buộc với Không thể test / Không thể xảy ra"'),
    ('<label>Tester</label>', '<label>Người test</label>'),
    ('<label>Date</label>', '<label>Ngày</label>'),
    ('<label>Defect ref.</label>', '<label>Mã lỗi (defect)</label>'),
    ('placeholder="e.g. JIRA-1234"', 'placeholder="vd. JIRA-1234"'),
    ('<label>Evidence</label>', '<label>Bằng chứng</label>'),
    ('>Drop screenshots / logs here or <input', '>Kéo thả ảnh chụp màn hình / log vào đây hoặc <input'),
    ('<h2>Test results</h2>', '<h2>Kết quả test</h2>'),
    ("[[n.pass,'pass'],[n.fail,'fail'],[n.not_testable,'cannot be tested'],[n.cannot_occur,'cannot occur'],"
     "[n.untested,'not tested'],[n.recheck,'needs re-check'],[n.invalid,'incomplete record'],[fmtB(bytes),'evidence']]",
     "[[n.pass,'đạt'],[n.fail,'không đạt'],[n.not_testable,'không thể test'],[n.cannot_occur,'không thể xảy ra'],"
     "[n.untested,'chưa test'],[n.recheck,'cần kiểm tra lại'],[n.invalid,'bản ghi thiếu thông tin'],"
     "[fmtB(bytes),'bằng chứng']]"),
    ("'Complete: every case has a valid result.'", "'Hoàn tất: mọi case đều có kết quả hợp lệ.'"),
    ("`Incomplete: ${n.untested} not tested, ${n.recheck} need re-check, ${n.invalid} with missing fields.`",
     "`Chưa hoàn tất: ${n.untested} chưa test, ${n.recheck} cần kiểm tra lại, ${n.invalid} thiếu thông tin.`"),
    ("Embedded evidence is ${fmtB(bytes)} (limit ${WARN_MB} MB): consider trimming long logs.",
     "Bằng chứng nhúng trong file là ${fmtB(bytes)} (giới hạn ${WARN_MB} MB): nên cắt bớt các log dài."),
    ("chip('all','All',C.length)", "chip('all','Tất cả',C.length)"),
    ("chip('untested','Not tested',n.untested)", "chip('untested','Chưa test',n.untested)"),
    ("chip('recheck','Needs re-check',n.recheck)", "chip('recheck','Cần kiểm tra lại',n.recheck)"),
    ("chip('invalid','Incomplete',n.invalid)", "chip('invalid','Thiếu thông tin',n.invalid)"),
    (">Save report${dirty?' *':''}</button>", ">Lưu báo cáo${dirty?' *':''}</button>"),
    ('>Print / PDF</button>', '>In / PDF</button>'),
    ('Saving writes a new single HTML file with all results and evidence inside.',
     'Khi lưu sẽ ghi ra một file HTML mới duy nhất chứa toàn bộ kết quả và bằng chứng.'),
    ('<h2>No longer reported (${ORPH.length})</h2>', '<h2>Không còn trong báo cáo (${ORPH.length})</h2>'),
    ('Results recorded on cases that this analysis no longer produces. Kept for the record, read-only.',
     'Kết quả đã ghi cho các case mà lần phân tích này không còn tạo ra. Giữ lại để lưu vết, chỉ đọc.'),
    # ---------- graph ----------
    ("h===0?'Changed':h===1?'Direct (1 hop)':'Indirect ('+h+' hops)'",
     "h===0?'Đã thay đổi':h===1?'Trực tiếp (1 hop)':'Gián tiếp ('+h+' hop)'"),
    ('>CMake targets</text>', '>Các CMake target</text>'),
    ("'\\nrisk: '+(n.risk_groups||[]).join(', ')", "'\\nrủi ro: '+(n.risk_groups||[]).map(g=>GL[g]||g).join(', ')"),
    ("'<div class=\"empty\">No impacted nodes.</div>'", "'<div class=\"empty\">Không có node nào bị ảnh hưởng.</div>'"),
    ("· risk: ${esc((n.risk_groups||[]).join(', '))} · targets: ",
     "· rủi ro: ${esc((n.risk_groups||[]).map(g=>GL[g]||g).join(', '))} · target: "),
    ("</code> at ${loc(e.source_location.file_path,e.source_location.line)}</li>",
     "</code> tại ${loc(e.source_location.file_path,e.source_location.line)}</li>"),
    ('id="clr">clear filter</a>', 'id="clr">bỏ lọc</a>'),
    # ---------- case list ----------
    ('title="bug-fix commits touching this file in the last 12 months">${c.bug_history} recent fixes</span>',
     'title="số commit sửa lỗi chạm vào file này trong 12 tháng qua">${c.bug_history} lần sửa lỗi gần đây</span>'),
    ('<div class="muted">When: ', '<div class="muted">Khi nào: '),
    ('<div class="muted">Path: ', '<div class="muted">Đường đi: '),
    ("x.checked?' · checked':''", "x.checked?' · đã kiểm tra':''"),
    ('>Corner cases:</div>', '>Corner case:</div>'),
    ('<div class="muted">Targets: ', '<div class="muted">Target: '),
    ('<div class="muted">Needs the target: ', '<div class="muted">Cần target vì: '),
    ('<div class="muted">Proof: ', '<div class="muted">Bằng chứng (proof): '),
    ("${c.verification.recheck?' · re-check':''}", "${c.verification.recheck?' · cần kiểm tra lại':''}"),
    ("'<div class=\"empty\">No cases match.</div>'", "'<div class=\"empty\">Không có case nào khớp.</div>'"),
    # ---------- sections ----------
    ('<h2>AI verification <span class="muted" style="font-size:13px;font-weight:400">cases closed by AI are in '
     'report.ai-verified.html, never deleted</span></h2>',
     '<h2>Kiểm tra bằng AI <span class="muted" style="font-size:13px;font-weight:400">case AI đã đóng nằm trong '
     'report.ai-verified.html, không bao giờ bị xoá</span></h2>'),
    ('verified cases: ${AV.verified_cases} · models: ', 'case đã kiểm tra: ${AV.verified_cases} · model: '),
    ('<h2>Trigger sources of <code>', '<h2>Nguồn kích hoạt của <code>'),
    ('<div class="muted">Guard added in ${', '<div class="muted">Điều kiện chặn (guard) được thêm trong ${'),
    ('<th>Source</th><th>Kind</th><th>Guard</th>', '<th>Nguồn</th><th>Loại</th><th>Điều kiện chặn (guard)</th>'),
    ("'callback registered at '+loc(x.registered_at[0],x.registered_at[1]):'call'",
     "'callback được đăng ký tại '+loc(x.registered_at[0],x.registered_at[1]):'lời gọi'"),
    ("'covered by this change':'<span class=\"flag\">check — see cases</span>'",
     "'đã được thay đổi này bao phủ':'<span class=\"flag\">cần kiểm tra — xem các case</span>'"),
    ('<h2>Where each changed function is triggered from</h2>', '<h2>Mỗi hàm bị thay đổi được kích hoạt từ đâu</h2>'),
    ('Exercise every source: a fix verified from one source only is the classic miss.',
     'Chạy qua mọi nguồn: bản sửa chỉ được kiểm tra từ một nguồn là kiểu bỏ sót kinh điển.'),
    ('<th>Changed function</th><th>Source (caller)</th><th>Entry points behind it</th>',
     '<th>Hàm bị thay đổi</th><th>Nguồn (caller)</th><th>Các điểm vào (entry point) phía sau</th>'),
    ("' · callback registered at '+loc(", "' · callback được đăng ký tại '+loc("),
    ('… ${t.total-t.sources.length} more</td>', '… còn ${t.total-t.sources.length} nguồn khác</td>'),
    ('<h2>Existing tests to re-run (${XT.length})</h2>', '<h2>Các test hiện có cần chạy lại (${XT.length})</h2>'),
    ('<h2>Test gaps (${TG.length})</h2>', '<h2>Chỗ thiếu test (${TG.length})</h2>'),
    ('<p>No existing test reaches these changed symbols: a new test is likely needed.</p>',
     '<p>Không test hiện có nào chạm tới các symbol bị thay đổi này: nhiều khả năng cần viết test mới.</p>'),
    ('<h2>Uncertain — needs manual review (${F.length})</h2>',
     '<h2>Chưa chắc chắn — cần review thủ công (${F.length})</h2>'),
    ('<th>Category</th><th>Symbol</th><th>Reason</th>', '<th>Loại</th><th>Symbol</th><th>Lý do</th>'),
    ("'<h2>Build / test scope to rerun</h2>", "'<h2>Phạm vi build / test cần chạy lại</h2>"),
    ("${t.via?' via '+esc(t.via):''}", "${t.via?' qua '+esc(t.via):''}"),
    ("'<h2>Skipped (out of scope)</h2>", "'<h2>Bỏ qua (ngoài phạm vi)</h2>"),
    ("'<h2>Run notes</h2>", "'<h2>Ghi chú lần chạy</h2>"),
    # spec 012: build-variant profile
    ('<h2 style="display:inline">Not built in the confirmed variants (',
     '<h2 style="display:inline">Không được build trong các biến thể đã xác nhận ('),
    ("These cases concern code that no selected variant compiles; they are listed here, not deleted.</div>",
     "Các case này nói về code mà không biến thể nào đã chọn biên dịch; chúng được liệt kê ở đây, không bị xóa.</div>"),
    ('<span class="muted">excluded:</span>', '<span class="muted">bị loại bởi:</span>'),
    ("`<li>changed <code>", "`<li>thay đổi <code>"),
]
