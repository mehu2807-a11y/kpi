import os

path = r'f:\Bussiness\templates\dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace("'openai': 'gpt-5.6-luna'", "'openai': 'gpt-4o'")
html = html.replace("gpt-5.6-luna", "gpt-4o")

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
