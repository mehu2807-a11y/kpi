import os

path = r'f:\Bussiness\task6\grok_llm.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Replace raise RuntimeError with one that includes response.text if available
old = "except requests.exceptions.RequestException as e:\n            raise RuntimeError(f\"Grok API request failed: {e}\")"
new = """except requests.exceptions.RequestException as e:
            msg = f"Grok API request failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f" | Details: {e.response.text}"
            raise RuntimeError(msg)"""
code = code.replace(old, new)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
