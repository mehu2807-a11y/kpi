"""
Shared retry helper for the LLM HTTP clients.

Every provider (Gemini, OpenAI, Grok, ...) occasionally returns a transient
error that has nothing to do with the request itself -- an overloaded model
(503), a momentary outage (500/502/504), or a rate limit (429). Failing the
whole /analyze call on the first one of these is unnecessary: a short
backoff-and-retry clears the large majority of them.

This is intentionally tiny and dependency-free (just stdlib `time`) so it
can be dropped into any of the `requests`-based clients unchanged.
"""

from __future__ import annotations
import time
from typing import Callable, Iterable

import requests

# Status codes worth retrying: rate-limited, or a server-side/upstream problem.
# 4xx codes that mean "your request is wrong" (400/401/403/404) are NOT here
# on purpose -- retrying those just wastes time and delays a useful error.
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def request_with_retry(
    send: Callable[[float], "requests.Response"],
    max_retries: int = 3,
    backoff_base: float = 1.5,
    retryable_statuses: Iterable[int] = RETRYABLE_STATUS_CODES,
    total_budget: float = 45.0,
    per_attempt_timeout: float = 55.0,
) -> "requests.Response":
    """
    Call `send(timeout)` (a function that performs one HTTP request using
    the given timeout and returns the Response), retrying with exponential
    backoff if the response status is in `retryable_statuses` or the
    request raised a timeout/connection error.

    `total_budget` is a hard wall-clock ceiling, in seconds, across ALL
    attempts and backoff sleeps combined. This matters because most
    deployments sit behind a reverse proxy / platform gateway with its own
    inbound request timeout (commonly 30-100s). If this helper is allowed
    to run 4 attempts x 55s + backoff sleeps (200+ seconds worst case),
    that gateway will kill the connection first and hand the browser a
    generic HTML "Internal Server Error" page -- *before* the Flask app's
    own try/except ever gets a chance to run and return a clean JSON error.
    Capping the whole retry loop well under typical gateway limits means we
    either succeed, or fail fast with an informative JSON error, instead of
    silently getting cut off. Tune `total_budget` down further (or up, if
    your gateway allows longer requests) via the LLM_RETRY_BUDGET_SECONDS
    env var -- see call sites.

    Returns the last Response once retries/budget are exhausted (or
    immediately on a non-retryable status/success) so the caller's existing
    status-code handling keeps working unchanged. Non-transient exceptions
    are re-raised immediately.
    """
    retryable_statuses = frozenset(retryable_statuses)
    start = time.monotonic()
    last_response = None
    last_exc = None

    for attempt in range(max_retries + 1):
        remaining = total_budget - (time.monotonic() - start)
        if remaining <= 1:
            # Not enough budget left for a worthwhile attempt -- stop now
            # rather than risk running past the gateway's own timeout.
            if last_exc is not None:
                raise last_exc
            if last_response is not None:
                return last_response
            raise TimeoutError(
                f"Giving up before the first attempt: the {total_budget:.0f}s "
                "retry budget was already exhausted (see request_with_retry)."
            )

        attempt_timeout = min(per_attempt_timeout, remaining)
        try:
            response = send(attempt_timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            remaining = total_budget - (time.monotonic() - start)
            if attempt < max_retries and remaining > 0:
                time.sleep(min(backoff_base * (2 ** attempt), remaining))
                continue
            raise

        if response.status_code not in retryable_statuses:
            return response

        last_response = response
        remaining = total_budget - (time.monotonic() - start)
        if attempt < max_retries and remaining > 0:
            time.sleep(min(backoff_base * (2 ** attempt), remaining))
        elif attempt < max_retries:
            break

    return last_response
