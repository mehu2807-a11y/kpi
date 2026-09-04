import os

path = r'f:\Bussiness\task6\grok_llm.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace("timeout=30", "timeout=90")

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
