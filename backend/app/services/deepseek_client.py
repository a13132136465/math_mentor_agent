"""
Low-level async DeepSeek client (OpenAI-compatible chat completions API).
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Type

import httpx
import structlog
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.services.deepseek_exceptions import (
    DeepSeekAuthError,
    DeepSeekError,
    DeepSeekQuotaError,
    DeepSeekSchemaError,
    DeepSeekTimeoutError,
    DeepSeekUnavailableError,
)
from app.services.vertex_types import (
    GeminiResponse,
    GenerationConfig,
    PromptMessage,
    StreamChunk,
)

logger = structlog.get_logger(__name__)


def _map_role(role: str) -> str:
    return "assistant" if role == "model" else role


class DeepSeekClient:
    def __init__(self, model_name: str, timeout: float) -> None:
        self._model_name = model_name
        self._timeout = timeout
        settings = get_settings()
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        logger.info("deepseek_client_ready", model=model_name, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise DeepSeekAuthError(
                "DEEPSEEK_API_KEY is not configured. Set it in backend/.env"
            )
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(
        self, system_prompt: str, messages: list[PromptMessage]
    ) -> list[dict[str, str]]:
        payload = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            payload.append({"role": _map_role(msg.role), "content": msg.content})
        return payload

    @staticmethod
    def _translate_error(exc: Exception, model: str, timeout: float) -> DeepSeekError:
        if isinstance(exc, httpx.TimeoutException):
            return DeepSeekTimeoutError(model, timeout)
        if isinstance(exc, DeepSeekError):
            return exc
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            detail = exc.response.text[:300]
            if status == 401:
                return DeepSeekAuthError(detail)
            if status == 429:
                return DeepSeekQuotaError(detail)
            if status >= 500:
                return DeepSeekUnavailableError(detail)
            return DeepSeekError(f"DeepSeek HTTP {status}: {detail}", retryable=False)
        if isinstance(exc, asyncio.TimeoutError):
            return DeepSeekTimeoutError(model, timeout)
        detail = str(exc).strip() or f"{type(exc).__name__}({exc!r})"
        return DeepSeekError(f"Unexpected DeepSeek error: {detail}", retryable=True)

    @staticmethod
    def _parse_json_text(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
        return json.loads(cleaned)

    async def generate(
        self,
        system_prompt: str,
        messages: list[PromptMessage],
        config: GenerationConfig = GenerationConfig(),
    ) -> GeminiResponse:
        body = {
            "model": self._model_name,
            "messages": self._build_messages(system_prompt, messages),
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_output_tokens,
        }

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise self._translate_error(exc, self._model_name, self._timeout) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        choice = data["choices"][0]
        text = choice.get("message", {}).get("content") or ""
        usage = data.get("usage", {})

        logger.debug(
            "deepseek_generate_ok",
            model=self._model_name,
            latency_ms=latency_ms,
            in_tokens=usage.get("prompt_tokens", 0),
            out_tokens=usage.get("completion_tokens", 0),
        )
        return GeminiResponse(
            text=text,
            parsed=None,
            model=self._model_name,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def generate_json(
        self,
        system_prompt: str,
        messages: list[PromptMessage],
        schema: Type[BaseModel],
        config: GenerationConfig = GenerationConfig(),
    ) -> GeminiResponse:
        json_system = (
            f"{system_prompt}\n\n"
            "## Output format\n"
            "Respond with valid JSON only. No markdown, no explanation, no prose.\n"
            f"Schema:\n```json\n{schema.model_json_schema()}\n```"
        )

        from app.utils.coerce import as_float

        temp = as_float(config.temperature, 0.2)
        json_config = GenerationConfig(
            temperature=min(temp, 0.1),
            top_p=as_float(config.top_p, 0.95),
            top_k=int(as_float(config.top_k, 40)),
            max_output_tokens=int(as_float(config.max_output_tokens, 2048)),
            candidate_count=int(as_float(config.candidate_count, 1)),
        )

        body = {
            "model": self._model_name,
            "messages": self._build_messages(json_system, messages),
            "temperature": json_config.temperature,
            "top_p": json_config.top_p,
            "max_tokens": json_config.max_output_tokens,
            "response_format": {"type": "json_object"},
        }

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise self._translate_error(exc, self._model_name, self._timeout) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        choice = data["choices"][0]
        text = choice.get("message", {}).get("content") or ""
        usage = data.get("usage", {})

        try:
            raw_dict = self._parse_json_text(text)
            parsed = schema.model_validate(raw_dict)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise DeepSeekSchemaError(
                model=self._model_name,
                raw=text,
                detail=str(exc),
            ) from exc

        return GeminiResponse(
            text=text,
            parsed=parsed,
            model=self._model_name,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency_ms,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def stream(
        self,
        system_prompt: str,
        messages: list[PromptMessage],
        config: GenerationConfig = GenerationConfig(),
    ) -> AsyncIterator[StreamChunk]:
        body = {
            "model": self._model_name,
            "messages": self._build_messages(system_prompt, messages),
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_output_tokens,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=body,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            yield StreamChunk(text="", is_final=True, finish_reason="stop")
                            break
                        try:
                            chunk_data: dict[str, Any] = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choice = chunk_data["choices"][0]
                        delta = choice.get("delta", {})
                        text = delta.get("content") or ""
                        finish = choice.get("finish_reason")
                        usage = chunk_data.get("usage") or {}
                        yield StreamChunk(
                            text=text,
                            is_final=finish is not None,
                            finish_reason=finish,
                            usage={
                                "input_tokens": usage.get("prompt_tokens", 0),
                                "output_tokens": usage.get("completion_tokens", 0),
                            },
                        )
        except Exception as exc:
            raise self._translate_error(exc, self._model_name, self._timeout) from exc
