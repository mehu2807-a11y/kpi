import os

path = r'f:\Bussiness\templates\dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Make absolutely sure all defaults are correct and stable
html = html.replace("'ollama': 'llama3.2'", "'ollama': 'llama3.1'")
html = html.replace("'ollama': 'llama3:8b'", "'ollama': 'llama3.1'")
html = html.replace("'gemini': 'gemini-1.5-flash'", "'gemini': 'gemini-1.5-pro'")
html = html.replace("'gemini': 'gemini-3.7-flash'", "'gemini': 'gemini-1.5-pro'")
html = html.replace("'openai': 'gpt-4o'", "'openai': 'gpt-4o'")
html = html.replace("'grok': 'grok-4.6'", "'grok': 'grok-2-1212'")

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
