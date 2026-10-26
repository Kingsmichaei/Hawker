"""LLM providers. History uses Gemini's `contents` format:

    {"role": "user" | "model", "parts": [{"text": ...} | {"functionCall": ...} | {"functionResponse": ...}]}

Any provider just has to take (system, contents, tools) and return one model turn.
"""
import asyncio
from typing import Protocol

import httpx

from .config import settings


class LLMError(Exception):
    pass


class LLMProvider(Protocol):
    async def generate(self, system: str, contents: list[dict], tools: list[dict]) -> dict: ...


def _gemini_schema(schema: dict) -> dict:
    """Convert a JSON Schema fragment into Gemini's OpenAPI-style schema (upper-case types)."""
    out: dict = {}
    for key, value in schema.items():
        if key == "type":
            out["type"] = str(value).upper()
        elif key == "properties":
            out["properties"] = {k: _gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out["items"] = _gemini_schema(value)
        elif key in ("description", "enum", "required", "minimum", "maximum", "nullable", "format"):
            out[key] = value
    return out


class GeminiProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None, http: httpx.AsyncClient | None = None):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self._http = http

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=60)
        return self._http

    async def generate(self, system: str, contents: list[dict], tools: list[dict]) -> dict:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.4},
        }
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t["description"],
                            "parameters": _gemini_schema(t["parameters"]),
                        }
                        for t in tools
                    ]
                }
            ]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        for attempt in range(3):
            try:
                r = await self._client().post(url, json=body, headers={"x-goog-api-key": self.api_key})
            except httpx.TimeoutException as e:
                # Already waited the full timeout; retrying would leave the buyer hanging for minutes.
                raise LLMError(f"Gemini timed out: {type(e).__name__}") from e
            except httpx.TransportError as e:
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise LLMError(f"Gemini network error: {type(e).__name__}") from e
            if r.status_code in (429, 500, 503) and attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            break
        if r.status_code != 200:
            raise LLMError(f"Gemini error {r.status_code}: {r.text[:300]}")
        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates or "content" not in candidates[0]:
            raise LLMError(f"Gemini returned no content: {str(data)[:300]}")
        content = candidates[0]["content"]
        content["role"] = "model"
        content.setdefault("parts", [])
        # Keep parts exactly as returned (including any thoughtSignature) so later turns stay valid.
        return content


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Used by tests to swap in a scripted provider."""
    global _provider
    _provider = provider
