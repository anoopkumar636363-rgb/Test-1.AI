const API = '/api';
const $ = (id) => document.getElementById(id);

function escapeHtml(value){return String(value).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));}
function addMessage(role, html){const box=$('chat');const el=document.createElement('div');el.className=`message ${role}`;el.innerHTML=role==='bot'?`<b>BIS AI</b><p>${html}</p>`:`<p>${escapeHtml(html)}</p>`;box.appendChild(el);box.scrollTop=box.scrollHeight;return el;}
function useText(text){$('question').value=text;focusAssistant();}
function usePrompt(button){useText(button.textContent);}
function focusAssistant(){document.querySelector('#assistant').scrollIntoView({behavior:'smooth'});setTimeout(()=>$('question').focus(),400);}

async function health(){try{const r=await fetch(`${API}/health`);const d=await r.json();$('apiBadge').textContent=d.ai_configured?'● AI connected':'● API online · demo AI';}catch{$('apiBadge').textContent='● Offline demo';}}

$('askForm').addEventListener('submit',async(e)=>{e.preventDefault();const q=$('question').value.trim();if(!q)return;addMessage('user',q);$('question').value='';const btn=$('askBtn');btn.disabled=true;btn.textContent='Thinking…';const typing=addMessage('bot','Searching the knowledge base…');try{const r=await fetch(`${API}/ask`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});const d=await r.json();typing.remove();let answer=escapeHtml(d.answer).replace(/\n/g,'<br>');if(d.sources?.length){answer+=`<br><br><span class="source">${d.sources.length} knowledge-base result(s)</span>`;}addMessage('bot',answer);}catch{typing.remove();addMessage('bot','The backend is not reachable. Start FastAPI with <b>uvicorn backend.main:app --reload</b>.');}finally{btn.disabled=false;btn.textContent='Ask AI';}});

async function searchStandards(){const q=$('standardSearch').value.trim();const box=$('standardResults');box.innerHTML='<p class="muted">Searching…</p>';try{const r=await fetch(`${API}/standards${q?`?q=${encodeURIComponent(q)}`:''}`);const data=await r.json();box.innerHTML=data.length?data.map(x=>`<article class="result"><span class="id">${escapeHtml(x.id)}</span><h3>${escapeHtml(x.title)}</h3><p><b>${escapeHtml(x.product)}</b> · ${escapeHtml(x.category)}</p><p>${escapeHtml(x.summary)}</p><span class="source">${escapeHtml(x.source)}</span></article>`).join(''):'<p class="muted">No matching demo records. Try a broader product keyword.</p>';}catch{box.innerHTML='<p class="muted">Backend unavailable.</p>';}}
$('standardSearch').addEventListener('keydown',e=>{if(e.key==='Enter')searchStandards();});

$('verifyForm').addEventListener('submit',async(e)=>{e.preventDefault();const number=$('license').value.trim();const box=$('verifyResult');box.textContent='Checking…';try{const r=await fetch(`${API}/verify`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({license_number:number})});const d=await r.json();box.innerHTML=d.found?`<b>Demo record found</b><br>${escapeHtml(d.result.product)} · ${escapeHtml(d.result.status)}<br><small>${escapeHtml(d.result.note)}</small>`:`<b>No demo record found.</b><br>${escapeHtml(d.message)}`;}catch{box.textContent='Backend unavailable.';}});

$('standardSearch').value='electrical';
health();searchStandards();
