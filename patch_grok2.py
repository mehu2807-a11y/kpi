import os

path = r'f:\Bussiness\task6\grok_llm.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

# Remove response_format
code = code.replace(',\n            "response_format": {"type": "json_object"}  # Important: requests JSON output', '')
code = code.replace(',\n            "response_format": {"type": "json_object"}', '')
code = code.replace(', "response_format": {"type": "json_object"}', '')

# Replace json.loads with a version that strips markdown
old_parse = 'return json.loads(generated_text)'
new_parse = """
            # Strip markdown fences if present
            clean_text = generated_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            
            return json.loads(clean_text.strip())
"""
code = code.replace(old_parse, new_parse.strip())

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
