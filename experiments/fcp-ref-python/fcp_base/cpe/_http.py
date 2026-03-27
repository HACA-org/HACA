"""
Shared HTTP helper for CPE adapters.

Provides a single post_json() function using stdlib urllib — zero external
dependencies.  Each adapter passes provider-specific URL and headers; error
handling raises the standard CPEError family from cpe.base.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import CPEAuthError, CPEError, CPERateLimitError


def post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    provider: str,
    timeout: int = 120,
) -> dict[str, Any]:
    """POST *payload* as JSON to *url* with *headers*.

    Args:
        url: Full endpoint URL.
        headers: HTTP headers dict (must include Content-Type).
        payload: Request body, serialised to JSON.
        provider: Provider name used in error messages (e.g. "Anthropic").
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response body.

    Raises:
        CPEAuthError: HTTP 401.
        CPERateLimitError: HTTP 429.
        CPEError: Any other HTTP or network error.
    """
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode()[:300]
        if exc.code == 401:
            raise CPEAuthError(f"{provider}: invalid API key") from exc
        if exc.code == 429:
            raise CPERateLimitError(f"{provider}: rate limit exceeded") from exc
        raise CPEError(f"{provider}: HTTP {exc.code} — {body_text}") from exc
    except urllib.error.URLError as exc:
        raise CPEError(f"{provider}: network error — {exc.reason}") from exc
