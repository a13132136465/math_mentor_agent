"""
Lightweight Vertex AI connectivity probe used by /v1/ready endpoint.
"""
from __future__ import annotations

import asyncio

import structlog

from app.services.vertex_types import GeminiModel, GenerationConfig, PromptMessage

logger = structlog.get_logger(__name__)


async def probe_vertex(timeout: float = 5.0) -> tuple[bool, str]:
    """
    Send a minimal Flash call to confirm Vertex AI is reachable.
    Returns (ok: bool, detail: str).
    """
    from app.services.vertex_service import get_gemini_service

    try:
        service = get_gemini_service()
        response = await asyncio.wait_for(
            service.generate(
                model=GeminiModel.FLASH,
                system_prompt="Reply with exactly the word: OK",
                messages=[PromptMessage(role="user", content="ping")],
                config=GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=4,
                ),
            ),
            timeout=timeout,
        )
        ok = "ok" in response.text.lower()
        return ok, response.text.strip()
    except asyncio.TimeoutError:
        return False, f"Vertex AI probe timed out after {timeout}s"
    except Exception as exc:
        logger.warning("vertex_probe_failed", error=str(exc))
        return False, str(exc)
