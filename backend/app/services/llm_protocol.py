"""Provider-agnostic LLM service interface used by agents."""
from __future__ import annotations

from asyncio import Queue
from typing import AsyncIterator, Protocol, Type

from pydantic import BaseModel

from app.services.vertex_types import (
    GeminiModel,
    GeminiResponse,
    GenerationConfig,
    PromptMessage,
    StreamChunk,
)


class LLMService(Protocol):
    async def generate(
        self,
        model: GeminiModel,
        system_prompt: str,
        messages: list[PromptMessage],
        config: GenerationConfig | None = None,
    ) -> GeminiResponse: ...

    async def generate_json(
        self,
        model: GeminiModel,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
        history: list[PromptMessage] | None = None,
        config: GenerationConfig | None = None,
    ) -> GeminiResponse: ...

    async def stream(
        self,
        model: GeminiModel,
        system_prompt: str,
        user_message: str,
        history: list[PromptMessage] | None = None,
        config: GenerationConfig | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    async def stream_to_queue(
        self,
        model: GeminiModel,
        system_prompt: str,
        user_message: str,
        queue: Queue,
        history: list[PromptMessage] | None = None,
        config: GenerationConfig | None = None,
        emit_done: bool = True,
    ) -> str: ...

    async def classify(
        self,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
        history: list[PromptMessage] | None = None,
    ) -> BaseModel: ...

    async def analyze(
        self,
        system_prompt: str,
        user_message: str,
        schema: Type[BaseModel],
    ) -> tuple[BaseModel, GeminiResponse]: ...

    async def teach(
        self,
        system_prompt: str,
        user_message: str,
        history: list[PromptMessage],
        queue: Queue,
        emit_done: bool = True,
    ) -> str: ...

    async def leak_check(self, draft_response: str) -> float: ...

    @property
    def provider_name(self) -> str: ...
