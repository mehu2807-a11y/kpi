import re
import codecs

with codecs.open('templates/dashboard.html', 'r', 'utf-8') as f:
    content = f.read()

# Replace the throw new Error("Status check failed") with better error logging
content = content.replace(
    'if (!statusRes.ok) throw new Error("Status check failed");',
    'if (!statusRes.ok) { const text = await statusRes.text(); throw new Error(`Status check failed: ${statusRes.status} ${text.substring(0, 100)}`); }'
)

# And while we are here, let's bump the timeout from 3 minutes to 6 minutes, just in case 
# the AI takes very long to do the 4 persona passes.
content = content.replace(
    'const CLIENT_POLL_GIVEUP_MS = 3 * 60 * 1000;',
    'const CLIENT_POLL_GIVEUP_MS = 6 * 60 * 1000;'
)
content = content.replace(
    'throw new Error("Analysis timed out after 3 minutes. The AI is too slow.");',
    'throw new Error("Analysis timed out after 6 minutes. The AI is too slow.");'
)

with codecs.open('templates/dashboard.html', 'w', 'utf-8') as f:
    f.write(content)
print("dashboard.html patched for better errors!")
