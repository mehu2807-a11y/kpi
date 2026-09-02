"""
Gemini LLM Client for BusinessIntelligence.ai
Uses Google's Gemini API (generateContent REST endpoint -- no SDK dependency).
"""

from __future__ import annotations
import json
import os
from typing import Optional
import requests


class GeminiLLMClient:
    """
    Gemini implementation of the LLMClient protocol (see llm_client.py).

    Google retires specific Gemini model versions on the order of months,
    not years, so this defaults to "gemini-flash-latest" -- a rolling alias
    Google maintains that always points at their current recommended Flash
    model -- specifically to avoid hardcoding a pinned version that later
    gets shut down. Override via the `model` constructor arg or the
    GEMINI_MODEL env var if you want a specific pinned version instead.
    Current models: https://ai.google.dev/gemini-api/docs/models
    """

    def __init__(self, model: str = None, api_key: Optional[str] = None, timeout: float = 120):
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("A Gemini API key must be set (GEMINI_API_KEY env var, or passed in).")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.timeout = timeout

    def complete_json(self, system: str, user: str) -> dict:
        """Call the Gemini API and parse the JSON response."""
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {
                "response_mime_type": "application/json",  # Requests JSON-only output
                "temperature": 0.1,  # Low temp for consistent, structured outputs
            },
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"

        try:
            response = requests.post(url, params={"key": self.api_key}, json=payload, timeout=25)
        except requests.exceptions.Timeout as e:
            raise RuntimeError(f"Gemini didn't respond within {self.timeout:.0f}s. Original error: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Gemini API request failed: {e}")

        if response.status_code in (400, 403):
            raise RuntimeError(
                f"Gemini rejected the request (HTTP {response.status_code}) -- usually an invalid "
                f"API key or model name ({self.model!r}). Response: {response.text[:500]}"
            )
        if response.status_code == 404:
            raise RuntimeError(
                f"Gemini says the model {self.model!r} doesn't exist (HTTP 404). Check "
                f"https://ai.google.dev/gemini-api/docs/models for current model names."
            )
        if response.status_code == 429:
            raise RuntimeError(
                "Gemini rate-limited or quota-exhausted this request (HTTP 429). Check your "
                "usage at https://aistudio.google.com."
            )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            raise RuntimeError(f"Gemini API error (HTTP {response.status_code}): {response.text[:500]}")

        result = response.json()
        try:
            generated_text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            return json.loads(generated_text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse Gemini response: {e}\nResponse: {result}")
