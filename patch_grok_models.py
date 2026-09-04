import os

path = r'f:\Bussiness\task6\grok_llm.py'
with open(path, 'r', encoding='utf-8') as f:
    code = f.read()

new_except = """except requests.exceptions.RequestException as e:
            msg = f"Grok API request failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f" | Details: {e.response.text}"
                if "Model not found" in e.response.text:
                    try:
                        r = requests.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"})
                        models = [m["id"] for m in r.json().get("data", [])]
                        msg += f" | VALID MODELS FOR YOUR KEY: {', '.join(models)}"
                    except:
                        pass
            raise RuntimeError(msg)"""

code = code.replace("""except requests.exceptions.RequestException as e:
            msg = f"Grok API request failed: {e}"
            if hasattr(e, 'response') and e.response is not None:
                msg += f" | Details: {e.response.text}"
            raise RuntimeError(msg)""", new_except)

with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
