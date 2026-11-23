"""Language-model clients over HTTP (EVAL-005, NFR-002, NFR-004; research.md R1, R2, R7).

Two clients share one protocol: ``AnthropicClient`` (Messages API) and
``OpenAICompatibleClient`` (``/chat/completions``). Credentials come only from environment
variables and are never logged, printed or included in error messages.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

import httpx

from reviewer.errors import ConfigurationError, LLMServiceError, ReviewerError

TEMPERATURE = 0.0
MAX_TOKENS = 8192
TIMEOUT_SECONDS = 60.0
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Statuses that mean the provider, not the application, failed (Constitution VI).
_SERVICE_STATUSES = frozenset({401, 403, 408, 409, 429})


class LLMClient(Protocol):
    """What the service and the harness need from a model client."""

    def complete(self, system: str, user: str) -> str:
        """Return the model's text reply to ``user`` under the ``system`` prompt."""
        ...

    def describe(self) -> dict[str, Any]:
        """Return ``provider``, ``model``, ``temperature`` and ``max_tokens`` (NFR-004)."""
        ...


def _error_reason(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message", ""))[:200]
    return str(error or "")[:200]


def _check_status(response: httpx.Response) -> None:
    status = response.status_code
    if 200 <= status < 300:
        return
    reason = _error_reason(response)
    if status in _SERVICE_STATUSES or status >= 500:
        raise LLMServiceError(f"provider returned HTTP {status}: {reason}")
    raise ReviewerError(f"provider rejected the request with HTTP {status}: {reason}")


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> Any:
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        kind = type(exc).__name__
        raise LLMServiceError(f"request to the model provider timed out ({kind})") from exc
    except httpx.RequestError as exc:
        kind = type(exc).__name__
        raise LLMServiceError(f"could not reach the model provider ({kind})") from exc
    _check_status(response)
    try:
        return response.json()
    except ValueError as exc:
        raise LLMServiceError("the model provider returned a body that is not JSON") from exc


def _describe(provider: str, model: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }


class AnthropicClient:
    """Claude via the Messages API (``POST /v1/messages``)."""

    def __init__(self, api_key: str, model: str = DEFAULT_ANTHROPIC_MODEL) -> None:
        self._api_key = api_key
        self.model = model

    def __repr__(self) -> str:
        return f"AnthropicClient(model={self.model!r})"

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body = _post_json(ANTHROPIC_URL, headers, payload)
        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, list):
            raise LLMServiceError("unexpected response shape from the Anthropic API")
        return "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    def describe(self) -> dict[str, Any]:
        return _describe("anthropic", self.model)


class OpenAICompatibleClient:
    """Any ``/chat/completions`` endpoint: OpenAI, Gemini's compatible endpoint, Groq, Ollama."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key

    def __repr__(self) -> str:
        return f"OpenAICompatibleClient(base_url={self.base_url!r}, model={self.model!r})"

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        body = _post_json(f"{self.base_url}/chat/completions", headers, payload)
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            message = "unexpected response shape from the chat completions API"
            raise LLMServiceError(message) from exc
        return text if isinstance(text, str) else ""

    def describe(self) -> dict[str, Any]:
        return _describe("openai_compatible", self.model)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"environment variable {name} is not set")
    return value


def _openai_compatible_from_env() -> OpenAICompatibleClient:
    base_url = _require("LLM_BASE_URL")
    if not base_url.startswith(("http://", "https://")):
        raise ConfigurationError("LLM_BASE_URL must start with http:// or https://")
    model = _require("REVIEW_MODEL")
    api_key = os.environ.get("LLM_API_KEY", "").strip() or None
    return OpenAICompatibleClient(base_url, model, api_key)


def build_client_from_env() -> LLMClient:
    """Build a client from ``LLM_PROVIDER`` and related environment variables.

    See contracts/python-api.md. Missing values raise ``ConfigurationError`` naming the
    variable, never its value. No ``.env`` file is read.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"
    if provider == "anthropic":
        api_key = _require("ANTHROPIC_API_KEY")
        model = os.environ.get("REVIEW_MODEL", "").strip() or DEFAULT_ANTHROPIC_MODEL
        return AnthropicClient(api_key, model)
    if provider == "openai_compatible":
        return _openai_compatible_from_env()
    raise ConfigurationError(
        f"LLM_PROVIDER must be 'anthropic' or 'openai_compatible', got {provider[:40]!r}"
    )
