
document.addEventListener('keydown', e => {
  if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA'||e.target.tagName==='SELECT')return;
  const ids=Object.keys(state.kpis),ci=ids.indexOf(state.selectedKpi);
  if(e.key==='j'||e.key==='ArrowDown'){const n=ids[(ci+1)%ids.length];if(n)selectKpi(n);}
  else if(e.key==='k'||e.key==='ArrowUp'){const p=ids[(ci-1+ids.length)%ids.length];if(p)selectKpi(p);}
  else if(e.key==='1')changeRole('EXECUTIVE');
  else if(e.key==='2')changeRole('ANALYST');
  else if(e.key==='3')changeRole('OPERATIONS');
  else if(e.key==='r'||e.key==='R')loadKpis();
  else if(e.key==='Escape'){state.selectedKpi=null;document.getElementById('detailPanel').innerHTML='<div class="card"><div class="story-empty"><div class="ei">&#128269;</div><p>Select a metric card or use the AI input box above.</p></div></div>';}
});

const state={kpis:{},kpiHistory:{},selectedKpi:null,activeRole:'EXECUTIVE',backend:'ollama',apiKey:'',lastStory:null,feedbackHistory:[],earlyWarnings:[],lastUpdated:null};

document.getElementById('backendSelector').addEventListener('change',e=>{
  state.backend=e.target.value;
  document.getElementById('apiKeyLabel').style.display=['gemini','openai','anthropic','grok'].includes(state.backend)?'flex':'none';
});
document.getElementById('apiKeyInput').addEventListener('input',e=>{state.apiKey=e.target.value;});

function changeRole(role){
  state.activeRole=role;
  document.querySelectorAll('.ptab').forEach(t=>t.classList.toggle('active',t.dataset.role===role));
  if(state.lastStory)renderStory(state.lastStory);
}

let btt=null;
function debounceBacktest(){clearTimeout(btt);btt=setTimeout(runBacktest,800);}
async function runBacktest(){
  const p=document.getElementById('primaryThresh')?.value||1.75,s=document.getElementById('secondaryThresh')?.value||3.0;
  const el=document.getElementById('backtestResult');el.textContent='Calculating...';
  try{
    const r=await fetch(`/backtest?primary=${p}&secondary=${s}&days=180`).then(r=>r.json());
    if(r.error)throw new Error(r.error);
    el.textContent=`Accuracy: ${r.f1?(r.f1*100).toFixed(0)+'%':'--'} | False Alarms: ${r.false_alarm_rate?(r.false_alarm_rate*100).toFixed(0)+'%':'--'}`;
    el.style.color=r.f1>0.5?'var(--green)':r.f1>0.3?'var(--accent)':'var(--red)';
  }catch(e){el.textContent='Could not calculate';}
}

async function runNLQuery(){
  const q=document.getElementById('nlQuery')?.value?.trim();if(!q)return;
  const el=document.getElementById('nlResult');el.style.display='block';el.textContent='Searching...';
  try{
    const r=await fetch('/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,backend:state.backend})}).then(r=>r.json());
    el.textContent=`Found: Metric=${r.parsed_kpi}, Location=${r.parsed_region}, Status=${r.kpi_status}`;
    if(r.kpi_status==='anomaly'){el.textContent+=' — loading full analysis...';state.selectedKpi=r.parsed_kpi;selectKpi(r.parsed_kpi);}
  }catch(e){el.textContent='Error: '+e.message;}
}

async function loadKpis(){
  try{
    const d=await fetch('/kpis').then(r=>r.json());
    d.forEach(k=>{state.kpis[k.kpi_id]=k;});
    for(const k of d){
      if(k.status!=='insufficient_data'){
        const h=await fetch('/kpis/'+k.kpi_id+'/history?days=14');
        if(h.ok)state.kpiHistory[k.kpi_id]=await h.json();
      }
    }
    state.earlyWarnings=d.filter(k=>k.early_warning);
    state.lastUpdated=new Date().toLocaleTimeString();
    renderHeader();renderGrid();
    if(typeof renderHeatmap==='function')renderHeatmap();
  }catch(e){console.error(e);}
}

async function loadHistory(){
  try{const d=await fetch('/feedback/history?n=50').then(r=>r.json());state.feedbackHistory=d.records||[];renderHistory();}catch(e){}
}

async function submitFeedback(fbType,value,anomalyId,hypIdx){
  try{await fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feedback_type:fbType,value,anomaly_id:anomalyId,hypothesis_index:hypIdx,provider_role:state.activeRole})});loadHistory();}catch(e){}
}

function renderSparkline(hist){
  if(!hist||!hist.values||!hist.values.length)return'';
  const w=80,h=30,vals=hist.values,ub=hist.upper_bounds||vals,lb=hist.lower_bounds||vals;
  const max=Math.max(...vals,...ub),min=Math.min(...vals,...lb),range=(max-min)||1;
  const dx=w/(vals.length-1||1),getY=v=>h-((v-min)/range)*h;
  let area='';
  for(let i=0;i<vals.length-1;i++){if(vals[i]==null||vals[i+1]==null)continue;area+=`${i*dx},${getY(ub[i])} ${(i+1)*dx},${getY(ub[i+1])} ${(i+1)*dx},${getY(lb[i+1])} ${i*dx},${getY(lb[i])} `;}
  let path='',first=true;
  for(let i=0;i<vals.length;i++){if(vals[i]!=null){if(first){path+=`M ${i*dx} ${getY(vals[i])}`;first=false;}else{path+=` L ${i*dx} ${getY(vals[i])}`;} }}
  return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polygon points="${area}" fill="rgba(245,158,11,.08)"/><path d="${path}" fill="none" stroke="var(--muted)" stroke-width="1.5"/><circle cx="${(vals.length-1)*dx}" cy="${getY(vals[vals.length-1])}" r="2.5" fill="var(--accent)"/></svg>`;
}

function renderHeader(){
  const b=document.getElementById('warningBanner');
  if(state.earlyWarnings.length>0){b.style.display='flex';b.innerHTML=`&#9888; ${state.earlyWarnings[0].name} is trending toward a problem`;}
  else b.style.display='none';
  document.getElementById('lastUpdated').textContent='Last refresh: '+state.lastUpdated;
}

function renderHeatmap(){
  const svg=document.getElementById('heatmapSvg');
  if(!svg||!Object.keys(state.kpis).length)return;
  const ids=Object.keys(state.kpis),regions=['Region X','Region Y','Region Z'];
  const cW=100,cH=28,lW=80;
  svg.setAttribute('viewBox',`0 0 ${lW+ids.length*cW} ${28+regions.length*cH}`);
  let html='';
  ids.forEach((id,ci)=>{html+=`<text x="${lW+ci*cW+cW/2}" y="18" text-anchor="middle" font-family="Inter" font-size="9" fill="#718096">${(state.kpis[id]?.name||id).split(' ').slice(-1)[0]}</text>`;});
  regions.forEach((r,ri)=>{
    html+=`<text x="${lW-4}" y="${28+ri*cH+cH/2+4}" text-anchor="end" font-family="Inter" font-size="9" fill="#718096">${r}</text>`;
    ids.forEach((id,ci)=>{
      const sev=ri===0?(state.kpis[id]?.severity_score||0):Math.random()*0.3,alpha=Math.min(sev,1);
      const color=sev>0.7?`rgba(239,68,68,${alpha})`:sev>0.4?`rgba(245,158,11,${alpha})`:`rgba(16,185,129,${alpha*0.6})`;
      const x=lW+ci*cW,y=28+ri*cH;
      html+=`<rect x="${x+1}" y="${y+1}" width="${cW-2}" height="${cH-2}" rx="3" fill="${color}" opacity="0.85"/>`;
      html+=`<text x="${x+cW/2}" y="${y+cH/2+4}" text-anchor="middle" font-family="Inter" font-size="9" fill="#fff" font-weight="600">${(sev*100).toFixed(0)}%</text>`;
    });
  });
  svg.innerHTML=html;
}

function renderGrid(){
  const grid=document.getElementById('kpiGrid');grid.innerHTML='';
  const nm={'revenue_total':'Total Revenue &#128176;','units_sold':'Units Sold &#128230;','avg_price':'Avg. Selling Price &#127991;','marketing_spend':'Marketing Spend &#128226;','inventory_level':'Inventory Level &#127981;'};
  Object.values(state.kpis).forEach(k=>{
    const el=document.createElement('div');
    el.className='kpi-card'+(k.kpi_id===state.selectedKpi?' active':'')+(k.status==='anomaly'?' has-anomaly':'')+(k.early_warning?' has-warning':'');
    el.onclick=()=>selectKpi(k.kpi_id);
    const spark=state.kpiHistory[k.kpi_id]&&!state.kpiHistory[k.kpi_id].error?renderSparkline(state.kpiHistory[k.kpi_id]):'';
    const st=k.status==='insufficient_data'?'&#9898; Not enough data':k.status==='anomaly'?'&#128308; Problem detected &mdash; click!':'&#128994; All normal';
    const bc=k.status==='anomaly'?'anomaly':'noise';
    el.innerHTML=`<p class="kpi-name">${nm[k.kpi_id]||k.name}</p><p class="kpi-value">${k.value!==undefined?Number(k.value).toLocaleString():'--'}</p><span class="kpi-delta ${k.trend_direction||'flat'}">${k.delta_pct!==undefined?(k.delta_pct>0?'&#9650; ':'&#9660; ')+Math.abs(k.delta_pct)+'% vs expected':'--'}</span><br/><span class="kpi-badge ${bc}">${st}</span>${spark}`;
    grid.appendChild(el);
  });
}

async function selectKpi(kpiId){
  state.selectedKpi=kpiId;renderGrid();
  const k=state.kpis[kpiId];
  if(!k||k.status!=='anomaly'){document.getElementById('detailPanel').innerHTML=`<div class="card"><div class="story-empty"><div class="ei">&#9989;</div><p><strong>${k?k.name:kpiId}</strong> is within its normal range. No problem detected right now.</p></div></div>`;return;}
  document.getElementById('detailPanel').innerHTML=`<div class="card"><div class="story-empty"><div class="ei">&#128260;</div><p>Loading AI analysis for <strong>${k.name}</strong>...<br><small style="color:var(--muted)">This may take up to 2 minutes on local Ollama.</small></p></div></div>`;
  try{
    const payload={test_case:'live',kpi_id:kpiId,region:'Region X',backend:state.backend};
    if(state.apiKey)payload.api_key=state.apiKey;
    const data=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());
    if(data.error){document.getElementById('detailPanel').innerHTML=`<div class="card"><div class="story-empty"><div class="ei">&#10060;</div><p><strong>Error:</strong> ${data.error}</p></div></div>`;return;}
    if(data.verdict==='noise'){document.getElementById('detailPanel').innerHTML=`<div class="card"><div class="story-empty"><div class="ei">&#9989;</div><p>Deeper check confirms this is normal variation &mdash; no action needed.</p></div></div>`;return;}
    state.lastStory=data;renderStory(data);
  }catch(e){document.getElementById('detailPanel').innerHTML=`<div class="card"><div class="story-empty"><div class="ei">&#10060;</div><p>Could not fetch analysis: ${e.message}</p></div></div>`;}
}

function renderStory(data){
  const detail=document.getElementById('detailPanel');
  const s=data.original_story;
  if(!s){detail.innerHTML=`<div class="card"><div class="story-empty"><p>No analysis data available.</p></div></div>`;return;}
  let p=(data.persona_narratives&&data.persona_narratives[state.activeRole])||{headline:s.headline,explanation:s.explanation,escalate:s.escalate_flag,structured_actions:data.structured_actions};
  const conf=Math.round((p.confidence||s.overall_confidence||0.5)*100);

  let html=`<div class="card">
  <div class="story-head">
    <div>
      <div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">&#129302; AI Summary</div>
      <h3 class="story-headline">${p.headline}${p.escalate?'<span class="esc-badge">&#9888; Needs expert review</span>':''}${data.peer_benchmark?`<span class="peer-chip ${data.peer_benchmark}">${data.peer_benchmark==='Market-wide'?'&#127760; Market-wide issue':data.peer_benchmark==='Regional'?'&#128205; Regional issue':'&#128308; Outlier'}</span>`:''}</h3>
    </div>
    <div class="conf-block">
      <div class="conf-num">${conf}%</div>
      <div class="conf-lbl">AI Confidence <span class="tip" data-tip="How sure the AI is. Above 70% = confident. Below 50% = uncertain, verify manually.">?</span></div>
      <div class="conf-bar"><div class="conf-bar-fill" style="width:${conf}%"></div></div>
    </div>
  </div>
  <div class="ptabs">
    <button class="ptab ${state.activeRole==='EXECUTIVE'?'active':''}" data-role="EXECUTIVE" onclick="changeRole('EXECUTIVE')">&#128084; Simple Summary</button>
    <button class="ptab ${state.activeRole==='ANALYST'?'active':''}" data-role="ANALYST" onclick="changeRole('ANALYST')">&#128202; Detailed Analysis</button>
    <button class="ptab ${state.activeRole==='OPERATIONS'?'active':''}" data-role="OPERATIONS" onclick="changeRole('OPERATIONS')">&#9881; Action Plan</button>
  </div>
  <div class="expl-box">${p.explanation}</div>`;

  if(s.escalate_flag)html+=`<div class="esc-box"><h4>&#9888;&#65039; This needs a human expert to review it</h4><p style="font-size:13px;color:var(--text2);margin-bottom:8px">The AI found multiple conflicting explanations and cannot confidently pick one single cause.</p><ul><li>The top two possible explanations have very similar confidence scores</li><li>Recommended next step: Share this with your data science or analytics team</li></ul></div>`;

  if(data.cross_kpi_cascade&&data.cross_kpi_cascade.length>0)html+=`<div class="sub-title">&#128279; Other Metrics Also Affected <span class="tip" data-tip="When one metric drops, it can pull related metrics down too. These also show unusual patterns at the same time.">?</span></div><div class="ckpi-row">${data.cross_kpi_cascade.map(c=>`<div class="ckpi-item"><div class="name">${c.kpi}</div><div class="val">${c.impact}</div></div>`).join('')}</div>`;

  if(state.activeRole!=='EXECUTIVE')html+=`<div class="sub-title">&#129504; Possible Causes, Ranked by Likelihood <span class="tip" data-tip="The AI ranked multiple explanations by how well they fit the data. First = most likely. Click thumbs up/down to give feedback.">?</span></div><ul class="hyp-list">${s.hypotheses.map((h,idx)=>`<li class="hyp-item"><div class="hyp-row"><span class="hyp-cause">${idx+1}. ${h.cause}</span><span class="hyp-pct">${Math.round(h.confidence*100)}% likely</span></div><div class="citations">${h.citations.map(c=>`<span class="citation">${c}</span>`).join('')}</div><div class="fb-btns"><button onclick="submitFeedback('hypothesis_validity',5,'${data.anomaly_id||''}',${idx})">&#128077; Correct</button><button onclick="submitFeedback('hypothesis_validity',1,'${data.anomaly_id||''}',${idx})">&#128078; Wrong</button></div></li>`).join('')}</ul>`;

  if(state.activeRole==='OPERATIONS'||state.activeRole==='ANALYST'){
    const acts=p.structured_actions||data.structured_actions||[];
    if(acts.length>0)html+=`<div class="sub-title">&#128203; Recommended Actions <span class="tip" data-tip="Specific steps to fix the problem. Shows what went wrong, what to change, who should act, and how confident the AI is.">?</span></div><table class="at"><thead><tr><th>What went wrong</th><th>What can be changed</th><th>Recommended action</th><th>Expected result</th><th>Who should act</th><th>Confidence</th></tr></thead><tbody>${acts.map(a=>`<tr><td>${a.driver}</td><td>${a.controllable_leverage}</td><td>${a.action}</td><td>${a.expected_impact}</td><td style="font-weight:600;color:var(--text)">${a.owner}</td><td><span class="cpill ${a.confidence}">${a.confidence}</span></td></tr>`).join('')}</tbody></table>`;
  }

  const drivers=(s.structured_drivers||s.hypotheses||[]).slice(0,3);
  const dOpts=drivers.map(d=>`<option value="${d.driver||d.cause||''};${d.contribution_pct||0.15}">${d.driver||d.cause||'Unknown'}</option>`).join('');
  html+=`<div class="wi-box"><h3>&#129514; What-If Simulator <span class="tip" data-tip="Test scenarios: 'What if marketing spend increases 10%? How would revenue change?' The AI estimates the impact.">?</span></h3><div class="wi-row"><label>If this factor changes:<select id="wiDriver" style="background:var(--surface);border:1px solid var(--border);padding:7px 10px;border-radius:var(--rs);font-size:13px;color:var(--text)">${dOpts||'<option value="avg_price;0.15">Average Price</option>'}</select></label><label>By how much (%):<input type="number" id="wiPct" value="-5" min="-50" max="50" style="width:80px"></label><button class="btn btn-secondary" onclick="runWhatIf()">Run Simulation</button></div><div id="wiResult"></div></div>`;

  const tel=data.telemetry||{};
  html+=`<div class="tel-row"><span class="ti">AI Engine: <b>${state.backend}</b></span><span class="ti">Method: <b>Maths + AI</b></span><span class="ti">Processing time: <b>${tel.latency_ms?(tel.latency_ms/1000).toFixed(1)+'s':'--'}</b></span><span class="ti">AI tokens: <b>${tel.llm_total_tokens_estimate||'--'}</b></span></div>`;
  html+=`<div style="margin-top:20px;border-top:1px solid var(--border);padding-top:16px"><span style="font-size:12px;font-weight:600;color:var(--muted)">Data Trail (how the answer was reached)</span><button class="btn btn-secondary btn-sm" style="margin-left:10px" onclick="loadLineage('${data.kpi_id||state.selectedKpi}')">Show data trail</button><div id="lineagePanel" style="margin-top:10px"></div></div></div>`;
  detail.innerHTML=html;
}

async function runWhatIf(){
  const dv=document.getElementById('wiDriver')?.value||'avg_price;0.15',[driver]=dv.split(';');
  const pct=parseFloat(document.getElementById('wiPct')?.value||-5)/100,kpi=state.kpis[state.selectedKpi]||{};
  document.getElementById('wiResult').textContent='Simulating...';
  try{
    const r=await fetch('/whatif',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'simulate',driver,driver_change_pct:pct,target_kpi:state.selectedKpi||'revenue_total',current_kpi_value:kpi.value||85000})}).then(r=>r.json());
    if(r.error)throw new Error(r.error);
    const dir=r.predicted_kpi_change_pct>0?'&#9650;':'&#9660;',col=r.predicted_kpi_change_pct>0?'var(--green)':'var(--red)';
    document.getElementById('wiResult').innerHTML=`If <b>${driver}</b> changes by <b>${(pct*100).toFixed(0)}%</b>: <span style="color:${col};font-weight:700">${dir} ${Math.abs(r.predicted_kpi_change_pct*100).toFixed(1)}%</span> &rarr; estimated: <b>${r.predicted_kpi_value?.toLocaleString()}</b>`;
  }catch(e){document.getElementById('wiResult').textContent='Simulation error: '+e.message;}
}

async function loadLineage(kpiId){
  const el=document.getElementById('lineagePanel');if(!el)return;
  el.innerHTML='<p style="font-size:12px;color:var(--muted)">Loading...</p>';
  try{
    const r=await fetch(`/lineage/${kpiId}`).then(r=>r.json());
    const rows=(r.lineage_chain||[]).map(s=>{
      const tag=s.is_llm?'<span style="background:var(--accent-s);color:var(--accent);padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">AI step</span>':'<span style="background:var(--green-s);color:var(--green);padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600">Math step</span>';
      return `<tr><td style="color:var(--text)">${s.step}</td><td>${tag}</td><td style="color:var(--text2)">${s.method}</td></tr>`;
    }).join('');
    el.innerHTML=`<table style="width:100%;font-size:12px;border-collapse:collapse"><thead><tr><th style="text-align:left;padding:6px;font-size:11px;color:var(--muted);border-bottom:1px solid var(--border)">Step</th><th style="text-align:left;padding:6px;font-size:11px;color:var(--muted);border-bottom:1px solid var(--border)">Type</th><th style="text-align:left;padding:6px;font-size:11px;color:var(--muted);border-bottom:1px solid var(--border)">Method</th></tr></thead><tbody>${rows}</tbody></table>`;
  }catch(e){el.innerHTML='<p style="color:var(--red);font-size:12px">Could not load data trail.</p>';}
}

function renderHistory(){
  const list=document.getElementById('historyList');
  if(!state.feedbackHistory.length){list.innerHTML='<li style="color:var(--muted);font-size:13px">No feedback yet. Use the thumbs up/down buttons after an analysis to give feedback.</li>';return;}
  list.innerHTML=state.feedbackHistory.slice().reverse().map(r=>{
    const stars='&#9733;'.repeat(r.value)+'&#9734;'.repeat(5-r.value);
    return `<li class="hist-item"><span class="hist-date">${new Date(r.timestamp).toLocaleString()}</span><span style="color:var(--text2)">${r.feedback_type}</span><span style="color:var(--accent)">${stars}</span><span style="color:var(--muted)">${r.provider_role}</span></li>`;
  }).join('');
}

async function submitCustomKpi(){
  const payload={kpi_id:document.getElementById('ckId')?.value,name:document.getElementById('ckName')?.value,formula:document.getElementById('ckFormula')?.value,threshold_warning:parseFloat(document.getElementById('ckWarn')?.value||5)/100,threshold_critical:parseFloat(document.getElementById('ckWarn')?.value||5)/100*3};
  if(!payload.kpi_id||!payload.name){document.getElementById('ckResult').textContent='Please fill in both the Code and Display Name.';return;}
  try{
    const r=await fetch('/kpi/define',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());
    const el=document.getElementById('ckResult');
    el.textContent=r.error?'Error: '+r.error:'&#9989; Added: '+r.name;
    el.style.color=r.error?'var(--red)':'var(--green)';
    if(!r.error)loadKpis();
  }catch(e){document.getElementById('ckResult').textContent='Error: '+e.message;}
}

function uploadCSV(input){
  if(!input.files||!input.files.length)return;
  const fd=new FormData();fd.append('file',input.files[0]);
  fetch('/upload',{method:'POST',body:fd})
    .then(r=>r.json())
    .then(d=>{if(d.error)alert('Upload failed: '+d.error);else{alert('Success! Added '+d.rows_added+' rows. Dashboard refreshing now.');loadKpis();}})
    .catch(e=>alert('Upload error: '+e.message));
  input.value='';
}

let magicInt=null;
async function runMagicAnalysis(){
  const raw=document.getElementById('magicInput').value.trim();
  if(!raw){alert('Please write something in the text box first.');return;}
  const tDiv=document.getElementById('magicTimer'),sSp=document.getElementById('magicStatus'),secSp=document.getElementById('magicSeconds'),errDiv=document.getElementById('magicError'),panel=document.getElementById('detailPanel');
  errDiv.style.display='none';tDiv.style.display='flex';sSp.style.color='var(--muted)';
  panel.innerHTML='<div class="card"><div class="story-empty"><div class="ei">&#129302;</div><p>AI is reading your input and running the analysis...<br><small style="color:var(--muted)">This can take 1-2 minutes on local Ollama. Please wait.</small></p></div></div>';
  let sec=0;sSp.textContent='Step 1/2: Reading your input...';
  if(magicInt)clearInterval(magicInt);
  magicInt=setInterval(()=>{sec+=0.1;secSp.textContent=sec.toFixed(1);},100);
  try{
    const pl={raw_text:raw,backend:state.backend,model:document.getElementById('modelInput').value};
    if(state.apiKey)pl.api_key=state.apiKey;
    const fmt=await fetch('/format_input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pl)}).then(r=>r.json());
    if(fmt.error)throw new Error(fmt.error);
    sSp.textContent='Step 2/2: Running causal analysis...';
    const apl={test_case:'custom',backend:state.backend,model:pl.model,anomaly:fmt.anomaly,correlation:fmt.correlation,evidence:fmt.evidence};
    if(state.apiKey)apl.api_key=state.apiKey;
    const story=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(apl)}).then(r=>r.json());
    if(story.error)throw new Error(story.error);
    sSp.textContent='&#9989; Analysis complete!';sSp.style.color='var(--green)';
    state.lastStory=story;renderStory(story);
  }catch(e){
    sSp.textContent='&#10060; Failed';sSp.style.color='var(--red)';
    let msg='Error: '+e.message;
    if(e.message.includes('API key'))msg+=' Check your API key in the settings above.';
    if(e.message.includes('ollama')||e.message.includes('connection'))msg+=' Make sure Ollama is running (run "ollama serve" in a terminal).';
    errDiv.textContent=msg;errDiv.style.display='block';
    panel.innerHTML='<div class="card"><div class="story-empty"><div class="ei">&#10060;</div><p>Analysis failed. See the error message above.</p></div></div>';
  }finally{clearInterval(magicInt);}
}

function startLiveUpdates(){
  if(typeof EventSource!=='undefined'){
    const es=new EventSource('/stream/kpis');
    es.onmessage=e=>{try{const k=JSON.parse(e.data);if(Array.isArray(k)){k.forEach(ki=>{state.kpis[ki.kpi_id]=ki;});state.lastUpdated=new Date().toLocaleTimeString();document.getElementById('lastUpdated').textContent='Last refresh: '+state.lastUpdated;renderGrid();if(typeof renderHeatmap==='function')renderHeatmap();}}catch(err){}};
    es.onerror=()=>{es.close();setInterval(loadKpis,60000);};
  }else{setInterval(loadKpis,60000);}
}

loadKpis();loadHistory();startLiveUpdates();
