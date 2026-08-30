"""
Grok LLM Client for BusinessIntelligence.ai
Uses xAI's Grok API with OpenAI-compatible interface.
"""

from __future__ import annotations
import json
import os
from typing import Optional
import requests

from schemas import AnomalyEvent, CorrelationResult, RetrievedEvidence
from llm_client import SYSTEM_PROMPT, build_user_prompt


class GrokLLMClient:
    """
    Grok implementation of LLMClient protocol.
    Uses xAI's Grok API (OpenAI-compatible endpoint).
    """

    def __init__(self, model: str = "grok-beta", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("GROK_API_KEY")
        if not self.api_key:
            raise ValueError("GROK_API_KEY must be set in environment or passed to constructor")
        self.base_url = "https://api.x.ai/v1"

    def complete_json(self, system: str, user: str) -> dict:
        """Call Grok API and parse JSON response."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": 0.1,  # Low temp for consistent outputs
            "response_format": {"type": "json_object"}  # Important: requests JSON output
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            generated_text = result["choices"][0]["message"]["content"].strip()

            # Parse the JSON from the generated text
            return json.loads(generated_text)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Grok API request failed: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse Grok response: {e}\nResponse: {generated_text}")
