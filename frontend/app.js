const $ = (s) => document.querySelector(s);
let me=null, dictItems=[], selectedImage=null, lastMultimodal=null, analysisMode='multimodal';

async function api(url, opts={}){
  const isForm=opts.body instanceof FormData;
  const headers={...(isForm?{}:{'Content-Type':'application/json'}),...(opts.headers||{})};
  let r;
  try{
    r=await fetch(url,{...opts,headers,credentials:'same-origin'});
  }catch(err){
    console.error('API network error',url,err);
    throw new Error(`Tidak dapat terhubung ke server: ${err?.message||err}`);
  }
  const text=await r.text();
  let data={};
  try{data=text?JSON.parse(text):{}}catch{data={raw:text};}
  if(!r.ok){
    const detail=data.detail||data.message||data.error||(typeof data.raw==='string'?data.raw.slice(0,500):'');
    throw new Error(`[HTTP ${r.status}] ${detail||'Terjadi kesalahan pada server.'}`);
  }
  if(data.raw && !Object.keys(data).some(k=>k!=='raw')){
    throw new Error('Server mengirim respons yang tidak valid.');
  }
  return data;
}
function esc(v=''){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function fmt(v){return Number(v||0).toLocaleString('id-ID');}
function showPage(name){document.querySelectorAll('.page').forEach(x=>x.classList.add('hidden'));$('#page-'+name).classList.remove('hidden');document.querySelectorAll('.nav-btn[data-page]').forEach(x=>x.classList.toggle('active',x.dataset.page===name));$('#pageTitle').textContent={analisa:'Analisa Multimodal',dashboard:'Dashboard',riwayat:'Riwayat Kasus',kamus:'Kamus Diagnosa',evaluasi:'Evaluasi Model'}[name]||name;if(name==='dashboard')loadDashboard();if(name==='riwayat')searchHistory();if(name==='kamus')loadDictionary();if(name==='evaluasi')loadEvaluation();}
document.querySelectorAll('.nav-btn[data-page]').forEach(b=>b.addEventListener('click',()=>showPage(b.dataset.page)));

const MODE_CONFIG={
  multimodal:{
    title:'Multimodal',
    description:'Gabungkan anamnesa/pemeriksaan, foto mata, dan histori kasus untuk membentuk evidence board.',
    button:'✦ Analisa Multimodal',
    chip:'Mode multimodal',
    chipClass:'mode-chip-multi',
    emptyTitle:'Belum ada hasil multimodal',
    emptyDescription:'Isi evidence klinis dan upload foto, lalu klik Analisa Multimodal.'
  },
  photo:{
    title:'Foto saja',
    description:'Gunakan foto mata sebagai satu-satunya input analisa. Clinical retrieval akan dilewati bila teks klinis kosong.',
    button:'✦ Analisa Foto',
    chip:'Mode foto',
    chipClass:'mode-chip-photo',
    emptyTitle:'Belum ada hasil analisa foto',
    emptyDescription:'Upload foto, jalankan Quality Check bila perlu, lalu klik Analisa Foto.'
  },
  clinical:{
    title:'Klinis saja',
    description:'Gunakan anamnesa, riwayat, dan pemeriksaan untuk retrieval histori tanpa foto.',
    button:'Analisa Teks',
    chip:'Mode klinis',
    chipClass:'mode-chip-clinical',
    emptyTitle:'Belum ada hasil klinis',
    emptyDescription:'Isi anamnesa atau pemeriksaan, lalu klik Analisa Teks.'
  }
};
function setAnalysisMode(mode){
  analysisMode=MODE_CONFIG[mode]?mode:'multimodal';
  const cfg=MODE_CONFIG[analysisMode];
  document.querySelectorAll('.mode-btn').forEach(b=>b.classList.toggle('active',b.dataset.mode===analysisMode));
  $('#modeTitle').textContent=cfg.title;
  $('#modeDescription').textContent=cfg.description;
  $('#clinicalPanel').classList.toggle('hidden',analysisMode==='photo');
  $('#imagePanel').classList.toggle('hidden',analysisMode==='clinical');
  $('#analysisWorkspace').classList.toggle('photo-only',analysisMode==='photo');
  $('#analysisWorkspace').classList.toggle('clinical-only',analysisMode==='clinical');
  $('#multimodalBtn').textContent=cfg.button;
  $('#multimodalBtn').classList.toggle('hidden',analysisMode==='clinical');
  $('#fusionState').textContent=cfg.chip;
  $('#fusionState').className='chip '+cfg.chipClass;
  $('#emptyTitle').textContent=cfg.emptyTitle;
  $('#emptyDescription').textContent=cfg.emptyDescription;
  $('#evidenceBoardTitle').textContent=analysisMode==='multimodal'?'3 · Multimodal Evidence Board':analysisMode==='photo'?'3 · Visual Evidence Board':'3 · Clinical Evidence Board';
  $('#evidenceBoardDescription').textContent=analysisMode==='multimodal'?'Hasil dari beberapa sumber evidence ditampilkan terpisah agar dapat diaudit.':analysisMode==='photo'?'Temuan visual dan retrieval histori dari foto ditampilkan tanpa memaksakan evidence klinis.':'Ranking histori berdasarkan anamnesa dan pemeriksaan ditampilkan tanpa evidence foto.';
}
document.querySelectorAll('.mode-btn').forEach(b=>b.addEventListener('click',()=>setAnalysisMode(b.dataset.mode)));
setAnalysisMode('multimodal');


async function boot(){try{me=await api('/api/auth/me');enterApp()}catch{$('#loginView').classList.remove('hidden');$('#appView').classList.add('hidden')}}
function enterApp(){$('#loginView').classList.add('hidden');$('#appView').classList.remove('hidden');$('#userBadge').innerHTML=`<b>${esc(me.username)}</b><div>${esc(me.role)}</div>`;checkVision();}
$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();$('#loginError').textContent='';try{me=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:$('#username').value.trim(),password:$('#password').value})});enterApp()}catch(err){$('#loginError').textContent=err.message}});
$('#logoutBtn').addEventListener('click',async()=>{try{await api('/api/auth/logout',{method:'POST'})}catch{}location.reload()});
async function checkVision(){try{const h=await api('/health');$('#visionStatus').textContent=h.vision_enabled?'Vision: siap':'Vision: baseline'}catch{$('#visionStatus').textContent='Vision: cek'}}

function collectClinical(){return{age:$('#age').value?Number($('#age').value):null,sex:$('#sex').value,alergi:$('#alergi').value,anamnese:$('#anamnese').value,riwayat_sekarang:$('#riwayat').value,periksa:$('#periksa').value,top_n:5}}
function renderFeatures(f){$('#clinicalFeatureBox').classList.remove('hidden');const m=f.measurements||{};$('#clinicalFeatureBox').innerHTML=`<div class="section-label">EXTRACTED CLINICAL FEATURES</div><div class="feature-tags"><span>Laterality <b>${esc(f.laterality||'unknown')}</b></span>${Object.entries(m).map(([k,v])=>`<span>${esc(k)} <b>${esc(v)}</b></span>`).join('')}${(f.signs||[]).map(x=>`<span>${esc(x)}</span>`).join('')||'<span>Tidak ada tanda terdeteksi dari kamus sederhana.</span>'}</div>`}

$('#analysisForm').addEventListener('submit',async e=>{e.preventDefault();try{const d=await api('/api/analisa',{method:'POST',body:JSON.stringify(collectClinical())});renderClinicalResults(d);renderFeatures(d.clinical_features||{});}catch(err){alert(err.message)}});
function renderClinicalResults(d){const arr=d.results||[];$('#fusionState').textContent=`Klinis: ${arr.length} hasil`;$('[id=fusionState]').className='chip mode-chip-clinical';$('#fusionEmpty').classList.add('hidden');$('#fusionContent').classList.remove('hidden');$('#clinicalEvidence').innerHTML=arr.map((x,i)=>`<div class="evidence-line"><div><b>${i+1}. ${esc(x.name||x.label)}</b><small>${esc(x.code||'teks bebas')} · support ${fmt(x.support_cases)}</small></div><span>${Number(x.confidence||0).toFixed(1)}%</span></div>`).join('')||'<div class="small-note">Belum ada hasil klinis.</div>';$('#visualEvidence').innerHTML='<div class="muted-box">Mode klinis: evidence foto tidak digunakan.</div>';$('#fusionResults').innerHTML=arr.map((x,i)=>`<div class="fusion-row"><div class="fusion-name"><b>${i+1}. ${esc(x.name||x.label||'-')}</b><small>${esc(x.code||'teks bebas')}</small></div><div class="fusion-bar"><span style="width:${Math.min(100,Math.max(0,Number(x.confidence||0)))}%"></span></div><div class="fusion-score">${Number(x.confidence||0).toFixed(1)}</div><div class="fusion-meta"><span>Clinical support ${fmt(x.support_cases)}</span><span class="chip mode-chip-clinical">klinis</span></div></div>`).join('')||'<div class="muted-box">Belum ada ranking klinis.</div>';$('#similarCard').classList.toggle('hidden',!((d.similar_cases||[]).length));}

$('#clearBtn').addEventListener('click',()=>{['#age','#alergi','#anamnese','#riwayat','#periksa'].forEach(s=>$(s).value='');$('#sex').value='';$('#clinicalFeatureBox').classList.add('hidden');$('#fusionContent').classList.add('hidden');$('#fusionEmpty').classList.remove('hidden');$('#fusionState').textContent='Belum dianalisa';$('#similarCard').classList.add('hidden');selectedImage=null;$('#eyeImage').value='';$('#imagePreviewWrap').classList.add('hidden');$('#imageAnalysisResult').classList.add('hidden');});

const dz=$('#dropZone'), fi=$('#eyeImage');
$('#chooseImageBtn').addEventListener('click',()=>fi.click());
fi.addEventListener('change',()=>{if(fi.files?.[0])setImage(fi.files[0])});
['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('dragging')}));['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('dragging')}));
dz.addEventListener('drop',e=>{if(e.dataTransfer.files?.[0])setImage(e.dataTransfer.files[0])});
function setImage(file){if(!['image/jpeg','image/png','image/webp'].includes(file.type))return alert('Format harus JPG/PNG/WEBP.');if(file.size>10*1024*1024)return alert('Maksimal 10 MB.');selectedImage=file;$('#imageFileName').textContent=`${file.name} · ${Math.round(file.size/1024)} KB`;$('#imagePreview').src=URL.createObjectURL(file);$('#imagePreviewWrap').classList.remove('hidden');}
$('#removeImageBtn').addEventListener('click',()=>{selectedImage=null;fi.value='';$('#imagePreviewWrap').classList.add('hidden');$('#imageAnalysisResult').classList.add('hidden')});
$('#analyzeImageBtn').addEventListener('click',async()=>{if(!selectedImage)return alert('Pilih foto dulu.');const f=new FormData();f.append('image',selectedImage);try{const d=await api('/api/analisa-gambar',{method:'POST',body:f});renderImageBaseline(d)}catch(e){alert(e.message)}});
function renderImageBaseline(d){
  const src=d||{};
  const q=src.quality||{};
  const meta=src.image||{};
  $('#imageAnalysisResult').classList.remove('hidden');
  $('#imageAnalysisResult').innerHTML=`<div class="image-result-head"><div><div class="label">QUALITY GATE</div><span class="quality-badge ${q.status==='baik'?'good':q.status==='cukup_dengan_catatan'?'warn':'bad'}">${esc(q.status||'unknown')}</span></div><div class="image-metrics"><span>Resolusi <b>${esc(meta.width||'-')}×${esc(meta.height||'-')}</b></span><span>Brightness <b>${esc(q.brightness??'-')}</b></span><span>Blur <b>${esc(q.blur_score??'-')}</b></span></div></div><div class="image-columns"><div><h4>Observasi</h4><ul>${(src.observations||[]).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>Tidak ada.</li>'}</ul></div><div><h4>Peringatan</h4><ul>${(src.warnings||[]).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>Tidak ada peringatan mayor.</li>'}</ul></div></div>`
}

$('#multimodalBtn').addEventListener('click',async()=>{if(analysisMode==='clinical')return; if(!selectedImage)return alert('Upload foto mata terlebih dahulu.');const f=new FormData();f.append('image',selectedImage);const c=collectClinical();if(analysisMode==='multimodal'){Object.entries(c).forEach(([k,v])=>{if(v!==null)f.append(k,String(v))});}$('#multimodalBtn').disabled=true;$('#multimodalBtn').textContent='Menganalisis…';try{const d=await api('/api/analisa-multimodal',{method:'POST',body:f});lastMultimodal=d;renderMultimodal(d);if(d.image)renderImageBaseline(d.image);renderFeatures(d.clinical_features||{});}catch(e){console.error('Multimodal error',e);alert(`Analisa multimodal gagal.\n\n${e?.message||e}\n\nLihat Console browser dan terminal server untuk detail.`)}finally{$('#multimodalBtn').disabled=false;$('#multimodalBtn').textContent=MODE_CONFIG[analysisMode].button}});
function renderMultimodal(d){$('#fusionContent').classList.remove('hidden');$('#fusionEmpty').classList.add('hidden');const hasClinical=Array.isArray(d.clinical_analysis?.results)&&d.clinical_analysis.results.length>0;const visionActive=Boolean(d.vision?.available);const state=analysisMode==='photo'?(visionActive?'Foto + Vision aktif':'Foto + quality/retrieval fallback'):analysisMode==='multimodal'?(visionActive?'Multimodal aktif':'Multimodal tanpa Vision provider'):'Klinis';$('#fusionState').textContent=state;const ce=Array.isArray(d.clinical_analysis?.results)?d.clinical_analysis.results:[];const ve=Array.isArray(d.visual_retrieval?.results)?d.visual_retrieval.results:[];const vr=d.vision?.analysis;$('#clinicalEvidence').innerHTML=ce.map((x,i)=>`<div class="evidence-line"><div><b>${i+1}. ${esc(x.name||x.label||'-')}</b><small>${esc(x.code||'teks bebas')} · support ${fmt(x.support_cases)}</small></div><span>${Number(x.confidence||0).toFixed(1)}%</span></div>`).join('')||'<div class="small-note">Tidak ada hasil klinis.</div>';
if(vr){$('#visualEvidence').innerHTML=`<div class="vision-summary"><div class="metric-row"><span>Photo type</span><b>${esc(vr.photo_type)}</b></div><div class="metric-row"><span>Laterality</span><b>${esc(vr.laterality)}</b></div><div class="metric-row"><span>Quality</span><b>${esc(vr.quality)}</b></div><p>${esc(vr.summary||'')}</p><div class="finding-list">${(vr.visible_findings||[]).map(x=>`<div class="finding"><b>${esc(x.finding)}</b><span>${Math.round(x.confidence*100)}%</span><small>${esc(x.evidence)}</small></div>`).join('')||'<div class="muted-box">Tidak ada temuan visual terstruktur.</div>'}</div>${(vr.limitations||[]).length?`<div class="limit-box"><b>Keterbatasan:</b> ${esc(vr.limitations.join(' · '))}</div>`:''}</div>`}else{$('#visualEvidence').innerHTML='<div class="muted-box">Vision provider belum tersedia. Pasang Ollama + qwen3-vl agar evidence visual AI aktif.</div>'}
const fused=Array.isArray(d.fused_results)?d.fused_results:[];$('#fusionResults').innerHTML=fused.map((x,i)=>{const score=Number(x.fusion_score||0);const cs=Number(x.clinical_support||0);const vs=Number(x.visual_support||0);return `<div class="fusion-row"><div class="fusion-name"><b>${i+1}. ${esc(x.name||x.label||'-')}</b><small>${esc(x.code||'teks bebas')}</small></div><div class="fusion-bar"><span style="width:${Math.min(100,Math.max(0,score))}%"></span></div><div class="fusion-score">${score.toFixed(1)}</div><div class="fusion-meta"><span>Klinis ${cs.toFixed(1)}%</span><span>Visual ${vs.toFixed(1)}%</span><span class="chip">${esc(x.consistency||'-')}</span></div></div>`}).join('')||'<div class="muted-box">Belum ada hasil fusion.</div>';
const cases=d.clinical_analysis?.similar_cases||[];if(cases.length){$('#similarCard').classList.remove('hidden');$('#similarList').innerHTML=cases.map(x=>`<div class="case"><div class="case-grid"><div><div class="label">Kemiripan</div><strong>${Math.round(x.similarity*100)}%</strong></div><div><div><b>${esc(x.age_group||'-')}</b> · ${esc(x.visit_year||'-')} · Poli ${esc(x.kd_poli||'-')}</div><div><span class="label">Anamnesa</span><br>${esc(x.case?.anamnese||'-')}</div><div><span class="label">Periksa</span><br>${esc(x.case?.periksa||'-')}</div><div><span class="label">Diagnosa</span><br>${esc((x.case?.diagnoses||[]).join(' | '))}</div></div></div></div>`).join('')}
}

async function loadDashboard(){try{const d=await api('/api/statistik');$('#statsCards').innerHTML=`<div class="stat"><div class="n">${fmt(d.total_cases)}</div><div class="l">Kasus terindeks</div></div><div class="stat"><div class="n">${fmt(d.unique_diagnoses)}</div><div class="l">Label diagnosis</div></div><div class="stat"><div class="n">${d.age_groups.length}</div><div class="l">Kelompok usia</div></div><div class="stat"><div class="n">${d.monthly.length}</div><div class="l">Bulan berdata</div></div>`;const max=d.top_diagnoses[0]?.count||1;$('#topDiag').innerHTML=d.top_diagnoses.map(x=>`<div class="rank"><div class="rank-head"><span>${esc(x.label)}</span><b>${fmt(x.count)}</b></div><div class="bar"><span style="width:${Math.round(x.count/max*100)}%"></span></div></div>`).join('');const maxAge=Math.max(...d.age_groups.map(x=>x.count),1);$('#ageGroups').innerHTML=d.age_groups.map(x=>`<div class="rank"><div class="rank-head"><span>${esc(x.label)}</span><b>${fmt(x.count)}</b></div><div class="bar"><span style="width:${Math.round(x.count/maxAge*100)}%"></span></div></div>`).join('');const last=d.monthly.slice(-18),mx=Math.max(...last.map(x=>x.count),1);$('#monthlyChart').innerHTML=last.map(x=>`<div class="bar-col"><div class="col" style="height:${Math.max(4,Math.round(x.count/mx*180))}px"></div><small>${esc(x.month)}</small></div>`).join('')}catch(e){alert(e.message)}}
async function searchHistory(){try{const p=new URLSearchParams();if($('#histQ').value)p.set('q',$('#histQ').value);if($('#histDiagnosis').value)p.set('diagnosis',$('#histDiagnosis').value);if($('#histAge').value)p.set('age_group',$('#histAge').value);if($('#histYear').value)p.set('year',$('#histYear').value);const d=await api('/api/riwayat?'+p.toString());$('#historyBody').innerHTML=d.items.map(x=>`<tr><td>${esc(x.visit_date||'-')}</td><td>${esc(x.age_group||'-')}</td><td>${esc(x.kd_poli||'-')}</td><td>${esc(x.anamnese||'-')}</td><td>${esc(x.periksa||'-')}</td><td>${esc((x.diagnoses||[]).join(' | '))}</td></tr>`).join('')||'<tr><td colspan="6">Tidak ada data.</td></tr>'}catch(e){alert(e.message)}}
$('#histBtn').addEventListener('click',searchHistory);
async function loadDictionary(){if(!dictItems.length){const d=await api('/api/kamus');dictItems=d.items}renderDict()}function renderDict(){const q=$('#dictQ').value.toLowerCase();const arr=dictItems.filter(x=>!q||x.label.toLowerCase().includes(q));$('#dictBody').innerHTML=arr.slice(0,300).map(x=>`<tr><td>${esc(x.code||'-')}</td><td>${esc(x.name)}</td><td>${x.code?'ICD-10':'Teks bebas'}</td><td>${fmt(x.count)}</td></tr>`).join('')||'<tr><td colspan="4">Tidak ada data.</td></tr>'}$('#dictBtn').addEventListener('click',renderDict);$('#dictQ').addEventListener('keydown',e=>{if(e.key==='Enter')renderDict()});
async function loadEvaluation(){try{const d=await api('/api/evaluasi');if(!d.available){$('#evalContent').innerHTML=`<strong>${esc(d.message)}</strong>`;return}const k=d.metrics||{};$('#evalContent').innerHTML=`<div class="eval-kpis"><div class="eval-kpi"><small>Recall@3</small><b>${k.recall_at_3!=null?(k.recall_at_3*100).toFixed(2)+'%':'-'}</b></div><div class="eval-kpi"><small>Recall@5</small><b>${k.recall_at_5!=null?(k.recall_at_5*100).toFixed(2)+'%':'-'}</b></div><div class="eval-kpi"><small>Test cases</small><b>${fmt(k.test_cases)}</b></div></div><p class="small-note">Retrospektif patient-group holdout. Bukan validasi klinis foto.</p>`}catch(e){alert(e.message)}}
boot();
