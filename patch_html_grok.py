import os

path = r'f:\Bussiness\templates\dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Update the default grok model
html = html.replace("'grok': 'grok-beta'", "'grok': 'grok-2-latest'")

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
