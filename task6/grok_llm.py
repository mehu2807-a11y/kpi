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
from retry_utils import request_with_retry


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
            "temperature": 0.1  # Low temp for consistent outputs
        }

        try:
            # Retries transient errors (429 rate-limit, 500/502/503/504
            # overload or outage) with backoff before giving up. The whole
            # retry loop (all attempts + backoff) is capped at
            # LLM_RETRY_BUDGET_SECONDS wall-clock time so we fail fast with
            # a clean JSON error instead of running past a reverse-proxy's
            # own timeout and getting a generic HTML error page back.
            response = request_with_retry(
                lambda t: requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=t
                ),
                total_budget=float(os.environ.get("LLM_RETRY_BUDGET_SECONDS", 45)),
            )
            if response.status_code == 503:
                raise RuntimeError(
                    f"Grok's model {self.model!r} is overloaded (HTTP 503) and stayed "
                    "unavailable after several retries. This is on xAI's side -- wait a bit "
                    "and try again."
                )
            response.raise_for_status()

            result = response.json()
            generated_text = result["choices"][0]["message"]["content"].strip()

            # Parse the JSON from the generated text
            # Strip markdown fences if present
            clean_text = generated_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            
            return json.loads(clean_text.strip())

        except requests.exceptions.RequestException as e:
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
            raise RuntimeError(msg)
        except (KeyError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse Grok response: {e}\nResponse: {generated_text}")
        except TimeoutError as e:
            raise RuntimeError(f"Grok API call aborted: {e}")
