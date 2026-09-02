"""
Ollama LLM Client for BusinessIntelligence.ai
Uses local Ollama instance with OpenAI-compatible interface.
"""

from __future__ import annotations
import json
import os
from typing import Optional
import requests

from schemas import AnomalyEvent, CorrelationResult, RetrievedEvidence
from llm_client import SYSTEM_PROMPT, build_user_prompt


class OllamaLLMClient:
    """
    Ollama implementation of LLMClient protocol.
    Uses Ollama's HTTP API to communicate with local models.
    """

    def __init__(self, model: str = None, base_url: str = None, timeout: float = None):
        # Falls back to env vars so you can point at a different model/host
        # (e.g. a remote Ollama server) without touching code.
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3:8b")
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        # 60s was too short for CPU-only local inference, where an 8B model
        # can easily take 1-3+ minutes for a full response, especially on
        # the first call while the model loads into memory. Override with
        # OLLAMA_TIMEOUT (seconds) if you need even longer.
        self.timeout = timeout or float(os.environ.get("OLLAMA_TIMEOUT", "300"))

    def complete_json(self, system: str, user: str) -> dict:
        """Call Ollama API and parse JSON response."""
        # Ollama uses a slightly different API format
        payload = {
            "model": self.model,
            "prompt": f"{system}\n\n{user}",
            "stream": False,
            "format": "json",  # Important: requests JSON output
            "options": {
                "temperature": 0.1,  # Low temp for consistent outputs
                "top_p": 0.9
            }
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=55
            )
            response.raise_for_status()
            
            # Ollama returns JSON with a "response" field containing the generated text
            result = response.json()
            generated_text = result.get("response", "").strip()
            
            # Parse the JSON from the generated text
            # Remove any potential markdown formatting
            if generated_text.startswith("`json"):
                generated_text = generated_text[7:]
            if generated_text.endswith("`"):
                generated_text = generated_text[:-3]
            
            return json.loads(generated_text.strip())
            
        except requests.exceptions.Timeout as e:
            raise RuntimeError(
                f"Ollama didn't respond within {self.timeout:.0f}s for model {self.model!r}. "
                f"This usually just means the model is slow on your hardware (common for "
                f"CPU-only inference) rather than something being broken. Try: waiting it out "
                f"with a longer OLLAMA_TIMEOUT env var, or switching to a smaller model like "
                f"'llama3.2:3b' or 'phi3' (pull it with `ollama pull <name>` first). "
                f"Original error: {e}"
            )
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Couldn't reach Ollama at {self.base_url}. Is it running? "
                f"Start it with `ollama serve` (or open the Ollama app), and make sure "
                f"you've pulled the model with `ollama pull {self.model}`. Original error: {e}"
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API request failed: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse JSON from Ollama response: {e}\nResponse: {generated_text}")
