"""Self-contained interactive HTML report: impact flow graph + filterable case list.

No external scripts or fonts are loaded (works offline, nothing leaves the machine — Principle VI).
Inside the VS Code webview, file:line links open the editor via ``postMessage``.
"""
from __future__ import annotations

import json
from typing import Any

_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TC Coverage Report</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--fg:#1d1f21;--muted:#62666d;--line:#d9dbde;--accent:#3559e0;
--h0:#c0392b;--h0bg:#fde2e1;--h1:#b9770e;--h1bg:#fff1d6;--h2:#2e86c1;--h2bg:#e3effa;--tg:#5b6770;--tgbg:#eceff1;
--p1:#c0392b;--p2:#b9770e;--p3:#5b6770;--warn:#8e44ad}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15171a;--panel:#1d2024;--fg:#e6e6e6;
--muted:#9aa0a6;--line:#33373d;--accent:#7b9cff;--h0:#ff7b6e;--h0bg:#3a1f1d;--h1:#f5b041;--h1bg:#3a2e17;--h2:#6cb4ee;
--h2bg:#172a3a;--tg:#b0bec5;--tgbg:#263238;--p1:#ff7b6e;--p2:#f5b041;--p3:#9aa0a6;--warn:#c39bd3}}
:root[data-theme="dark"]{--bg:#15171a;--panel:#1d2024;--fg:#e6e6e6;--muted:#9aa0a6;--line:#33373d;--accent:#7b9cff;
--h0:#ff7b6e;--h0bg:#3a1f1d;--h1:#f5b041;--h1bg:#3a2e17;--h2:#6cb4ee;--h2bg:#172a3a;--tg:#b0bec5;--tgbg:#263238;
--p1:#ff7b6e;--p2:#f5b041;--p3:#9aa0a6;--warn:#c39bd3}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header,main{max-width:1280px;margin:0 auto;padding:16px}h1{font-size:20px;margin:0 0 4px}
h2{font-size:16px;margin:24px 0 8px}.muted{color:var(--muted)}code,.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:12px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px}
.tile b{display:block;font-size:22px}.tile span{color:var(--muted);font-size:12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}
#graphWrap{overflow:auto;max-height:70vh}svg text{fill:var(--fg);font-size:12px}
.node rect{stroke-width:1.5;rx:6}.node{cursor:pointer}.node.dim{opacity:.25}.edge{fill:none;stroke:var(--muted);stroke-width:1.2;opacity:.55}
.edge.hl{stroke:var(--accent);opacity:1;stroke-width:2}.edge.dim{opacity:.08}
.colhead{fill:var(--muted)!important;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.chip{border:1px solid var(--line);background:var(--panel);
color:var(--fg);border-radius:999px;padding:3px 10px;cursor:pointer;font-size:12.5px}.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
input[type=search]{padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg);min-width:240px;max-width:100%}
.case{border-top:1px solid var(--line);padding:10px 2px}.case:first-child{border-top:0}
.prio{display:inline-block;font-weight:700;font-size:11px;padding:1px 6px;border-radius:4px;color:#fff}
.P1{background:var(--p1)}.P2{background:var(--p2)}.P3{background:var(--p3)}
.grp{font-size:11.5px;border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-left:4px;color:var(--muted)}
.case ul{margin:4px 0 0 18px;padding:0}.case li{margin:1px 0}a.loc{color:var(--accent);text-decoration:none;cursor:pointer}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px;text-align:left;vertical-align:top}
.ai{margin-top:6px;padding:6px 8px;border-left:3px solid var(--accent);background:var(--bg)}
.aib{font-size:11.5px;font-weight:700;padding:1px 6px;border-radius:4px;border:1px solid var(--accent);color:var(--accent)}
.aib.weak{border-color:var(--muted);color:var(--muted)}.aib.needs_info{border-color:var(--warn);color:var(--warn)}
.flag{color:var(--warn);font-weight:600}.tw{overflow-x:auto}td code{word-break:break-all}.node.unc rect{stroke:var(--warn)!important;stroke-dasharray:4 3}#detail{margin-top:8px}.empty{padding:24px;text-align:center;color:var(--muted)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-bottom:6px}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-2px;margin-right:4px;border:1.5px solid}
@media (max-width:640px){header,main{padding:12px 16px}input[type=search]{min-width:0;width:100%}}
</style></head><body>
<header><h1>TC Coverage — change impact &amp; test cases</h1><div class="muted" id="sub"></div>
<div class="tiles" id="tiles"></div></header>
<main>
<section id="noimpact"></section>
<h2>Impact flow</h2>
<div class="panel"><div class="legend"><span><i class="sw" style="background:var(--h0bg);border-color:var(--h0)"></i>changed</span>
<span><i class="sw" style="background:var(--h1bg);border-color:var(--h1)"></i>direct (1 hop)</span>
<span><i class="sw" style="background:var(--h2bg);border-color:var(--h2)"></i>indirect</span>
<span><i class="sw" style="background:var(--tgbg);border-color:var(--tg)"></i>CMake target</span>
<span><i class="sw" style="border-color:var(--warn);border-style:dashed"></i>uncertain</span>
<span>click a node to filter the cases · hover to trace the path</span></div>
<div id="graphWrap"><svg id="graph" role="img" aria-label="impact graph"></svg></div><div id="detail" class="muted"></div></div>
<h2>Test cases to check</h2>
<div class="panel"><div class="chips" id="prioChips"></div><div class="chips" id="grpChips"></div>
<input type="search" id="q" placeholder="Filter by symbol, file, text…">
<select id="ord" title="List order" style="margin-left:8px;padding:5px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg)"><option value="rel">Order: relevance</option><option value="ai">Order: AI-triaged</option></select><span class="muted" id="count" style="margin-left:8px"></span>
<div id="cases"></div></div>
<section id="aiSec"></section><section id="testsSec"></section><section id="flagsSec"></section><section id="targetsSec"></section><section id="oosSec"></section><section id="notesSec"></section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
const R=JSON.parse(document.getElementById('data').textContent);
const vs=(typeof acquireVsCodeApi==='function')?acquireVsCodeApi():null;
const repo=R.change_input.target_repo_path;
const GL={logic:'Logic',abi_layout:'ABI / layout',ownership_lifetime:'Ownership / lifetime',thread_safety:'Thread safety',exception_safety:'Exception safety',build_config:'Build config'};
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function loc(f,l){const u='vscode://file/'+encodeURI((repo+'/'+f).replace(/\\/g,'/'))+':'+l;
 return `<a class="loc mono" data-f="${esc(f)}" data-l="${l}" href="${vs?'#':u}">${esc(f)}:${l}</a>`}
document.addEventListener('click',e=>{const a=e.target.closest('a.loc');if(a&&vs){e.preventDefault();vs.postMessage({type:'open',file:a.dataset.f,line:+a.dataset.l})}});
const C=R.test_case_candidates, by=p=>C.filter(c=>c.priority===p).length;
const llm=R.llm_degraded?'degraded':R.llm_enabled?'on':'off';
const ci=R.change_input;
document.getElementById('sub').textContent=`${ci.mode} · ${ci.commit_range||(ci.working_tree?'working tree':(ci.symbols_requested||[]).join(', '))} · ${repo}`;
const tiles=[[C.length,'test cases'],[by('P1'),'P1'],[by('P2'),'P2'],[by('P3'),'P3'],[R.uncertainty_flags.length,'uncertain'],
[(R.changed_symbols||[]).length,'changed symbols'],[(R.affected_targets||[]).length,'targets'],[R.cache_hit?'hit':'miss','cache'],[llm,'LLM']];
document.getElementById('tiles').innerHTML=tiles.map(t=>`<div class="tile"><b>${esc(t[0])}</b><span>${t[1]}</span></div>`).join('');
if(R.no_detected_impact)document.getElementById('noimpact').innerHTML='<div class="panel empty"><b>No detected impact.</b><br>The change touches no indexed symbol semantically (comments, whitespace, non-C++ files). This is a result, not a failure.</div>';
// ---------- graph ----------
const N=(R.impact_nodes||[]).slice(0,400);const key=s=>s.qualified_name+'|'+s.file_path+'|'+s.line;
const byKey={};N.forEach(n=>byKey[key(n.symbol)]=n);
const cols={};N.forEach(n=>{(cols[n.hop_distance]=cols[n.hop_distance]||[]).push(n)});
const hops=Object.keys(cols).map(Number).sort((a,b)=>a-b);
const tg=[...new Set(N.flatMap(n=>n.targets||[]))].sort();
const W=230,H=30,GX=90,GY=12,TOP=34;const pos={};
hops.forEach((h,ci)=>cols[h].forEach((n,i)=>pos[n.id]={x:16+ci*(W+GX),y:TOP+i*(H+GY),n}));
const tx=16+hops.length*(W+GX);tg.forEach((t,i)=>pos['T:'+t]={x:tx,y:TOP+i*(H+GY),t});
const maxRows=Math.max(1,...hops.map(h=>cols[h].length),tg.length);
const svg=document.getElementById('graph');const sw=tx+(tg.length?W:0)+16,sh=TOP+maxRows*(H+GY)+10;
svg.setAttribute('width',sw);svg.setAttribute('height',sh);svg.setAttribute('viewBox',`0 0 ${sw} ${sh}`);
let s='';const names=['changed','direct','indirect'];
hops.forEach((h,ci)=>s+=`<text class="colhead" x="${16+ci*(W+GX)}" y="18">${h===0?'Changed':h===1?'Direct (1 hop)':'Indirect ('+h+' hops)'}</text>`);
if(tg.length)s+=`<text class="colhead" x="${tx}" y="18">CMake targets</text>`;
const E=[];N.forEach(n=>(n.edges||[]).forEach(e=>{const t=byKey[key(e.to_symbol)];if(t&&pos[t.id]&&pos[n.id]&&t.id!==n.id)E.push({a:t.id,b:n.id,rel:e.relation,loc:e.source_location})}));
N.forEach(n=>(n.targets||[]).forEach(t=>E.push({a:n.id,b:'T:'+t,rel:'link_to_target'})));
const uniq={};E.forEach((e,i)=>{const k=e.a+'>'+e.b+'>'+e.rel;if(uniq[k])return;uniq[k]=1;const A=pos[e.a],B=pos[e.b];
 const x1=A.x+W,y1=A.y+H/2,x2=B.x,y2=B.y+H/2,dx=Math.max(30,(x2-x1)/2);
 const back=x2<=x1;const d=back?`M${A.x+W/2},${A.y+H} C${A.x+W/2},${A.y+H+40} ${B.x+W/2},${B.y+H+40} ${B.x+W/2},${B.y+H}`:`M${x1},${y1} C${x1+dx},${y1} ${x2-dx},${y2} ${x2},${y2}`;
 s+=`<path class="edge" data-a="${esc(e.a)}" data-b="${esc(e.b)}" d="${d}"><title>${esc(e.rel)}${e.loc?' @ '+esc(e.loc.file_path+':'+e.loc.line):''}</title></path>`});
const P1=id=>C.filter(c=>c.node_id===id&&c.priority==='P1').length;
const UNC=new Set(R.uncertainty_flags.filter(f=>f.related_symbol).map(f=>key(f.related_symbol)));
Object.entries(pos).forEach(([id,p])=>{const n=p.n;const h=n?Math.min(n.hop_distance,2):3;const col=['h0','h1','h2','tg'][h];
 const label=n?(n.test?'test '+n.test:n.symbol.qualified_name):p.t;const p1=n?P1(id):0;const max=p1?26:31;
 const short=label.length>max?'…'+label.slice(-(max-1)):label;
 s+=`<g class="node${n&&UNC.has(key(n.symbol))?' unc':''}" data-id="${esc(id)}" transform="translate(${p.x},${p.y})"><rect width="${W}" height="${H}" style="fill:var(--${col}bg);stroke:var(--${col})"></rect>`+
 `<text x="8" y="19">${esc(short)}</text>${p1?`<text x="${W-8}" y="19" text-anchor="end" style="fill:var(--p1);font-weight:700">${p1}●</text>`:''}`+
 `<title>${esc(label)}${n?'\n'+n.symbol.file_path+':'+n.symbol.line+'\nrisk: '+(n.risk_groups||[]).join(', '):''}</title></g>`});
svg.innerHTML=s||'';
if(!N.length)document.getElementById('graphWrap').innerHTML='<div class="empty">No impacted nodes.</div>';
function related(id){const up=new Set([id]),down=new Set([id]);let ch=true;
 while(ch){ch=false;E.forEach(e=>{if(down.has(e.a)&&!down.has(e.b)){down.add(e.b);ch=true}if(up.has(e.b)&&!up.has(e.a)){up.add(e.a);ch=true}})}
 return new Set([...up,...down])}
function hl(id){const r=id?related(id):null;svg.querySelectorAll('.node').forEach(g=>g.classList.toggle('dim',!!r&&!r.has(g.dataset.id)));
 svg.querySelectorAll('.edge').forEach(p=>{const on=r&&r.has(p.dataset.a)&&r.has(p.dataset.b);p.classList.toggle('hl',!!on);p.classList.toggle('dim',!!r&&!on)})}
let selNode=null;
svg.addEventListener('mouseover',e=>{const g=e.target.closest('.node');if(g)hl(g.dataset.id)});
svg.addEventListener('mouseout',e=>{if(!e.relatedTarget||!e.relatedTarget.closest||!e.relatedTarget.closest('.node'))hl(selNode)});
svg.addEventListener('click',e=>{const g=e.target.closest('.node');if(!g)return;const id=g.dataset.id;selNode=selNode===id?null:id;hl(selNode);
 const n=pos[id]&&pos[id].n;const d=document.getElementById('detail');
 if(selNode&&n){d.innerHTML=`<b>${esc(n.symbol.qualified_name)}</b> ${loc(n.symbol.file_path,n.symbol.line)} · hop ${n.hop_distance} · risk: ${esc((n.risk_groups||[]).join(', '))} · targets: ${esc((n.targets||[]).join(', ')||'-')}`+
 ((n.edges||[]).length?'<ul>'+n.edges.map(e=>`<li>${esc(e.relation)} → <code>${esc(e.to_symbol.qualified_name)}</code> at ${loc(e.source_location.file_path,e.source_location.line)}</li>`).join('')+'</ul>':'')+' <a class="loc" id="clr">clear filter</a>';
 document.getElementById('clr').onclick=()=>{selNode=null;hl(null);d.textContent='';render()}}else d.textContent='';render()});
// ---------- cases ----------
const st={p:new Set(['P1','P2','P3']),g:new Set(Object.keys(GL)),q:''};
function chips(el,vals,set,lab){el.innerHTML=vals.map(v=>`<button class="chip ${set.has(v)?'on':''}" data-v="${v}">${esc(lab(v))} (${C.filter(c=>c.priority===v||c.risk_group===v).length})</button>`).join('');
 el.onclick=e=>{const b=e.target.closest('.chip');if(!b)return;const v=b.dataset.v;set.has(v)?set.delete(v):set.add(v);b.classList.toggle('on');render()}}
chips(document.getElementById('prioChips'),['P1','P2','P3'],st.p,v=>v);
chips(document.getElementById('grpChips'),Object.keys(GL).filter(g=>C.some(c=>c.risk_group===g)),st.g,v=>GL[v]);
document.getElementById('q').oninput=e=>{st.q=e.target.value.toLowerCase();render()};
function evHtml(e){return e.qualified_name!==undefined?`<code>${esc(e.qualified_name)}</code> ${loc(e.file_path,e.line)}`:
 `<code>${esc(e.from_symbol.qualified_name)}</code> —${esc(e.relation)}→ <code>${esc(e.to_symbol.qualified_name)}</code> ${loc(e.source_location.file_path,e.source_location.line)}`}
const AIO={confirmed:0,needs_info:1,weak:3};const aiKey=c=>c.verification?AIO[c.verification.verdict]:2;
const ordEl=document.getElementById('ord');if(!C.some(c=>c.verification))ordEl.style.display='none';
ordEl.onchange=()=>render();
function render(){const list=C.filter(c=>st.p.has(c.priority)&&st.g.has(c.risk_group)&&(!selNode||c.node_id===selNode)&&
 (!st.q||JSON.stringify(c).toLowerCase().includes(st.q)));
 if(ordEl.value==='ai')list.sort((x,y)=>aiKey(x)-aiKey(y)); // stable: relevance order inside each verdict
 document.getElementById('count').textContent=`${list.length} / ${C.length}`;
 document.getElementById('cases').innerHTML=list.length?list.map(c=>`<div class="case"><span class="prio ${c.priority}">${c.priority}</span> <b class="mono">${c.id}</b><span class="grp">${GL[c.risk_group]}${c.sub_reason?' · '+esc(c.sub_reason):''}</span><span class="grp">hop ${c.hop_distance}</span>${c.bug_history?`<span class="grp" title="bug-fix commits touching this file in the last 12 months">${c.bug_history} recent fixes</span>`:''}
 <div>${esc(c.description)}</div><div class="muted">When: ${esc(c.activation_condition)}</div>
 <ul>${c.evidence.map(e=>`<li>${evHtml(e)}</li>`).join('')}</ul>
 ${(c.corner_cases||[]).length?`<div class="muted" style="margin-top:4px">Corner cases:</div><ul>${c.corner_cases.map(h=>`<li>${esc(h)}</li>`).join('')}</ul>`:''}
 <div class="muted">Targets: ${esc(c.related_cmake_targets.join(', '))}</div>${c.verification?`<div class="ai"><span class="aib ${c.verification.verdict}">AI · ${esc(c.verification.verdict)}${c.verification.recheck?' · re-check':''}</span> ${esc(c.verification.note)}${c.verification.extra_corner_cases.length?'<ul>'+c.verification.extra_corner_cases.map(h=>`<li>${esc(h)}</li>`).join('')+'</ul>':''}</div>`:''}</div>`).join(''):'<div class="empty">No cases match.</div>'}
render();
const AV=R.ai_verification;
if(AV)document.getElementById('aiSec').innerHTML=`<h2>AI verification <span class="muted" style="font-size:13px;font-weight:400">annotations only — no case is removed</span></h2><div class="panel"><div>${esc(AV.summary)}</div><div class="muted">verified cases: ${AV.verified_cases} · models: ${esc((AV.models||[]).join(', ')||'-')}</div>`+
 (AV.additional_checks.length?'<ul>'+AV.additional_checks.map(a=>`<li><b>${esc(a.title)}</b> — ${esc(a.why)} <span class="mono muted">${esc(a.evidence)}</span></li>`).join('')+'</ul>':'')+'</div>';
const XT=R.existing_tests||[];
if(XT.length)document.getElementById('testsSec').innerHTML=`<h2>Existing tests to re-run (${XT.length})</h2><div class="panel"><code>--gtest_filter=${esc(XT.map(t=>t.test).join(':'))}</code><ul>`+XT.map(t=>`<li><code>${esc(t.test)}</code> ${loc(t.file_path,t.line)} · hop ${t.hop_distance}</li>`).join('')+'</ul></div>';
const F=R.uncertainty_flags;
if(F.length)document.getElementById('flagsSec').innerHTML=`<h2>Uncertain — needs manual review (${F.length})</h2><div class="panel tw"><table><tr><th>Category</th><th>Symbol</th><th>Reason</th></tr>`+
 F.map(f=>`<tr><td class="flag">${esc(f.category)}</td><td>${f.related_symbol?`<code>${esc(f.related_symbol.qualified_name)}</code><br>${loc(f.related_symbol.file_path,f.related_symbol.line)}`:'-'}</td><td>${esc(f.reason)}</td></tr>`).join('')+'</table></div>';
const T=R.affected_targets||[];
if(T.length)document.getElementById('targetsSec').innerHTML='<h2>Build / test scope to rerun</h2><div class="panel">'+T.map(t=>`<code>${esc(t.name)}</code> <span class="muted">${esc(t.relation)}${t.via?' via '+esc(t.via):''}</span>`).join('<br>')+'</div>';
const O=R.out_of_scope||[];
if(O.length)document.getElementById('oosSec').innerHTML='<h2>Skipped (out of scope)</h2><div class="panel">'+O.map(o=>`<code>${esc(o.path)}</code> <span class="muted">${esc(o.reason)}</span>`).join('<br>')+'</div>';
const NO=R.run_notes||[];
if(NO.length)document.getElementById('notesSec').innerHTML='<h2>Run notes</h2><div class="panel">'+NO.map(n=>esc(n)).join('<br>')+'</div>';
})();
</script></body></html>
"""


def to_html(report: dict[str, Any]) -> str:
    data = json.dumps(report).replace("<", "\\u003c")
    return _TEMPLATE.replace("__DATA__", data)

