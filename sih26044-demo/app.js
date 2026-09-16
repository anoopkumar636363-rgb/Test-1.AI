const API = '/api';
const state = { skills: new Set(['python','git','html/css','problem solving']) };

const catalog = [
  ['Python','python'],['JavaScript','javascript'],['React','react'],['HTML/CSS','html/css'],['Git & GitHub','git'],['FastAPI','fastapi'],['SQL','sql'],['Communication','communication'],['Problem Solving','problem solving']
];

function esc(value){return String(value).replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));}
function renderSkills(){
  const box=document.querySelector('#skillPicker');
  box.innerHTML=catalog.map(([label,key])=>`<button class="skill ${state.skills.has(key)?'selected':''}" data-skill="${key}">${label}</button>`).join('');
  box.querySelectorAll('.skill').forEach(b=>b.onclick=()=>{const k=b.dataset.skill;state.skills.has(k)?state.skills.delete(k):state.skills.add(k);renderSkills();updateMatches();});
}
function scoreFor(role){const have=state.skills;const need=role.skills.map(x=>x.toLowerCase());return Math.round(need.filter(x=>have.has(x)).length/need.length*100)}
function renderMatches(items){
 const ranked=items.map(x=>({...x,match:scoreFor(x)})).sort((a,b)=>b.match-a.match);
 document.querySelector('#matches').innerHTML=ranked.map(x=>`<article class="opportunity"><div><div class="muted">${esc(x.type)} · ${esc(x.location)}</div><h3>${esc(x.title)}</h3><p>${esc(x.company)}</p><div class="chips">${x.skills.map(s=>`<span class="chip ${state.skills.has(s.toLowerCase())?'have':''}">${esc(s)}</span>`).join('')}</div></div><div class="match"><strong>${x.match}%</strong><span>match</span><button class="apply" data-title="${esc(x.title)}">View details</button></div></article>`).join('');
 document.querySelectorAll('.apply').forEach(b=>b.onclick=()=>openModal(b.dataset.title));
}
async function updateMatches(){
 try{const r=await fetch(`${API}/opportunities`);const items=await r.json();renderMatches(items);document.querySelector('#skillCount').textContent=state.skills.size;document.querySelector('#readiness').textContent=Math.min(98,Math.round(45+state.skills.size*6))+'%';}
 catch(e){document.querySelector('#apiStatus').textContent='Demo mode';}
}
function openModal(title){document.querySelector('#modalTitle').textContent=title;document.querySelector('#modal').classList.add('show');}
function closeModal(){document.querySelector('#modal').classList.remove('show');}

document.addEventListener('click',e=>{if(e.target.id==='closeModal'||e.target.id==='modal')closeModal();});
document.querySelector('#assessmentBtn').onclick=()=>document.querySelector('#skills').scrollIntoView({behavior:'smooth'});
document.querySelector('#portfolioBtn').onclick=()=>openModal('Digital Student Portfolio');
document.querySelector('#generateBtn').onclick=()=>{document.querySelector('#roadmap').innerHTML='<b>Your 30-day roadmap:</b> strengthen React → build one REST API project → practice SQL → publish a GitHub portfolio → apply to 5 matched opportunities.';};

document.querySelector('#industryForm').onsubmit=async e=>{e.preventDefault();const data={title:roleTitle.value,company:company.value,location:location.value||'Remote',skills:roleSkills.value.split(',').map(x=>x.trim()).filter(Boolean)};await fetch(`${API}/roles`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});e.target.reset();await updateMatches();alert('Industry opportunity published!');};

renderSkills();updateMatches();
