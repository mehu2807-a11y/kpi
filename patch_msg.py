import os

path = r'f:\Bussiness\task6\gemini_llm.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace("within {self.timeout:.0f}s", "within 25s")

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
