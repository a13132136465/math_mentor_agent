"""
Value objects and enums used across the Vertex AI service layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GeminiModel(str, Enum):
    """Canonical model aliases — map to real endpoint names from Settings."""

    PRO = "pro"
    FLASH = "flash"


@dataclass(frozen=True)
class GenerationConfig:
    """Per-call generation parameters."""

    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 2048
    candidate_count: int = 1


@dataclass(frozen=True)
class PromptMessage:
    """A single message in a multi-turn prompt."""

    role: str  # "user" | "model"
    content: str


@dataclass
class GeminiResponse:
    """Parsed, validated response from a Gemini call."""

    text: str
    parsed: Any | None          # Pydantic model instance if schema was provided
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = "STOP"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class StreamChunk:
    """A single SSE-style token chunk from a streaming call."""

    text: str
    is_final: bool = False
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)
