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
/* test results (spec 006) */
:root{--ok:#1e8449;--okbg:#e3f4ea;--bad:#c0392b;--badbg:#fde2e1;--nt:#5b6770;--ntbg:#eceff1;--no:#7d3c98;--nobg:#f1e4f6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ok:#58d68d;--okbg:#17321f;--bad:#ff7b6e;--badbg:#3a1f1d;
--nt:#b0bec5;--ntbg:#263238;--no:#c39bd3;--nobg:#2f2236}}
:root[data-theme="dark"]{--ok:#58d68d;--okbg:#17321f;--bad:#ff7b6e;--badbg:#3a1f1d;--nt:#b0bec5;--ntbg:#263238;--no:#c39bd3;--nobg:#2f2236}
.tr{margin-top:8px;border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:var(--bg)}
.vb{display:inline-block;font-size:11.5px;font-weight:700;padding:1px 7px;border-radius:4px;border:1px solid var(--line);color:var(--muted)}
.vb.pass{color:var(--ok);background:var(--okbg);border-color:var(--ok)}.vb.fail{color:var(--bad);background:var(--badbg);border-color:var(--bad)}
.vb.not_testable{color:var(--nt);background:var(--ntbg);border-color:var(--nt)}.vb.cannot_occur{color:var(--no);background:var(--nobg);border-color:var(--no)}
.vb.re{color:var(--warn);border-color:var(--warn)}
.btn{border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:6px;padding:3px 10px;cursor:pointer;font:inherit;font-size:12.5px}
.btn.pri{background:var(--accent);border-color:var(--accent);color:#fff}
.trf{display:grid;grid-template-columns:110px 1fr;gap:6px 10px;margin-top:8px;align-items:start}
.trf label{color:var(--muted);font-size:12.5px;padding-top:4px}
.trf input[type=text],.trf input[type=date],.trf textarea{width:100%;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg);font:inherit}
.trf textarea{min-height:56px;resize:vertical}.radios{display:flex;flex-wrap:wrap;gap:4px 14px}.radios label{color:var(--fg);padding:0}
.drop{border:1.5px dashed var(--line);border-radius:6px;padding:8px;text-align:center;color:var(--muted);font-size:12.5px}
.drop.over{border-color:var(--accent);color:var(--accent)}
.att{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:6px;font-size:12.5px}
.thumb{max-width:220px;max-height:140px;border:1px solid var(--line);border-radius:4px;display:block}
.err{color:var(--bad);font-size:12.5px;margin-top:4px}.banner{padding:8px 10px;border-radius:6px;margin-top:8px;font-weight:600}
.banner.inc{background:var(--h1bg);color:var(--h1)}.banner.done{background:var(--okbg);color:var(--ok)}.banner.big{background:var(--badbg);color:var(--bad)}
.rp{display:none}pre.log{white-space:pre-wrap;font-size:11px;border:1px solid var(--line);padding:6px;margin:4px 0}
@media print{.noprint,.chips,input[type=search],#ord,.btn,.drop,#count{display:none!important}
 body{background:#fff;color:#000}.panel,.tr{border-color:#999;background:#fff}.case{break-inside:avoid}.rp{display:block}
 .thumb{max-width:100%;max-height:none}}
</style></head><body>
<header><h1>TC Coverage — change impact &amp; test cases</h1><div class="muted" id="sub"></div>
<div class="tiles" id="tiles"></div><section id="trSec"></section></header>
<main>
<section id="noimpact"></section>
<h2 class="noprint">Impact flow</h2>
<div class="panel noprint"><div class="legend"><span><i class="sw" style="background:var(--h0bg);border-color:var(--h0)"></i>changed</span>
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
<section id="srcSec"></section><section id="orphSec"></section><section id="aiSec"></section><section id="testsSec"></section><section id="flagsSec"></section><section id="targetsSec"></section><section id="oosSec"></section><section id="notesSec"></section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script type="application/json" id="results">__RESULTS__</script>
<script>
(function(){
const PRISTINE='<!doctype html>\n'+document.documentElement.outerHTML; // before any rendering: the file as delivered
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
// ---------- test results (spec 006): verdict + evidence per case, saved inside this file ----------
const RB=document.getElementById('results');
const RS=JSON.parse(RB.textContent);RS.results=RS.results||{};RS.orphaned_results=RS.orphaned_results||{};RS.attachments=RS.attachments||{};
const WARN_MB=RS.attachment_warn_mb||(R.metrics&&R.metrics.attachment_warn_mb)||50;
const VL={pass:'Pass',fail:'Fail',not_testable:'Cannot be tested',cannot_occur:'Cannot occur'};
const VS_ORDER=['pass','fail','not_testable','cannot_occur'];
const byKeyCase={};C.forEach(c=>byKeyCase[c.key]=c);
const openSet=new Set();let dirty=false,printing=false;
const store={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};
const today=()=>{const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')};
function rec(k){return RS.results[k]||(RS.results[k]={verdict:null,comment:'',tester:'',date:'',defect_ref:'',attachments:[],needs_recheck:false,carried_from:null})}
function problems(r){if(!r||!r.verdict)return[];const o=[];
 if(!String(r.tester||'').trim())o.push('Tester is required.');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(r.date||''))o.push('Date is required.');
 if((r.verdict==='not_testable'||r.verdict==='cannot_occur')&&!String(r.comment||'').trim())o.push('A justification comment is required.');
 if(r.verdict==='fail'&&!(r.attachments||[]).some(a=>RS.attachments[a])&&!String(r.defect_ref||'').trim())o.push('A failed case needs an attachment or a defect reference.');
 return o}
function inFilter(k){const r=RS.results[k];if(RF.v==='all')return true;if(RF.v==='untested')return!r||!r.verdict;
 if(RF.v==='recheck')return!!(r&&r.verdict&&r.needs_recheck);if(RF.v==='invalid')return!!(r&&problems(r).length);return!!(r&&r.verdict===RF.v)}
const fmtB=n=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';
const attBytes=()=>Object.values(RS.attachments).reduce((a,x)=>a+(x.size||0),0);
function vbadge(r){if(!r||!r.verdict)return'<span class="vb">Not tested</span>';
 return `<span class="vb ${r.verdict}">${VL[r.verdict]}</span>${r.needs_recheck?' <span class="vb re" title="carried over from an earlier report; the code behind this case changed since">needs re-check</span>':''}${r.carried_from&&!r.needs_recheck?' <span class="vb" title="carried over from an earlier report">carried over</span>':''}`}
function b64ToBytes(b){const s=atob(b),u=new Uint8Array(s.length);for(let i=0;i<s.length;i++)u[i]=s.charCodeAt(i);return u}
function bytesToB64(u){let s='';for(let i=0;i<u.length;i+=0x8000)s+=String.fromCharCode.apply(null,u.subarray(i,i+0x8000));return btoa(s)}
const isText=a=>/^text\//.test(a.type||'')||/\.(log|txt|csv|json|xml|md|out|trace|ini|cfg|yaml|yml)$/i.test(a.name);
function attHtml(k,id,ro){const a=RS.attachments[id];if(!a)return'';
 const img=/^image\//.test(a.type||'')?`<img class="thumb" alt="${esc(a.name)}" src="data:${esc(a.type)};base64,${a.data}">`:'';
 let head='';if(ro&&isText(a)){try{head=new TextDecoder().decode(b64ToBytes(a.data)).split(/\r?\n/).slice(0,40).join('\n')}catch(e){}}
 return `<div class="att">${img}<span class="mono">${esc(a.name)}</span><span class="muted">${fmtB(a.size)} · sha256 ${esc(a.sha256.slice(0,12))}…</span>`+
  (ro?'':`<button class="btn" data-act="dl" data-id="${id}">Save file</button><button class="btn" data-act="rm" data-id="${id}">Remove</button>`)+
  `</div>${head?`<pre class="log">${esc(head)}</pre>`:''}`}
function trHtml(c){const r=RS.results[c.key];const pr=problems(r);
 const head=`<div>${vbadge(r)}${r&&r.verdict?` <span class="muted">${esc(r.tester||'')} · ${esc(r.date||'')}</span>`:''} <button class="btn noprint" data-act="tog">${openSet.has(c.key)?'Close':'Record result'}</button></div>`;
 const ro=`<div class="rp">${r&&r.verdict?`<div>Comment: ${esc(r.comment||'-')}</div>${r.defect_ref?`<div>Defect: ${esc(r.defect_ref)}</div>`:''}`+(r.attachments||[]).map(id=>attHtml(c.key,id,true)).join(''):''}</div>`;
 if(printing||!openSet.has(c.key))return head+(pr.length?`<div class="err">${pr.map(esc).join(' ')}</div>`:'')+ro;
 const R_=rec(c.key);
 return head+`<div class="trf"><label>Result</label><div class="radios">${VS_ORDER.map(v=>`<label><input type="radio" name="v-${esc(c.key)}" data-f="verdict" value="${v}"${R_.verdict===v?' checked':''}> ${VL[v]}</label>`).join('')}<button class="btn" data-act="clear">Clear</button></div>`+
 `<label>Comment</label><textarea data-f="comment" placeholder="What was tested, how, observed result; required for Cannot be tested / Cannot occur">${esc(R_.comment)}</textarea>`+
 `<label>Tester</label><input type="text" data-f="tester" value="${esc(R_.tester)}">`+
 `<label>Date</label><input type="date" data-f="date" value="${esc(R_.date)}">`+
 `<label>Defect ref.</label><input type="text" data-f="defect_ref" value="${esc(R_.defect_ref)}" placeholder="e.g. JIRA-1234">`+
 `<label>Evidence</label><div><div class="drop" data-act="drop">Drop screenshots / logs here or <input type="file" multiple data-act="file"></div>${(R_.attachments||[]).map(id=>attHtml(c.key,id,false)).join('')}</div></div>`+
 `<div class="err" data-err>${pr.map(esc).join(' ')}</div>`}
function touch(k){const r=rec(k),c=byKeyCase[k];r.updated_at=new Date().toISOString();if(c){r.fingerprint=c.code_fingerprint;r.description=c.description}dirty=true;summaryBar()}
function refreshTr(k){const el=document.querySelector(`.tr[data-k="${CSS.escape(k)}"]`);if(el)el.innerHTML=trHtml(byKeyCase[k])}
async function sha256hex(buf){if(window.crypto&&crypto.subtle){const h=await crypto.subtle.digest('SHA-256',buf);return[...new Uint8Array(h)].map(b=>b.toString(16).padStart(2,'0')).join('')}return sha256js(new Uint8Array(buf))}
function sha256js(m){const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
 const H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];const l=m.length,n=((l+9+63)>>6)<<6,b=new Uint8Array(n);b.set(m);b[l]=0x80;
 const dv=new DataView(b.buffer);dv.setUint32(n-4,(l*8)>>>0);dv.setUint32(n-8,Math.floor(l/0x20000000));const w=new Uint32Array(64),r=(x,s)=>(x>>>s)|(x<<(32-s));
 for(let o=0;o<n;o+=64){for(let i=0;i<16;i++)w[i]=dv.getUint32(o+i*4);for(let i=16;i<64;i++){const a=w[i-15],c=w[i-2];w[i]=(w[i-16]+(r(a,7)^r(a,18)^(a>>>3))+w[i-7]+(r(c,17)^r(c,19)^(c>>>10)))>>>0}
  let[a,bb,c,d,e,f,g,h]=H;for(let i=0;i<64;i++){const t1=(h+(r(e,6)^r(e,11)^r(e,25))+((e&f)^(~e&g))+K[i]+w[i])>>>0,t2=((r(a,2)^r(a,13)^r(a,22))+((a&bb)^(a&c)^(bb&c)))>>>0;h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=bb;bb=a;a=(t1+t2)>>>0}
  H[0]=(H[0]+a)>>>0;H[1]=(H[1]+bb)>>>0;H[2]=(H[2]+c)>>>0;H[3]=(H[3]+d)>>>0;H[4]=(H[4]+e)>>>0;H[5]=(H[5]+f)>>>0;H[6]=(H[6]+g)>>>0;H[7]=(H[7]+h)>>>0}
 return H.map(x=>x.toString(16).padStart(8,'0')).join('')}
async function addFiles(k,files){const r=rec(k);for(const f of files){const buf=await f.arrayBuffer();const sha=await sha256hex(buf);const id=sha.slice(0,16);
 if(!RS.attachments[id])RS.attachments[id]={name:f.name,type:f.type||'application/octet-stream',size:f.size,sha256:sha,data:bytesToB64(new Uint8Array(buf)),added_at:new Date().toISOString()};
 if(!r.attachments.includes(id))r.attachments.push(id)}touch(k);refreshTr(k)}
function download(name,mime,b64){if(vs){vs.postMessage({type:'saveFile',name,data:b64});return}
 const url=URL.createObjectURL(new Blob([b64ToBytes(b64)],{type:mime}));const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000)}
function gcAttachments(){const used=new Set();[RS.results,RS.orphaned_results].forEach(m=>Object.values(m).forEach(r=>(r.attachments||[]).forEach(a=>used.add(a))));
 Object.keys(RS.attachments).forEach(id=>{if(!used.has(id))delete RS.attachments[id]})}
function saveReport(){gcAttachments();Object.keys(RS.results).forEach(k=>{const r=RS.results[k];if(!r.verdict&&!r.comment&&!(r.attachments||[]).length&&!r.defect_ref)delete RS.results[k]});
 RS.saved_at=new Date().toISOString();
 const mk='<script type="application/json" id="results">',i=PRISTINE.indexOf(mk),j=PRISTINE.indexOf('</'+'script>',i);
 const html=PRISTINE.slice(0,i+mk.length)+JSON.stringify(RS).replace(/</g,'\\u003c')+PRISTINE.slice(j);
 const d=new Date(),stamp=d.getFullYear()+String(d.getMonth()+1).padStart(2,'0')+String(d.getDate()).padStart(2,'0')+'-'+String(d.getHours()).padStart(2,'0')+String(d.getMinutes()).padStart(2,'0');
 const name=`report-${String(R.commit_hash||'change').slice(0,9)}-${stamp}.html`;
 if(vs){vs.postMessage({type:'saveReport',name,html});return} // dirty cleared when the extension confirms
 download(name,'text/html',bytesToB64(new TextEncoder().encode(html)));dirty=false;summaryBar()}
const RF={v:'all'};
function summaryBar(){const n={pass:0,fail:0,not_testable:0,cannot_occur:0,untested:0,recheck:0,invalid:0};
 C.forEach(c=>{const r=RS.results[c.key];if(!r||!r.verdict){n.untested++;return}n[r.verdict]++;if(r.needs_recheck)n.recheck++;if(problems(r).length)n.invalid++});
 const done=n.untested+n.recheck+n.invalid===0&&C.length>0,bytes=attBytes(),big=bytes>WARN_MB*1048576;
 const chip=(v,l,x)=>`<button class="chip ${RF.v===v?'on':''}" data-rf="${v}">${l} (${x})</button>`;
 document.getElementById('trSec').innerHTML=`<h2>Test results</h2><div class="panel"><div class="tiles" style="margin-top:0">`+
 [[n.pass,'pass'],[n.fail,'fail'],[n.not_testable,'cannot be tested'],[n.cannot_occur,'cannot occur'],[n.untested,'not tested'],[n.recheck,'needs re-check'],[n.invalid,'incomplete record'],[fmtB(bytes),'evidence']].map(t=>`<div class="tile"><b>${esc(t[0])}</b><span>${t[1]}</span></div>`).join('')+
 `</div><div class="banner ${done?'done':'inc'}">${done?'Complete: every case has a valid result.':`Incomplete: ${n.untested} not tested, ${n.recheck} need re-check, ${n.invalid} with missing fields.`}</div>`+
 (big?`<div class="banner big">Embedded evidence is ${fmtB(bytes)} (limit ${WARN_MB} MB): consider trimming long logs.</div>`:'')+
 `<div class="chips">${chip('all','All',C.length)}${chip('untested','Not tested',n.untested)}${VS_ORDER.map(v=>chip(v,VL[v],n[v])).join('')}${chip('recheck','Needs re-check',n.recheck)}${chip('invalid','Incomplete',n.invalid)}</div>`+
 `<button class="btn pri" data-act="save">Save report${dirty?' *':''}</button> <button class="btn" data-act="print">Print / PDF</button> <span class="muted">Saving writes a new single HTML file with all results and evidence inside.</span></div>`}
document.getElementById('trSec').addEventListener('click',e=>{const b=e.target.closest('[data-rf],[data-act]');if(!b)return;
 if(b.dataset.rf){RF.v=b.dataset.rf;summaryBar();render()}else if(b.dataset.act==='save')saveReport();else if(b.dataset.act==='print')window.print()});
const casesEl=document.getElementById('cases');
casesEl.addEventListener('click',e=>{const t=e.target.closest('[data-act]');const tr=e.target.closest('.tr');if(!t||!tr||t.tagName==='INPUT')return;const k=tr.dataset.k;
 if(t.dataset.act==='tog'){openSet.has(k)?openSet.delete(k):openSet.add(k);refreshTr(k)}
 else if(t.dataset.act==='clear'){const r=rec(k);r.verdict=null;r.needs_recheck=false;touch(k);refreshTr(k)}
 else if(t.dataset.act==='rm'){const r=rec(k);r.attachments=r.attachments.filter(a=>a!==t.dataset.id);touch(k);refreshTr(k)}
 else if(t.dataset.act==='dl'){const a=RS.attachments[t.dataset.id];if(a)download(a.name,a.type,a.data)}});
casesEl.addEventListener('change',e=>{const tr=e.target.closest('.tr');if(!tr)return;const k=tr.dataset.k,f=e.target.dataset.f;
 if(e.target.dataset.act==='file'){addFiles(k,[...e.target.files]);return}
 if(f==='verdict'){const r=rec(k);r.verdict=e.target.value;r.needs_recheck=false;if(!r.date)r.date=today();if(!r.tester)r.tester=store.get('tcadvisor.tester')||'';touch(k);refreshTr(k)}});
casesEl.addEventListener('input',e=>{const tr=e.target.closest('.tr');const f=e.target.dataset.f;if(!tr||!f||f==='verdict')return;const k=tr.dataset.k,r=rec(k);
 r[f]=e.target.value;if(f==='tester')store.set('tcadvisor.tester',e.target.value);touch(k);const er=tr.querySelector('[data-err]');if(er)er.textContent=problems(r).join(' ')});
casesEl.addEventListener('dragover',e=>{const d=e.target.closest('.drop');if(d){e.preventDefault();d.classList.add('over')}});
casesEl.addEventListener('dragleave',e=>{const d=e.target.closest('.drop');if(d)d.classList.remove('over')});
casesEl.addEventListener('drop',e=>{const d=e.target.closest('.drop');if(!d)return;e.preventDefault();d.classList.remove('over');addFiles(d.closest('.tr').dataset.k,[...e.dataTransfer.files])});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});
window.addEventListener('beforeprint',()=>{printing=true;render()});window.addEventListener('afterprint',()=>{printing=false;render()});
if(vs)window.addEventListener('message',e=>{const m=e.data||{};if(m.type==='saved'){dirty=false;summaryBar()}});
summaryBar();
const ORPH=Object.entries(RS.orphaned_results||{});
if(ORPH.length)document.getElementById('orphSec').innerHTML=`<h2>No longer reported (${ORPH.length})</h2><div class="panel"><div class="muted">Results recorded on cases that this analysis no longer produces. Kept for the record, read-only.</div>`+
 ORPH.map(([k,r])=>`<div class="case"><span class="mono">${esc(k)}</span> ${vbadge(r)} <span class="muted">${esc(r.tester||'')} · ${esc(r.date||'')}</span><div>${esc(r.last_description||r.description||'')}</div>${r.comment?`<div class="muted">${esc(r.comment)}</div>`:''}${(r.attachments||[]).map(id=>attHtml(k,id,true)).join('')}</div>`).join('')+'</div>';
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
function render(){const list=printing?C.slice():C.filter(c=>st.p.has(c.priority)&&st.g.has(c.risk_group)&&(!selNode||c.node_id===selNode)&&
 (!st.q||JSON.stringify(c).toLowerCase().includes(st.q))&&inFilter(c.key));
 if(ordEl.value==='ai')list.sort((x,y)=>aiKey(x)-aiKey(y)); // stable: relevance order inside each verdict
 document.getElementById('count').textContent=`${list.length} / ${C.length}`;
 document.getElementById('cases').innerHTML=list.length?list.map(c=>`<div class="case"><span class="prio ${c.priority}">${c.priority}</span> <b class="mono">${c.id}</b><span class="grp">${GL[c.risk_group]}${c.sub_reason?' · '+esc(c.sub_reason):''}</span><span class="grp">hop ${c.hop_distance}</span>${c.bug_history?`<span class="grp" title="bug-fix commits touching this file in the last 12 months">${c.bug_history} recent fixes</span>`:''}
 <div>${esc(c.description)}</div><div class="muted">When: ${esc(c.activation_condition)}</div>
 <ul>${c.evidence.map(e=>`<li>${evHtml(e)}</li>`).join('')}</ul>
 ${c.path?`<div class="muted">Path: ${c.path.map(x=>`<code>${esc(x.symbol.qualified_name)}</code> <span class="grp">${esc(x.role)}${x.checked?' · checked':''}</span> ${loc(x.symbol.file_path,x.line)}`).join(' → ')}</div>`:''}
 ${(c.corner_cases||[]).length?`<div class="muted" style="margin-top:4px">Corner cases:</div><ul>${c.corner_cases.map(h=>`<li>${esc(h)}</li>`).join('')}</ul>`:''}
 <div class="muted">Targets: ${esc(c.related_cmake_targets.join(', '))}</div>${c.verification?`<div class="ai"><span class="aib ${c.verification.verdict}">AI · ${esc(c.verification.verdict)}${c.verification.recheck?' · re-check':''}</span> ${esc(c.verification.note)}${c.verification.extra_corner_cases.length?'<ul>'+c.verification.extra_corner_cases.map(h=>`<li>${esc(h)}</li>`).join('')+'</ul>':''}</div>`:''}<div class="tr" data-k="${esc(c.key)}">${trHtml(c)}</div></div>`).join(''):'<div class="empty">No cases match.</div>'}
render();
const AV=R.ai_verification;
if(AV)document.getElementById('aiSec').innerHTML=`<h2>AI verification <span class="muted" style="font-size:13px;font-weight:400">annotations only — no case is removed</span></h2><div class="panel"><div>${esc(AV.summary)}</div><div class="muted">verified cases: ${AV.verified_cases} · models: ${esc((AV.models||[]).join(', ')||'-')}</div>`+
 (AV.additional_checks.length?'<ul>'+AV.additional_checks.map(a=>`<li><b>${esc(a.title)}</b> — ${esc(a.why)} <span class="mono muted">${esc(a.evidence)}</span></li>`).join('')+'</ul>':'')+'</div>';
const TS=R.trigger_sources||[];
if(TS.length)document.getElementById('srcSec').innerHTML=TS.map(t=>`<h2>Trigger sources of <code>${esc(t.target.qualified_name)}</code></h2><div class="panel tw"><div class="muted">Guard added in ${t.covered_by.map(c=>'<code>'+esc(c)+'</code>').join(', ')}: <code>${esc(t.guard.join('; '))}</code></div><table><tr><th>Source</th><th>Kind</th><th>Guard</th><th></th></tr>`+
 t.sources.map(x=>`<tr><td><code>${esc(x.symbol.qualified_name)}</code><br>${loc(x.symbol.file_path,x.call_line)}</td><td>${x.registered_at?'callback registered at '+loc(x.registered_at[0],x.registered_at[1]):'call'}</td><td>${esc(x.guard)}</td><td>${x.covered_by_change?'covered by this change':'<span class="flag">check — see cases</span>'}</td></tr>`).join('')+'</table></div>').join('');
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
    from tcadvisor.report.results import empty_block
    block = report.get("test_results") or empty_block(report, report.get("metrics", {}).get("attachment_warn_mb", 50))
    data = {k: v for k, v in report.items() if k != "test_results"}  # attachments live once, in the results block
    pre, rest = _TEMPLATE.split("__DATA__")
    mid, post = rest.split("__RESULTS__")
    return (pre + json.dumps(data).replace("<", "\\u003c") + mid + json.dumps(block).replace("<", "\\u003c")
            + post)

