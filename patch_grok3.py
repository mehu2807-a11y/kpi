import os
import re

path = r'f:\Bussiness\task6\grok_llm.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Delete response_format line using regex
code = re.sub(r',\s*"response_format"\s*:\s*\{"type"\s*:\s*"json_object"\}\s*(?:#.*)?', '', code)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
