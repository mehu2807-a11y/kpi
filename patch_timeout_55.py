import os
import glob

for py_file in glob.glob(r'f:\Bussiness\task6\*_llm.py'):
    with open(py_file, 'r', encoding='utf-8') as f:
        code = f.read()
    
    code = code.replace("timeout=25", "timeout=55")
    code = code.replace("within 25s", "within 55s")
    
    with open(py_file, 'w', encoding='utf-8') as f:
        f.write(code)
