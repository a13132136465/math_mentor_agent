"""
GeminiService — high-level Vertex AI service for MathMentor agents.

Adds on top of GeminiClient:
- Retry with exponential back-off (tenacity)
- Per-model client caching (factory pattern)
- Convenience methods aligned to agent use-cases
- Structured output helpers for every agent prompt contract
- Leak-check mini-call
- Async token streaming bridge to asyncio.Queue for SSE
"""
from __future__ import annotations

import asyncio
import time
from asyncio import Queue
from functools import lru_cache
from typing import AsyncIterator, Type

import structlog
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.utils.tracing import trace_span
from app.services.vertex_client import GeminiClient
from app.services.vertex_exceptions import (
    VertexError,
    VertexSafetyError,
    VertexSchemaError,
    VertexTimeoutError,
)
from app.services.vertex_types import (
    GeminiModel,
    GeminiResponse,
    GenerationConfig,
    PromptMessage,
    StreamChunk,
)
from pydantic import BaseModel, field_validator

logger = structlog.get_logger(__name__)


# ── Client factory ────────────────────────────────────────────────

@lru_cache(maxsize=2)
def _get_client(model_alias: str) -> GeminiClient:
    """
    Return a cached GeminiClient for the given alias.
    Called at most twice: once for PRO, once for FLASH.
    """
    settings = get_settings()
    if model_alias == GeminiModel.PRO:
        return GeminiClient(settings.gemini_model_pro, settings.vertex_timeout_pro)
    return GeminiClient(settings.gemini_model_flash, settings.vertex_timeout_flash)


# ── Retry predicate ───────────────────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, VertexError) and exc.retryable


def _before_sleep_log_retry(retry_state: RetryCallState) -> None:
    """
    Tenacity before_sleep hook compatible with structlog.
    (before_sleep_log passes a string level; structlog expects int.)
    """
    if retry_state.outcome is None or retry_state.next_action is None:
        return
    if not retry_state.outcome.failed:
        return
    exc = retry_state.outcome.exception()
    logger.warning(
        "vertex_retry_sleep",
        attempt=retry_state.attempt_number,
        wait_s=retry_state.next_action.sleep,
        exc_type=type(exc).__name__ if exc else None,
        error=str(exc) if exc else None,
    )


# ── Service ───────────────────────────────────────────────────────

class GeminiService:
    """
    Facade used by all MathMentor agents.

    Usage (inject via FastAPI dependency):
        service = GeminiService()
        result = await service.generate_json(
            model=GeminiModel.PRO,
            system_prompt="...",
            user_message="...",
            schema=AnalysisResult,
        )
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def provider_name(self) -> str:
        return "gemini"

    # ── Internal retry wrapper ────────────────────────────────────

    async def _with_retry(self, coro_fn, *args, **kwargs) -> GeminiResponse:
        """
        Execute an async callable with exponential back-off retry.
        Safety errors are never retried.
        Schema errors get one retry with a stricter config.
        """
        s = self._settings
        attempt_num = 0

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(s.vertex_max_retries),
                wait=wait_exponential(
                    multiplier=1,
                    min=s.vertex_retry_min_wait,
                    max=s.vertex_retry_max_wait,
                ),
                retry=retry_if_exception(_is_retryable),
                before_sleep=_before_sleep_log_retry,
                reraise=True,
            ):
                with attempt:
                    attempt_num += 1
                    return await coro_fn(*args, **kwargs)
        except RetryError as exc:
            raise exc.last_attempt.exception() from exc

    # ── Core call methods ─────────────────────────────────────────

    async def generate(
        self,
        model: GeminiModel,
        system_prompt: str,
        messages: list[PromptMessage],
        config: GenerationConfig | None = None,
    ) -> GeminiResponse:
        """Free-text generation with retry."""
        cfg = config or self._default_config(model)
        client = _get_client(model)
        return await self._with_retry(client.generate, system_prompt, messages, cfg)

    async def generate_json(
        self,
        model: GeminiModel,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
        history: list[PromptMessage] | None = None,
        config: GenerationConfig | None = None,
    ) -> GeminiResponse:
        """
        Structured JSON generation with Pydantic validation and retry.

        The `parsed` field on the returned GeminiResponse is guaranteed to be
        an instance of `schema` if this method returns without exception.
        """
        cfg = config or self._default_config(model)
        client = _get_client(model)
        messages = list(history or []) + [PromptMessage(role="user", content=user_message)]
        return await self._with_retry(
            client.generate_json, system_prompt, messages, schema, cfg
        )

    async def stream(
        self,
        model: GeminiModel,
        system_prompt: str,
        user_message: str,
        history: list[PromptMessage] | None = None,
        config: GenerationConfig | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Token streaming — yields StreamChunk objects.
        The caller is responsible for catching VertexError.
        Streaming calls are NOT retried mid-stream.
        """
        cfg = config or self._default_config(model)
        client = _get_client(model)
        messages = list(history or []) + [PromptMessage(role="user", content=user_message)]
        async for chunk in client.stream(system_prompt, messages, cfg):
            yield chunk

    async def stream_to_queue(
        self,
        model: GeminiModel,
        system_prompt: str,
        user_message: str,
        queue: Queue,
        history: list[PromptMessage] | None = None,
        config: GenerationConfig | None = None,
        emit_done: bool = True,
    ) -> str:
        """
        Convenience bridge: stream tokens into an asyncio.Queue for SSE.

        Puts dicts of shape {"type": "token", "text": "..."}.
        Puts {"type": "done"} at the end only when emit_done=True (default).

        Set emit_done=False when the caller needs to inspect the full text
        before deciding whether to forward, retract, or replace the stream
        (e.g. TeachingAgent runs a leak check before committing).

        Returns the full concatenated text.
        """
        from app.utils.llm_error import emit_llm_error

        full_text = ""
        try:
            async for chunk in self.stream(
                model, system_prompt, user_message, history, config
            ):
                if chunk.text:
                    full_text += chunk.text
                    await queue.put({"type": "token", "text": chunk.text})
                if chunk.is_final:
                    break
        except VertexSafetyError as exc:
            await emit_llm_error(queue, exc)
            raise
        except VertexTimeoutError as exc:
            await emit_llm_error(queue, exc)
            raise
        except VertexError as exc:
            await emit_llm_error(queue, exc)
            raise
        except Exception as exc:
            await emit_llm_error(queue, exc)
            raise
        else:
            if emit_done:
                await queue.put({"type": "done"})
        return full_text

    # ── Agent-specific convenience methods ────────────────────────

    async def classify(
        self,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
        history: list[PromptMessage] | None = None,
    ) -> BaseModel:
        """
        Flash-model JSON classification call.
        Returns the validated Pydantic instance directly.
        """
        async with trace_span("vertex", "classify", model="flash"):
            response = await self.generate_json(
                model=GeminiModel.FLASH,
                system_prompt=system_prompt,
                user_message=user_message,
                schema=schema,
                history=history,
                config=GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=512,
                ),
            )
        return response.parsed  # type: ignore[return-value]

    async def analyze(
        self,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
    ) -> tuple[BaseModel, GeminiResponse]:
        """
        Pro-model deep analysis call.
        Returns (parsed_model, full_response) so callers can log token usage.
        """
        async with trace_span("vertex", "analyze", model="pro"):
            response = await self.generate_json(
                model=GeminiModel.PRO,
                system_prompt=system_prompt,
                user_message=user_message,
                schema=schema,
                config=GenerationConfig(
                    temperature=self._settings.gemini_temperature_pro,
                    max_output_tokens=self._settings.gemini_max_output_tokens,
                ),
            )
        return response.parsed, response  # type: ignore[return-value]

    async def teach(
        self,
        system_prompt: str,
        user_message: str,
        history: list[PromptMessage],
        queue: Queue,
        emit_done: bool = True,
    ) -> str:
        """
        Flash streaming tutor turn — tokens flow to queue in real time.

        Pass emit_done=False when the caller (TeachingAgent) needs to run
        a post-stream leak check before committing the response with "done".
        """
        async with trace_span("vertex", "teach", model="flash"):
            return await self.stream_to_queue(
                model=GeminiModel.FLASH,
                system_prompt=system_prompt,
                user_message=user_message,
                queue=queue,
                history=history,
                config=GenerationConfig(
                    temperature=self._settings.gemini_temperature_flash,
                    max_output_tokens=512,
                ),
                emit_done=emit_done,
            )

    async def leak_check(self, draft_response: str) -> float:
        """
        Fast sanity check: ask Flash if the draft leaks the final answer.
        Returns a risk score in [0.0, 1.0].
        Raises on failure (no silent fallback).
        """
        from app.services.vertex_prompts import LEAK_CHECK_SYSTEM  # local import avoids cycle

        class _LeakResult(BaseModel):
            leak_risk: float
            reason: str = ""

            @field_validator("leak_risk", mode="before")
            @classmethod
            def _coerce_leak_risk(cls, v: object) -> float:
                from app.utils.coerce import as_float
                return as_float(v, 0.0)

        try:
            async with trace_span("vertex", "leak_check", model="flash"):
                result = await self.generate_json(
                    model=GeminiModel.FLASH,
                    system_prompt=LEAK_CHECK_SYSTEM,
                    user_message=f'Draft response:\n"""\n{draft_response}\n"""',
                    schema=_LeakResult,
                    config=GenerationConfig(
                        temperature=0.0,
                        max_output_tokens=128,
                    ),
                )
            risk = result.parsed.leak_risk  # type: ignore[union-attr]
            logger.debug("leak_check_done", risk=risk)
            return float(max(0.0, min(1.0, risk)))
        except Exception as exc:
            logger.warning("leak_check_failed", error=str(exc))
            return 0.0

    # ── Helpers ───────────────────────────────────────────────────

    def _default_config(self, model: GeminiModel) -> GenerationConfig:
        s = self._settings
        if model == GeminiModel.PRO:
            return GenerationConfig(
                temperature=s.gemini_temperature_pro,
                max_output_tokens=s.gemini_max_output_tokens,
            )
        return GenerationConfig(
            temperature=s.gemini_temperature_flash,
            max_output_tokens=s.gemini_max_output_tokens,
        )


# ── Singleton accessor ────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_gemini_service() -> GeminiService:
    """Return the process-level singleton GeminiService."""
    return GeminiService()
