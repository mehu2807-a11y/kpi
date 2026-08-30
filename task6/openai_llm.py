"""
OpenAI LLM Client for BusinessIntelligence.ai
Uses OpenAI's Chat Completions API (requests-based -- no SDK dependency).
"""

from __future__ import annotations
import json
import os
from typing import Optional
import requests


class OpenAILLMClient:
    """
    OpenAI implementation of the LLMClient protocol (see llm_client.py).

    Model IDs move fast at OpenAI -- "gpt-5.4-mini" is a reasonable,
    cost-effective default as of mid-2026, but confirm the current
    recommended model at https://platform.openai.com/docs/models before
    deploying, and override here via the `model` constructor arg or the
    OPENAI_MODEL env var.
    """

    def __init__(self, model: str = None, api_key: Optional[str] = None, timeout: float = 120):
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("An OpenAI API key must be set (OPENAI_API_KEY env var, or passed in).")
        self.base_url = "https://api.openai.com/v1"
        self.timeout = timeout

    def complete_json(self, system: str, user: str) -> dict:
        """Call the OpenAI API and parse the JSON response."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,  # Low temp for consistent, structured outputs
            "response_format": {"type": "json_object"},  # Requests JSON-only output
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as e:
            raise RuntimeError(f"OpenAI didn't respond within {self.timeout:.0f}s. Original error: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"OpenAI API request failed: {e}")

        if response.status_code == 401:
            raise RuntimeError(
                "OpenAI rejected the API key (HTTP 401). Double-check the key you entered -- "
                "it should start with 'sk-'."
            )
        if response.status_code == 404:
            raise RuntimeError(
                f"OpenAI says the model {self.model!r} doesn't exist (HTTP 404). Check "
                f"https://platform.openai.com/docs/models for current model names."
            )
        if response.status_code == 429:
            raise RuntimeError(
                "OpenAI rate-limited or quota-exhausted this request (HTTP 429). Check your "
                "usage/billing at https://platform.openai.com/usage."
            )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise RuntimeError(f"OpenAI API error (HTTP {response.status_code}): {response.text[:500]}")

        result = response.json()
        try:
            generated_text = result["choices"][0]["message"]["content"].strip()
            return json.loads(generated_text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse OpenAI response: {e}\nResponse: {result}")
