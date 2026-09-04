import os

path = r'f:\Bussiness\templates\dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Update the default grok model
html = html.replace("'grok': 'grok-2-latest'", "'grok': 'grok-4.6'")

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
