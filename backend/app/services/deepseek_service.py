"""DeepSeekService — high-level facade mirroring GeminiService for agents."""
from __future__ import annotations

from asyncio import Queue
from functools import lru_cache
from typing import AsyncIterator, Type

import structlog
from pydantic import BaseModel, field_validator
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.services.deepseek_client import DeepSeekClient
from app.services.deepseek_exceptions import (
    DeepSeekError,
    DeepSeekTimeoutError,
)
from app.services.vertex_types import (
    GeminiModel,
    GeminiResponse,
    GenerationConfig,
    PromptMessage,
    StreamChunk,
)

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=2)
def _get_client(model_alias: str) -> DeepSeekClient:
    settings = get_settings()
    if model_alias == GeminiModel.PRO:
        return DeepSeekClient(settings.deepseek_model_pro, settings.deepseek_timeout_pro)
    return DeepSeekClient(settings.deepseek_model_flash, settings.deepseek_timeout_flash)


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, DeepSeekError) and exc.retryable


def _before_sleep_log_retry(retry_state: RetryCallState) -> None:
    if retry_state.outcome is None or retry_state.next_action is None:
        return
    if not retry_state.outcome.failed:
        return
    exc = retry_state.outcome.exception()
    logger.warning(
        "deepseek_retry_sleep",
        attempt=retry_state.attempt_number,
        wait_s=retry_state.next_action.sleep,
        exc_type=type(exc).__name__ if exc else None,
        error=str(exc) if exc else None,
    )


class DeepSeekService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def provider_name(self) -> str:
        return "deepseek"

    async def _with_retry(self, coro_fn, *args, **kwargs) -> GeminiResponse:
        s = self._settings
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
                    return await coro_fn(*args, **kwargs)
        except RetryError as exc:
            raise exc.last_attempt.exception() from exc

    async def generate(
        self,
        model: GeminiModel,
        system_prompt: str,
        messages: list[PromptMessage],
        config: GenerationConfig | None = None,
    ) -> GeminiResponse:
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
        except DeepSeekTimeoutError as exc:
            await emit_llm_error(queue, exc)
            raise
        except DeepSeekError as exc:
            await emit_llm_error(queue, exc)
            raise
        except Exception as exc:
            await emit_llm_error(queue, exc)
            raise
        else:
            if emit_done:
                await queue.put({"type": "done"})
        return full_text

    async def classify(
        self,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
        history: list[PromptMessage] | None = None,
    ) -> BaseModel:
        response = await self.generate_json(
            model=GeminiModel.FLASH,
            system_prompt=system_prompt,
            user_message=user_message,
            schema=schema,
            history=history,
            config=GenerationConfig(temperature=0.0, max_output_tokens=512),
        )
        return response.parsed  # type: ignore[return-value]

    async def analyze(
        self,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
    ) -> tuple[BaseModel, GeminiResponse]:
        response = await self.generate_json(
            model=GeminiModel.PRO,
            system_prompt=system_prompt,
            user_message=user_message,
            schema=schema,
            config=GenerationConfig(
                temperature=self._settings.deepseek_temperature_pro,
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
        return await self.stream_to_queue(
            model=GeminiModel.FLASH,
            system_prompt=system_prompt,
            user_message=user_message,
            queue=queue,
            history=history,
            config=GenerationConfig(
                temperature=self._settings.deepseek_temperature_flash,
                max_output_tokens=512,
            ),
            emit_done=emit_done,
        )

    async def leak_check(self, draft_response: str) -> float:
        from app.services.vertex_prompts import LEAK_CHECK_SYSTEM

        class _LeakResult(BaseModel):
            leak_risk: float
            reason: str = ""

            @field_validator("leak_risk", mode="before")
            @classmethod
            def _coerce_leak_risk(cls, v: object) -> float:
                from app.utils.coerce import as_float
                return as_float(v, 0.0)

        try:
            result = await self.generate_json(
                model=GeminiModel.FLASH,
                system_prompt=LEAK_CHECK_SYSTEM,
                user_message=f'Draft response:\n"""\n{draft_response}\n"""',
                schema=_LeakResult,
                config=GenerationConfig(temperature=0.0, max_output_tokens=128),
            )
            risk = result.parsed.leak_risk  # type: ignore[union-attr]
            logger.debug("leak_check_done", risk=risk, provider="deepseek")
            return float(max(0.0, min(1.0, risk)))
        except Exception as exc:
            logger.warning("leak_check_failed", error=str(exc), provider="deepseek")
            raise

    def _default_config(self, model: GeminiModel) -> GenerationConfig:
        s = self._settings
        if model == GeminiModel.PRO:
            return GenerationConfig(
                temperature=s.deepseek_temperature_pro,
                max_output_tokens=s.gemini_max_output_tokens,
            )
        return GenerationConfig(
            temperature=s.deepseek_temperature_flash,
            max_output_tokens=s.gemini_max_output_tokens,
        )


@lru_cache(maxsize=1)
def get_deepseek_service() -> DeepSeekService:
    return DeepSeekService()
