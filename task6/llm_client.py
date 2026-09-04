"""
Prompt construction + the LLM call boundary for Task 6.

The synthesis prompt deliberately never asks the model for a confidence
number -- see scoring.py for why not. It asks for exactly three things:
a plain-language explanation, 2-3 ranked hypotheses (each grounded in
specific driver_id / source_id citations -- no bare assertions), and
next-step actions per hypothesis.

LLMClient is a tiny protocol so synthesize.py never has to know whether
it's talking to the real Anthropic API or a canned response. Swap
MockLLMClient for AnthropicLLMClient once you have an API key -- nothing
else in the pipeline changes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Protocol, Optional

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from schemas import AnomalyEvent, CorrelationResult, RetrievedEvidence


SYSTEM_PROMPT = """You are an analyst assistant inside an automated anomaly-explanation \
pipeline. You will be given one detected metric anomaly, a ranked list of structured \
statistical drivers, and a ranked list of retrieved evidence sources.

Your job:
1. Write a short, plain-language explanation of what changed (2-4 sentences, no jargon).
2. Propose 2-3 ranked root-cause hypotheses. EVERY hypothesis must cite at least one \
driver_id or source_id from the data you were given -- never state a cause with no \
citation attached. If two hypotheses share a cause, merge them.
3. For each hypothesis, propose 1-2 concrete next-step actions a human should take to \
confirm or act on it.

Hard rules:
- Do not invent drivers, sources, dates, or numbers that are not in the input.
- Do not include a confidence score or self-rating anywhere in your output -- confidence \
is computed downstream from your citations, not from your judgment.
- Cite structured drivers as "CorrelationResult.<driver_id>" and evidence sources as the \
bare source_id (e.g. "news_00231"), using only the ids given to you.
- Respond with a single JSON object and nothing else -- no markdown fences, no prose \
before or after it.

Respond in exactly this shape:
{
  "explanation": "string",
  "hypotheses": [
    {"cause": "string", "citations": ["string", ...], "actions": ["string", ...]}
  ]
}"""


def _format_drivers(correlation: CorrelationResult) -> str:
    lines = []
    for d in correlation.drivers:
        lines.append(
            f"- driver_id={d.driver_id!r} | {d.stat_type}={d.value:+.2f} | "
            f"rank={d.rank} | {d.label}"
        )
    return "\n".join(lines)


def _format_sources(evidence: RetrievedEvidence) -> str:
    lines = []
    for s in evidence.sources:
        lines.append(
            f"- source_id={s.source_id!r} | relevance={s.relevance_score:.2f} | "
            f"rank={s.rank} | publisher={s.publisher} | date={s.date}\n"
            f"  title: {s.title}\n"
            f"  snippet: {s.snippet}"
        )
    return "\n".join(lines)


def build_user_prompt(
    anomaly: AnomalyEvent,
    correlation: CorrelationResult,
    evidence: RetrievedEvidence,
) -> str:
    direction_word = "up" if anomaly.direction == "increase" else "down"
    return f"""ANOMALY
{anomaly.entity} {anomaly.metric_name} {direction_word} {abs(anomaly.magnitude_pct):.1f}% \
({anomaly.baseline_value:,.0f} -> {anomaly.observed_value:,.0f}), \
window {anomaly.window_start} to {anomaly.window_end}.

STRUCTURED DRIVERS (ranked, from CorrelationResult)
{_format_drivers(correlation)}

RETRIEVED EVIDENCE (ranked, from RetrievedEvidence)
{_format_sources(evidence)}

Produce the JSON object described in your instructions now."""


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


class MockLLMClient:
    """
    Returns one canned response regardless of input. Construct one per test
    case with that case's expected LLM output -- see demo.py and
    test_synthesize.py. This is what makes the whole pipeline runnable with
    no network access, per the brief's "day-one start" instruction.
    """

    def __init__(self, canned_response: dict):
        self._canned_response = canned_response

    def complete_json(self, system: str, user: str) -> dict:
        return self._canned_response


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence (``` or ```json)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


class AnthropicLLMClient:
    """
    Real implementation, backed by the Anthropic Messages API. Requires the
    `anthropic` package (see requirements.txt) and an ANTHROPIC_API_KEY in
    the environment. Not exercised in this sandbox -- no network egress
    here -- so wire it in and swap it for MockLLMClient in your own
    environment; nothing else in synthesize.py needs to change.

    Model IDs change over time -- "claude-sonnet-5" is current as of this
    writing and is a reasonable default for this task (grounded, structured
    reasoning over a moderate amount of context). Confirm the current
    recommended model at https://docs.claude.com/en/docs/about-claude/models/overview
    before deploying, and swap it here or via the `model` constructor arg.
    """

    def __init__(self, model: str = "claude-sonnet-5", max_tokens: int = 1500, api_key: Optional[str] = None):
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("An Anthropic API key must be set (ANTHROPIC_API_KEY env var, or passed in).")
        self._client = None  # lazy: only imports/inits the SDK if this class is actually used

    def _get_client(self):
        if self._client is None:
            import anthropic  # local import so this module loads fine without the SDK installed
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def complete_json(self, system: str, user: str) -> dict:
        import time

        client = self._get_client()
        max_retries = 3
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                break
            except Exception as e:
                # Retry transient, non-request-specific failures (rate limits,
                # momentary overload, connection hiccups) with backoff --
                # they usually clear within a couple seconds. Anything else
                # (bad key, bad model name, etc.) still fails on the first try.
                status_code = getattr(e, "status_code", None)
                is_transient = status_code in (429, 500, 502, 503, 504) or \
                    type(e).__name__ in ("RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError")
                last_exc = e
                if is_transient and attempt < max_retries:
                    time.sleep(1.5 * (2 ** attempt))
                    continue
                # Covers anthropic.AuthenticationError (bad key), NotFoundError
                # (bad model name), RateLimitError, APIConnectionError, etc.
                # in one place rather than importing and matching every SDK
                # exception class.
                raise RuntimeError(f"Anthropic API request failed: {e}")
        text = "".join(block.text for block in response.content if block.type == "text")
        try:
            return json.loads(_strip_code_fence(text))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse JSON from Anthropic response: {e}\nResponse: {text}")
