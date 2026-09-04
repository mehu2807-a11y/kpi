import re
import codecs

with codecs.open('templates/dashboard.html', 'r', 'utf-8') as f:
    content = f.read()

# 1. Update runAnalyzeJob to runAsyncJob(url, payload)
content = content.replace(
    'async function runAnalyzeJob(payload) {',
    'async function runAsyncJob(url, payload) {'
).replace(
    "const postRes = await fetch('/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});",
    "const postRes = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});"
).replace(
    "const statusRes = await fetch('/analyze/status/' + jobId);",
    "const statusRes = await fetch(url + '/status/' + jobId);"
)

# 2. Update existing callers of runAnalyzeJob
content = content.replace('runAnalyzeJob(payload)', "runAsyncJob('/analyze', payload)")
content = content.replace('runAnalyzeJob(apl)', "runAsyncJob('/analyze', apl)")

# 3. Update the /format_input call
magic_old = """const fmtRes=await fetch('/format_input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pl)});
      if (!fmtRes.ok) {
          const errText = await fmtRes.text();
          throw new Error("Server error: " + fmtRes.status + " " + errText.substring(0, 100));
      }
      const fmt=await fmtRes.json();"""

magic_new = """const fmt = await runAsyncJob('/format_input', pl);"""
content = content.replace(magic_old, magic_new)

with codecs.open('templates/dashboard.html', 'w', 'utf-8') as f:
    f.write(content)
print("dashboard.html patched for async format_input!")
