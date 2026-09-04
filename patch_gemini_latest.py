import os

path = r'f:\Bussiness\templates\dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace("'gemini': 'gemini-1.5-flash'", "'gemini': 'gemini-3.7-flash'")

with open(path, 'w', encoding='utf-8') as f:
    f.write(html)
