from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str
    model: str = "claude-3-5-sonnet-latest"
    max_tokens: int = 2000
    timeout_seconds: int = 120


class AnthropicError(RuntimeError):
    pass


def _anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "user-agent": "johbloch-oracle-migration/0.1.0",
    }


def call_anthropic_messages(*, config: AnthropicConfig, system: str, user: str) -> dict[str, Any]:
    """Call Anthropic Messages API.

    Uses only stdlib to keep this project dependency-light.
    """

    if not config.api_key:
        raise AnthropicError("missing api key")

    payload: dict[str, Any] = {
        "model": config.model,
        "max_tokens": int(config.max_tokens),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers=_anthropic_headers(config.api_key),
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as e:  # pragma: no cover
        raise AnthropicError(f"anthropic request failed: {e}") from e

    try:
        return json.loads(body)
    except Exception as e:  # pragma: no cover
        raise AnthropicError(f"anthropic response was not valid JSON: {e}") from e


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a text blob."""

    if not text:
        raise ValueError("empty text")

    m = _JSON_OBJ_RE.search(text)
    if not m:
        raise ValueError("no JSON object found")

    candidate = m.group(0).strip()
    return json.loads(candidate)


def get_api_key_from_env(env_var: str = "ANTHROPIC_API_KEY") -> str:
    return os.environ.get(env_var, "").strip()
