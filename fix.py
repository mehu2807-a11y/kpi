import os
import re

html_path = r'f:\Bussiness\templates\dashboard.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

overview_tab_html = """
      <div id="tab-overview" class="tab-pane" style="display:none;">
        <div class="card">
          <h2 class="sec-title">Data Processing Workflow</h2>
          <p style="margin-top: 10px; color: var(--text2);">The processes through which the input data goes through are strictly defined in steps:</p>
          <ul style="margin-left: 20px; margin-top: 10px; color: var(--text2); line-height: 1.8;">
            <li><strong>Step 1: Data Ingestion (task1)</strong> - Raw data is securely fetched from source systems and ingested into the staging area.</li>
            <li><strong>Step 2: Validation & Cleansing</strong> - Missing values are handled and structural integrity is checked.</li>
            <li><strong>Step 3: KPI Engine Processing</strong> - Data is passed through anomaly detection algorithms.</li>
            <li><strong>Step 4: LLM Synthesizer</strong> - Detected anomalies are packaged and sent to the LLM backend for root cause analysis.</li>
            <li><strong>Step 5: Dashboard Rendering</strong> - Synthesized insights are displayed in this secure BI portal.</li>
          </ul>
        </div>
      </div>
"""

insights_tab_html = """
      <div id="tab-insights" class="tab-pane" style="display:none;">
        <div class="card" style="margin-bottom: 24px;">
          <h2 class="sec-title" style="margin-bottom: 14px;">Sector News</h2>
          <div id="news-domain">Loading news...</div>
        </div>
        <div class="card" style="margin-bottom: 24px;">
          <h2 class="sec-title" style="margin-bottom: 14px;">Company News</h2>
          <div id="news-company">Loading news...</div>
        </div>
        <div class="card" style="margin-bottom: 24px;">
          <h2 class="sec-title" style="margin-bottom: 14px;">Macroeconomic News</h2>
          <div id="news-macro">Loading news...</div>
        </div>
      </div>
"""

old_wrap_start = '<div class="wrap">\n<div id="inputView">'
new_wrap_start = '<div class="wrap">\n' + overview_tab_html + insights_tab_html + '\n      <div id="tab-health" class="tab-pane active">\n<div id="inputView">'
html = html.replace(old_wrap_start, new_wrap_start)

old_add_metric = """        </div>
          <div class="sec">
          <div class="sec-hdr">
            <h2 class="sec-title">Add Your Own Metric to Monitor</h2>"""

new_add_metric = """        </div>
      </div> <!-- End tab-health -->
      
      <div id="tab-analysis" class="tab-pane" style="display:none;">
          <div class="sec">
          <div class="sec-hdr">
            <h2 class="sec-title">Add Your Own Metric to Monitor</h2>"""

html = html.replace(old_add_metric, new_add_metric)

old_tail = """            </div>
        
    </div>
  </div>
</div>"""

new_tail = """            </div>
        
    </div>
  </div>
      </div> <!-- End tab-analysis -->
</div>"""

html = html.replace(old_tail, new_tail)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

print('Dashboard HTML tabs refactored!')
