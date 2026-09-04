import re
import codecs

with codecs.open('templates/dashboard.html', 'r', 'utf-8') as f:
    content = f.read()

# 1. Inject runAnalyzeJob
helper = '''const CLIENT_POLL_GIVEUP_MS = 3 * 60 * 1000;
async function runAnalyzeJob(payload) {
  const postRes = await fetch('/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
  if (!postRes.ok) throw new Error("Server error: " + postRes.status);
  const postData = await postRes.json();
  if (postData.error) throw new Error(postData.error);
  if (!postData.job_id) return postData;
  const jobId = postData.job_id;
  const startTime = Date.now();
  while (true) {
    await new Promise(r => setTimeout(r, 2000));
    if (Date.now() - startTime > CLIENT_POLL_GIVEUP_MS) throw new Error("Analysis timed out after 3 minutes. The AI is too slow.");
    const statusRes = await fetch('/analyze/status/' + jobId);
    if (!statusRes.ok) throw new Error("Status check failed");
    const statusData = await statusRes.json();
    if (statusData.status === 'error') throw new Error(statusData.error || "Unknown error during analysis");
    if (statusData.status === 'done') return statusData.result;
  }
}
'''

content = content.replace(
    "const state={kpis:{},kpiHistory:{},selectedKpi:null,activeRole:'EXECUTIVE',backend:'ollama',apiKey:'',lastStory:null,feedbackHistory:[],earlyWarnings:[],lastUpdated:null};",
    "const state={kpis:{},kpiHistory:{},selectedKpi:null,activeRole:'EXECUTIVE',backend:'ollama',apiKey:'',lastStory:null,feedbackHistory:[],earlyWarnings:[],lastUpdated:null};\n\n" + helper
)

# 2. Patch selectKpi
content = content.replace(
    "const data=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());",
    "const data=await runAnalyzeJob(payload);"
)

# 3. Patch magic timer
magic_old = """const storyRes=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(apl)});
      if (!storyRes.ok) {
          const errText = await storyRes.text();
          throw new Error("Server error: " + storyRes.status + " " + errText.substring(0, 100));
      }
      const story=await storyRes.json();"""

content = content.replace(magic_old, "const story=await runAnalyzeJob(apl);")

# fallback regex if spacing is weird
content = re.sub(
    r"const storyRes=await fetch\('/analyze'.*?const story=await storyRes\.json\(\);",
    "const story=await runAnalyzeJob(apl);",
    content, flags=re.DOTALL
)

with codecs.open('templates/dashboard.html', 'w', 'utf-8') as f:
    f.write(content)
print("dashboard.html patched!")
