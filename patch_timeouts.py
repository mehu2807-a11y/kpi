import os
import glob

for py_file in glob.glob(r'f:\Bussiness\task6\*_llm.py'):
    with open(py_file, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Replace any generic timeout kwargs
    code = code.replace("timeout=self.timeout", "timeout=25")
    code = code.replace("timeout=120", "timeout=25")
    code = code.replace("timeout=300", "timeout=25")
    code = code.replace("timeout=90", "timeout=25")
    code = code.replace("timeout=30", "timeout=25")
    
    with open(py_file, 'w', encoding='utf-8') as f:
        f.write(code)
