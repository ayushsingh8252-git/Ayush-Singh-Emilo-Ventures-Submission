"""LLM provider abstraction.

A provider turns a system instruction + user text into a JSON object that
follows a response schema. Only :class:`GeminiProvider` is implemented; adding
another vendor means implementing ``generate_json`` and registering it in
:func:`create_provider`.

The Gemini REST API is called directly with ``httpx`` (already a dependency),
so no vendor SDK is required. The API key is sent in a header, never in the
URL, so it cannot leak into access logs or exception messages.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class LLMError(Exception):
    """A failed LLM call. ``kind`` is a stable, user-safe reason code."""

    KINDS = {"timeout", "rate_limited", "http_error", "network", "invalid_response", "missing_key",
             "disabled", "circuit_open"}

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


@dataclass
class LLMResult:
    data: dict[str, Any]
    model: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    raw_text: str = field(default="", repr=False)


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult: ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 6.0,
                 client: Optional[httpx.Client] = None, base_url: str = GEMINI_BASE_URL) -> None:
        if not api_key:
            raise LLMError("missing_key", "GEMINI_API_KEY is not set")
        self._api_key = api_key
        self.model = model
        self._url = f"{base_url}/models/{model}:generateContent"
        # httpx applies a timeout per network phase, so connect + read could add up to
        # twice the budget (a 7 s call was observed with a 5 s setting). Splitting one
        # budget between the phases keeps the worst case close to timeout_seconds.
        connect = min(2.0, timeout_seconds / 2)
        self._client = client or httpx.Client(timeout=httpx.Timeout(
            timeout_seconds, connect=connect, read=max(timeout_seconds - connect, 0.001)))

    def __repr__(self) -> str:  # never show the key
        return f"GeminiProvider(model={self.model!r})"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 512,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        started = time.perf_counter()
        try:
            response = self._client.post(self._url, json=body, headers={"x-goog-api-key": self._api_key})
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", type(exc).__name__) from None
        except httpx.HTTPError as exc:
            raise LLMError("network", type(exc).__name__) from None
        latency_ms = (time.perf_counter() - started) * 1000

        if response.status_code == 429:
            raise LLMError("rate_limited", "HTTP 429")
        if response.status_code != 200:
            # Error bodies from Google do not contain the key; keep only the status.
            raise LLMError("http_error", f"HTTP {response.status_code}")
        try:
            payload = response.json()
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("invalid_response", type(exc).__name__) from None
        if not isinstance(data, dict):
            raise LLMError("invalid_response", "top-level JSON is not an object")

        usage = payload.get("usageMetadata", {}) or {}
        return LLMResult(
            data=data,
            model=self.model,
            latency_ms=latency_ms,
            input_tokens=int(usage.get("promptTokenCount", 0) or 0),
            # Thinking tokens are billed as output, so they are counted here too.
            output_tokens=int(usage.get("candidatesTokenCount", 0) or 0) + int(usage.get("thoughtsTokenCount", 0) or 0),
            raw_text=text,
        )


def create_provider(settings) -> tuple[Optional[LLMProvider], str, Optional[str]]:
    """Return (provider or None, status, reason). Never raises.

    status is one of: ``ready``, ``disabled``, ``missing_key``, ``unsupported_provider``.
    No network call is made here, so startup stays fast and free.
    """
    if not settings.llm_enabled:
        return None, "disabled", "LLM_ENABLED is false"
    if settings.llm_provider != "gemini":
        return None, "unsupported_provider", f"unknown LLM_PROVIDER {settings.llm_provider!r}"
    if not settings.gemini_api_key:
        logger.warning("LLM_ENABLED is true but GEMINI_API_KEY is missing; using rule-based understanding.")
        return None, "missing_key", "GEMINI_API_KEY is not set"
    provider = GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_seconds)
    logger.info("LLM query understanding enabled: %s/%s", provider.name, provider.model)
    return provider, "ready", None
