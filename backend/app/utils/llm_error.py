"""Map LLM / Vertex failures to SSE error events."""
from __future__ import annotations

import asyncio

from app.services.deepseek_exceptions import DeepSeekError, DeepSeekTimeoutError
from app.services.vertex_exceptions import (
    VertexError,
    VertexSafetyError,
    VertexTimeoutError,
)


def llm_error_code(exc: BaseException) -> str:
    if isinstance(exc, (VertexTimeoutError, DeepSeekTimeoutError)):
        return "timeout"
    if isinstance(exc, VertexSafetyError):
        return "safety"
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if isinstance(exc, DeepSeekError):
        return "deepseek"
    if isinstance(exc, VertexError):
        return "vertex"
    return "unknown"


def llm_error_detail(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__


async def emit_llm_error(queue: asyncio.Queue, exc: BaseException) -> None:
    await queue.put({
        "type": "error",
        "code": llm_error_code(exc),
        "detail": llm_error_detail(exc),
    })
