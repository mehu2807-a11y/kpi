import os

path = r'f:\Bussiness\templates\dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace("'ollama': 'llama3:8b'", "'ollama': 'llama3.2'")
html = html.replace("'gemini': 'gemini-1.5-flash'", "'gemini': 'gemini-3.7-flash'")
html = html.replace("'openai': 'gpt-4o-mini'", "'openai': 'gpt-5.6-luna'")

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
