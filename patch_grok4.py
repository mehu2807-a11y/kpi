import os

path = r'f:\Bussiness\task6\grok_llm.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "response_format" in line:
        continue
    # Ensure temperature doesn't end with a trailing comma since it's the last item now
    if "temperature" in line:
        line = line.replace(",", "")
    new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
