"""Resolve the active LLM provider for a student or request."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from app.services.deepseek_service import DeepSeekService, get_deepseek_service
from app.services.llm_protocol import LLMService
from app.services.vertex_service import GeminiService, get_gemini_service

LLMProvider = Literal["gemini", "deepseek"]

SUPPORTED_LLM_PROVIDERS: list[LLMProvider] = ["gemini", "deepseek"]


@lru_cache(maxsize=2)
def get_llm_service(provider: str = "gemini") -> LLMService:
    if provider == "deepseek":
        return get_deepseek_service()
    return get_gemini_service()


def resolve_llm_provider(preferences: dict | None) -> LLMProvider:
    raw = (preferences or {}).get("llm_provider", "gemini")
    if raw in SUPPORTED_LLM_PROVIDERS:
        return raw  # type: ignore[return-value]
    return "gemini"
