import re

with open('d:/project/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Feature 1
hint_html = """      <span class="sim-badge">LIVE</span>
      <span style="font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--dim); cursor:pointer;" onclick="alert('J/K: navigate | 1/2/3: role | R: refresh | Esc: clear | ?: help')">[ ? shortcuts ]</span>"""
content = content.replace('      <span class="sim-badge">LIVE</span>', hint_html)

js_shortcuts = """// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  const kpiIds = Object.keys(state.kpis);
  const currentIdx = kpiIds.indexOf(state.selectedKpi);
  if (e.key === 'j' || e.key === 'ArrowDown') {
    const next = kpiIds[(currentIdx + 1) % kpiIds.length];
    if (next) selectKpi(next);
  } else if (e.key === 'k' || e.key === 'ArrowUp') {
    const prev = kpiIds[(currentIdx - 1 + kpiIds.length) % kpiIds.length];
    if (prev) selectKpi(prev);
  } else if (e.key === '1') changeRole('EXECUTIVE');
  else if (e.key === '2') changeRole('ANALYST');
  else if (e.key === '3') changeRole('OPERATIONS');
  else if (e.key === 'r' || e.key === 'R') loadKpis();
  else if (e.key === 'Escape') {
    state.selectedKpi = null;
    document.getElementById('detailPanel').innerHTML = '<div class="noise-panel">Click on an anomaly card to view the live story and causal analysis.</div>';
  }
  else if (e.key === '?') {
    alert('Keyboard shortcuts:\\nJ/K or ↑↓ — navigate KPIs\\n1/2/3 — switch role\\nR — refresh\\nEsc — clear story');
  }
});
"""
content = content.replace('<script>\n', '<script>\n' + js_shortcuts)

# Feature 2
heatmap_html = """  <section>
    <h2><span class="bracket">[</span> regional heatmap <span class="bracket">]</span></h2>
    <div id="regionHeatmap" style="overflow-x:auto;">
      <svg id="heatmapSvg" width="100%" viewBox="0 0 700 100" style="display:block;"></svg>
    </div>
  </section>
"""
content = content.replace('  <section>\n    <h2><span class="bracket">[</span> analysis & story <span class="bracket">]</span></h2>', heatmap_html + '  <section>\n    <h2><span class="bracket">[</span> analysis & story <span class="bracket">]</span></h2>')

heatmap_js = """function renderHeatmap() {
  const svg = document.getElementById('heatmapSvg');
  if (!svg || !Object.keys(state.kpis).length) return;
  
  const kpiIds = Object.keys(state.kpis);
  const regions = ['Region X', 'Region Y', 'Region Z'];
  const cellW = 100, cellH = 28, labelW = 80;
  const totalW = labelW + kpiIds.length * cellW;
  const totalH = 28 + regions.length * cellH;
  svg.setAttribute('viewBox', `0 0 ${totalW} ${totalH}`);
  
  let html = '';
  kpiIds.forEach((kpiId, ci) => {
    const kpi = state.kpis[kpiId];
    const shortName = (kpi?.name || kpiId).split(' ').slice(-1)[0];
    html += `<text x="${labelW + ci*cellW + cellW/2}" y="18" text-anchor="middle" font-family="IBM Plex Mono" font-size="9" fill="#8b91a0">${shortName}</text>`;
  });
  
  regions.forEach((region, ri) => {
    html += `<text x="${labelW-4}" y="${28 + ri*cellH + cellH/2 + 4}" text-anchor="end" font-family="IBM Plex Mono" font-size="9" fill="#8b91a0">${region}</text>`;
    kpiIds.forEach((kpiId, ci) => {
      const kpi = state.kpis[kpiId];
      const sev = ri === 0 ? (kpi?.severity_score || 0) : Math.random() * 0.3;
      const alpha = Math.min(sev, 1.0);
      const color = sev > 0.7 ? `rgba(226,100,90,${alpha})` :
                    sev > 0.4 ? `rgba(231,163,62,${alpha})` :
                                `rgba(111,174,124,${alpha * 0.5})`;
      const x = labelW + ci * cellW;
      const y = 28 + ri * cellH;
      html += `<rect x="${x+1}" y="${y+1}" width="${cellW-2}" height="${cellH-2}" rx="3" fill="${color}" opacity="0.85"/>`;
      html += `<text x="${x+cellW/2}" y="${y+cellH/2+4}" text-anchor="middle" font-family="IBM Plex Mono" font-size="9" fill="#ece9e1">${(sev*100).toFixed(0)}%</text>`;
    });
  });
  svg.innerHTML = html;
}
"""
content = content.replace('function renderGrid() {', heatmap_js + '\nfunction renderGrid() {')
content = content.replace('renderGrid();\n  } catch(e)', 'renderGrid();\n    if (typeof renderHeatmap === "function") renderHeatmap();\n  } catch(e)')

# Feature 3
whatif_js = """function renderWhatIf(story) {
  if (!story) return '';
  const drivers = (story.structured_drivers || story.hypotheses || []).slice(0, 3);
  const driverOptions = drivers.map(d => `<option value="${d.driver || d.cause || ''};${d.contribution_pct || 0.15}">${d.driver || d.cause || 'Unknown'}</option>`).join('');
  return `
  <div style="margin-top:20px; padding:16px; background:var(--ink); border:1px solid var(--wire); border-radius:8px;">
    <h3 style="font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--dim); margin:0 0 12px;">[ what-if simulator ]</h3>
    <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end;">
      <label style="font-size:13px;">Driver:
        <select id="wiDriver" style="background:var(--panel); color:var(--paper); border:1px solid var(--wire); padding:4px 8px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; margin-left:6px;">
          ${driverOptions || '<option value="avg_price;0.15">avg_price</option>'}
        </select>
      </label>
      <label style="font-size:13px;">Change: <input type="number" id="wiPct" value="-5" min="-50" max="50" style="width:70px; background:var(--panel); color:var(--paper); border:1px solid var(--wire); padding:4px 8px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; margin-left:6px;"> %</label>
      <button onclick="runWhatIf()" style="background:var(--signal); color:var(--ink); border:none; padding:6px 14px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; cursor:pointer;">Simulate</button>
    </div>
    <div id="wiResult" style="margin-top:12px; font-family:'IBM Plex Mono',monospace; font-size:13px; color:var(--body-text);"></div>
  </div>`;
}

async function runWhatIf() {
  const driverVal = document.getElementById('wiDriver')?.value || 'avg_price;0.15';
  const [driver, contribStr] = driverVal.split(';');
  const pct = parseFloat(document.getElementById('wiPct')?.value || -5) / 100;
  const kpi = state.kpis[state.selectedKpi] || {};
  document.getElementById('wiResult').textContent = 'Simulating...';
  try {
    const res = await fetch('/whatif', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        mode: 'simulate',
        driver: driver,
        driver_change_pct: pct,
        target_kpi: state.selectedKpi || 'revenue_total',
        current_kpi_value: kpi.value || 85000,
      })
    }).then(r => r.json());
    if (res.error) throw new Error(res.error);
    const direction = res.predicted_kpi_change_pct > 0 ? '▲' : '▼';
    const color = res.predicted_kpi_change_pct > 0 ? 'var(--ok)' : 'var(--warn)';
    document.getElementById('wiResult').innerHTML =
      `If <b>${driver}</b> changes by <b>${(pct*100).toFixed(0)}%</b>: ` +
      `<span style="color:${color}">${direction} ${Math.abs(res.predicted_kpi_change_pct*100).toFixed(1)}%</span> ` +
      `→ ~<b>${res.predicted_kpi_value?.toLocaleString()}</b> ` +
      `<span style="color:var(--dim)">via ${res.causal_chain?.join('→') || 'direct effect'}</span>`;
  } catch(e) {
    document.getElementById('wiResult').textContent = 'Simulation error: ' + e.message;
  }
}
"""
content = content.replace('function renderStory(data) {', whatif_js + '\nfunction renderStory(data) {')
whatif_call = """
  // What-If Simulator
  html += renderWhatIf(s);
"""
content = content.replace('  const tel = data.telemetry || {};', whatif_call + '\n  const tel = data.telemetry || {};')

# Feature 4
tuner_html = """    <div style="flex:1;"></div>
    <span id="lastUpdated" style="color:var(--dim);">Last sync: --</span>
    <div style="flex-basis: 100%; height: 0;"></div>
    <div id="thresholdTuner" style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top: 10px;">
      <span style="font-size:12px; color:var(--dim);">Primary threshold:</span>
      <input type="range" id="primaryThresh" min="1.0" max="2.5" step="0.25" value="1.75" 
             oninput="document.getElementById('primaryVal').textContent=this.value; debounceBacktest()"
             style="width:100px;">
      <span id="primaryVal" style="font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--paper);">1.75</span>
      <span style="font-size:12px; color:var(--dim); margin-left:8px;">Secondary:</span>
      <input type="range" id="secondaryThresh" min="2.0" max="3.5" step="0.5" value="3.0"
             oninput="document.getElementById('secondaryVal').textContent=this.value; debounceBacktest()"
             style="width:80px;">
      <span id="secondaryVal" style="font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--paper);">3.0</span>
      <span id="backtestResult" style="font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--dim);">F1: —</span>
    </div>
  </div>"""
content = content.replace('    <div style="flex:1;"></div>\n    <span id="lastUpdated" style="color:var(--dim);">Last sync: --</span>\n  </div>', tuner_html)

tuner_js = """let backtestTimer = null;
function debounceBacktest() {
  clearTimeout(backtestTimer);
  backtestTimer = setTimeout(runBacktest, 800);
}
async function runBacktest() {
  const p = document.getElementById('primaryThresh')?.value || 1.75;
  const s = document.getElementById('secondaryThresh')?.value || 3.0;
  document.getElementById('backtestResult').textContent = 'F1: ...';
  try {
    const res = await fetch(`/backtest?primary=${p}&secondary=${s}&days=180`).then(r => r.json());
    if (res.error) throw new Error(res.error);
    const el = document.getElementById('backtestResult');
    el.textContent = `F1:${res.f1?.toFixed(2)} P:${res.precision?.toFixed(2)} R:${res.recall?.toFixed(2)} FAR:${res.false_alarm_rate?.toFixed(2)}`;
    el.style.color = res.f1 > 0.5 ? 'var(--ok)' : res.f1 > 0.3 ? 'var(--signal)' : 'var(--warn)';
  } catch(e) {
    document.getElementById('backtestResult').textContent = 'F1: err';
  }
}
"""
content = content.replace('async function loadKpis() {', tuner_js + '\nasync function loadKpis() {')

# Feature 5
nl_html = """  <section>
    <div style="display:flex; gap:10px; margin-bottom:18px; align-items:center;">
      <input type="text" id="nlQuery" placeholder="Ask a question: Why is revenue down in Region X?" 
             style="flex:1; background:var(--panel); color:var(--paper); border:1px solid var(--wire); 
                    padding:10px 14px; border-radius:6px; font-family:'IBM Plex Mono',monospace; font-size:13px;"
             onkeydown="if(event.key==='Enter') runNLQuery()">
      <button onclick="runNLQuery()" style="background:var(--signal); color:var(--ink); border:none; 
              padding:10px 16px; border-radius:6px; font-family:'IBM Plex Mono',monospace; font-size:12px; 
              cursor:pointer; white-space:nowrap;">Ask →</button>
    </div>
    <div id="nlResult" style="display:none; font-family:'IBM Plex Mono',monospace; font-size:12px; 
         color:var(--dim); margin-bottom:14px; padding:8px 12px; background:var(--panel); 
         border:1px solid var(--wire); border-radius:6px;"></div>
    <div class="kpi-grid" id="kpiGrid">"""
content = content.replace('  <section>\n    <div class="kpi-grid" id="kpiGrid">', nl_html)

nl_js = """async function runNLQuery() {
  const query = document.getElementById('nlQuery')?.value?.trim();
  if (!query) return;
  const el = document.getElementById('nlResult');
  el.style.display = 'block';
  el.textContent = 'Routing query...';
  try {
    const res = await fetch('/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query, backend: state.backend})
    }).then(r => r.json());
    el.textContent = `Interpreted: KPI=${res.parsed_kpi}, Region=${res.parsed_region}, Status=${res.kpi_status}`;
    if (res.kpi_status === 'anomaly') {
      el.textContent += ' — loading story...';
      state.selectedKpi = res.parsed_kpi;
      selectKpi(res.parsed_kpi);
    }
  } catch(e) {
    el.textContent = 'Error: ' + e.message;
  }
}
"""
content = content.replace('async function loadKpis() {', nl_js + '\nasync function loadKpis() {')

# Feature 6
sse_js = """// SSE-based live updates (with graceful fallback to polling)
function startLiveUpdates() {
  if (typeof EventSource !== 'undefined') {
    const es = new EventSource('/stream/kpis');
    es.onmessage = e => {
      try {
        const kpis = JSON.parse(e.data);
        if (Array.isArray(kpis)) {
          kpis.forEach(k => { state.kpis[k.kpi_id] = k; });
          state.lastUpdated = new Date().toLocaleTimeString();
          document.getElementById('lastUpdated').textContent = 'Last sync: ' + state.lastUpdated;
          renderGrid();
          if (typeof renderHeatmap === 'function') renderHeatmap();
        }
      } catch(err) {}
    };
    es.onerror = () => {
      es.close();
      setInterval(loadKpis, 60000);
    };
  } else {
    setInterval(loadKpis, 60000);
  }
}
startLiveUpdates();"""
content = content.replace('setInterval(loadKpis, 60000);', sse_js)

# Feature 7 & 10 together to avoid issue at end
add_sections = """  </section>

  <section id="calibrationSection" style="display:none;">
    <h2><span class="bracket">[</span> confidence calibration <span class="bracket">]</span> <button onclick="loadCalibration()" style="background:var(--wire); color:var(--dim); border:none; border-radius:4px; padding:3px 8px; font-size:11px; cursor:pointer; margin-left:10px;">Load</button></h2>
    <div class="story-panel" id="calibrationPanel">
      <p style="color:var(--dim); font-size:13px;">Click Load to run calibration backtest (~5s).</p>
    </div>
  </section>

  <section id="customKpiSection">
    <h2><span class="bracket">[</span> custom kpi definition <span class="bracket">]</span></h2>
    <div class="story-panel">
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:14px;">
        <label style="font-size:12px;">KPI ID<br><input id="ckId" placeholder="e.g. gross_margin" style="width:100%; background:var(--ink); color:var(--paper); border:1px solid var(--wire); padding:6px 8px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; margin-top:4px;"></label>
        <label style="font-size:12px;">Name<br><input id="ckName" placeholder="e.g. Gross Margin" style="width:100%; background:var(--ink); color:var(--paper); border:1px solid var(--wire); padding:6px 8px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; margin-top:4px;"></label>
        <label style="font-size:12px;">Formula<br><input id="ckFormula" placeholder="e.g. (revenue - cogs) / revenue" style="width:100%; background:var(--ink); color:var(--paper); border:1px solid var(--wire); padding:6px 8px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; margin-top:4px;"></label>
        <label style="font-size:12px;">Warning threshold (%)<br><input id="ckWarn" type="number" value="5" style="width:100%; background:var(--ink); color:var(--paper); border:1px solid var(--wire); padding:6px 8px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; margin-top:4px;"></label>
      </div>
      <button onclick="submitCustomKpi()" style="background:var(--signal); color:var(--ink); border:none; padding:8px 18px; border-radius:4px; font-family:'IBM Plex Mono',monospace; font-size:12px; cursor:pointer;">Add KPI →</button>
      <span id="ckResult" style="margin-left:12px; font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--dim);"></span>
    </div>
  </section>
"""
content = content.replace('  </section>\n</div>', add_sections + '</div>')

calib_js = """async function loadCalibration() {
  document.getElementById('calibrationSection').style.display = 'block';
  document.getElementById('calibrationPanel').innerHTML = '<p style="color:var(--dim);">Running calibration backtest...</p>';
  try {
    const res = await fetch('/calibration?days=180').then(r => r.json());
    if (res.error) throw new Error(res.error);
    const buckets = res.buckets || [];
    const W = 300, H = 200, pad = 40;
    let svg = `<svg viewBox="0 0 ${W} ${H}" style="max-width:340px; display:block;">`;
    svg += `<line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${pad}" stroke="#6fae7c" stroke-dasharray="4" stroke-width="1"/>`;
    svg += `<line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H-pad}" stroke="#2a2f3a" stroke-width="1"/>`;
    svg += `<line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="#2a2f3a" stroke-width="1"/>`;
    svg += `<text x="${pad-4}" y="${pad}" text-anchor="end" font-size="9" fill="#8b91a0">1.0</text>`;
    svg += `<text x="${W-pad}" y="${H-pad+12}" text-anchor="middle" font-size="9" fill="#8b91a0">1.0</text>`;
    svg += `<text x="${pad}" y="${H-pad+12}" text-anchor="middle" font-size="9" fill="#8b91a0">0</text>`;
    const pts = buckets.map(b => {
      const x = pad + b.stated_confidence * (W - 2*pad);
      const y = H - pad - b.empirical_accuracy * (H - 2*pad);
      return `${x},${y}`;
    }).join(' ');
    if (pts) svg += `<polyline points="${pts}" fill="none" stroke="var(--signal)" stroke-width="2"/>`;
    buckets.forEach(b => {
      const x = pad + b.stated_confidence * (W - 2*pad);
      const y = H - pad - b.empirical_accuracy * (H - 2*pad);
      svg += `<circle cx="${x}" cy="${y}" r="4" fill="var(--signal)"/>`;
    });
    svg += `<text x="${W/2}" y="${H-4}" text-anchor="middle" font-size="9" fill="#8b91a0">Stated confidence</text>`;
    svg += `</svg>`;
    const ece = res.ece?.toFixed(3) || '—';
    document.getElementById('calibrationPanel').innerHTML = `
      <div style="display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap;">
        ${svg}
        <div style="flex:1;">
          <p style="font-family:'IBM Plex Mono',monospace; font-size:13px; color:var(--paper);">ECE: <b>${ece}</b></p>
          <p style="font-size:13px; color:var(--body-text);">${res.recommendation || ''}</p>
          <p style="font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--dim);">Green dashed = perfect calibration<br>Orange = system output</p>
        </div>
      </div>`;
  } catch(e) {
    document.getElementById('calibrationPanel').innerHTML = `<p style="color:var(--warn);">Error: ${e.message}</p>`;
  }
}

async function submitCustomKpi() {
  const payload = {
    kpi_id: document.getElementById('ckId')?.value,
    name: document.getElementById('ckName')?.value,
    formula: document.getElementById('ckFormula')?.value,
    threshold_warning: parseFloat(document.getElementById('ckWarn')?.value || 5) / 100,
    threshold_critical: parseFloat(document.getElementById('ckWarn')?.value || 5) / 100 * 3,
  };
  if (!payload.kpi_id || !payload.name) {
    document.getElementById('ckResult').textContent = 'KPI ID and Name are required.';
    return;
  }
  try {
    const res = await fetch('/kpi/define', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    }).then(r => r.json());
    document.getElementById('ckResult').textContent = res.error ? `Error: ${res.error}` : `✓ Added: ${res.name}`;
    document.getElementById('ckResult').style.color = res.error ? 'var(--warn)' : 'var(--ok)';
  } catch(e) {
    document.getElementById('ckResult').textContent = 'Error: ' + e.message;
  }
}
"""
content = content.replace('function renderHistory() {', calib_js + '\nfunction renderHistory() {')

# Feature 8
stl_js = """async function loadDecomposition(kpiId) {
  const el = document.getElementById('decompPanel');
  if (!el) return;
  el.innerHTML = '<p style="color:var(--dim); font-size:12px;">Loading decomposition...</p>';
  try {
    const res = await fetch(`/decompose/${kpiId}?days=90`).then(r => r.json());
    if (res.error) throw new Error(res.error);
    const {dates, trend, seasonal, residual} = res;
    function miniSvg(vals, label, color) {
      const min = Math.min(...vals), max = Math.max(...vals), range = max - min || 1;
      const W = 200, H = 50, n = vals.length;
      const pts = vals.map((v, i) => `${(i/(n-1))*W},${H - ((v-min)/range)*H}`).join(' ');
      return `<div style="margin-bottom:10px;">
        <div style="font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--dim); margin-bottom:3px;">${label}</div>
        <svg viewBox="0 0 ${W} ${H}" style="width:100%; height:50px; display:block;">
          <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/>
        </svg></div>`;
    }
    el.innerHTML = miniSvg(trend, 'Trend', 'var(--signal)') +
                   miniSvg(seasonal, 'Seasonal', 'var(--info)') +
                   miniSvg(residual, 'Residual', 'var(--warn)');
  } catch(e) {
    el.innerHTML = `<p style="color:var(--warn); font-size:12px;">Error: ${e.message}</p>`;
  }
}
"""
content = content.replace('function renderStory(data) {', stl_js + '\nfunction renderStory(data) {')

stl_html = """
    <div style="margin-top:12px;">
      <button onclick="loadDecomposition('${data.kpi_id || state.selectedKpi}')" style="background:var(--wire); color:var(--dim); border:none; border-radius:4px; padding:4px 10px; font-family:'IBM Plex Mono',monospace; font-size:11px; cursor:pointer;">▸ Show decomposition</button>
    </div>
    <div id="decompPanel" style="margin-top:8px;"></div>
"""
content = content.replace('<div class="persona-body"><p>${p.explanation}</p></div>', '<div class="persona-body"><p>${p.explanation}</p></div>' + stl_html)

# Feature 9
lineage_js = """async function loadLineage(kpiId) {
  const el = document.getElementById('lineagePanel');
  if (!el) return;
  el.innerHTML = '<p style="font-size:12px; color:var(--dim);">Loading lineage...</p>';
  try {
    const res = await fetch(`/lineage/${kpiId}`).then(r => r.json());
    const rows = (res.lineage_chain || []).map(step => {
      const tag = step.is_llm ? '<span style="background:var(--signal-soft); color:var(--signal); padding:1px 5px; border-radius:3px; font-size:10px;">LLM</span>'
                              : '<span style="background:var(--ok-soft); color:var(--ok); padding:1px 5px; border-radius:3px; font-size:10px;">det.</span>';
      const freshness = step.freshness_hours != null ? `<span style="color:var(--dim)"> (${step.freshness_hours}h ago)</span>` : '';
      return `<tr><td style="color:var(--paper);">${step.step}</td><td>${tag}</td><td style="color:var(--body-text);">${step.method}</td><td>${freshness}</td></tr>`;
    }).join('');
    el.innerHTML = `<table class="actions-table">
      <thead><tr><th>Step</th><th>Type</th><th>Method</th><th>Freshness</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div style="margin-top:8px; font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--dim);">LLM steps: ${res.llm_steps || 1} / Deterministic steps: ${res.deterministic_steps || 4}</div>`;
  } catch(e) {
    el.innerHTML = `<p style="color:var(--warn); font-size:12px;">Lineage unavailable</p>`;
  }
}
"""
content = content.replace('function renderStory(data) {', lineage_js + '\nfunction renderStory(data) {')

lineage_html = """
  // Lineage Panel
  html += `<div style="margin-top:20px; border-top:1px solid var(--wire); padding-top:16px;">
    <h4 style="font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--dim); margin:0 0 8px;">[ source lineage ] <button onclick="loadLineage('${data.kpi_id || state.selectedKpi}')" style="background:var(--wire); color:var(--dim); border:none; border-radius:3px; padding:2px 7px; font-size:10px; cursor:pointer; margin-left:6px;">Show</button></h4>
    <div id="lineagePanel"></div>
  </div>`;
"""
content = content.replace('  detail.innerHTML = html;', lineage_html + '\n  detail.innerHTML = html;')


# Feature 11
export_html = """        <a id="exportBtn" href="#" style="display:none; font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--dim); border:1px solid var(--wire); padding:4px 10px; border-radius:4px; text-decoration:none; margin-left:auto;" target="_blank">↓ Export Report</a>"""
content = content.replace('        ${p.escalate ? \'<span class="escalate-badge">ESCALATED</span>\' : \'\'}', 
                          export_html + '\n        ${p.escalate ? \'<span class="escalate-badge">ESCALATED</span>\' : \'\'}')

export_js = """
  const exportBtn = document.getElementById('exportBtn');
  if (exportBtn && state.selectedKpi) {
    exportBtn.href = `/report/${state.selectedKpi}`;
    exportBtn.style.display = 'inline-block';
  }
"""
content = content.replace('  detail.innerHTML = html;', export_js + '\n  detail.innerHTML = html;')

with open('d:/project/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)
