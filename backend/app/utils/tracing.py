"""
Lightweight per-agent span logging for Cloud Logging / Trace correlation.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog

logger = structlog.get_logger("mathmentor.trace")


@asynccontextmanager
async def trace_span(agent: str, operation: str, **attrs) -> AsyncIterator[str]:
    span_id = uuid.uuid4().hex[:16]
    t0 = time.monotonic()
    logger.info(
        "span_start",
        span_id=span_id,
        agent=agent,
        operation=operation,
        **attrs,
    )
    try:
        yield span_id
    except Exception as exc:
        logger.error(
            "span_error",
            span_id=span_id,
            agent=agent,
            operation=operation,
            error=str(exc),
            latency_ms=int((time.monotonic() - t0) * 1000),
            **attrs,
        )
        raise
    else:
        logger.info(
            "span_end",
            span_id=span_id,
            agent=agent,
            operation=operation,
            latency_ms=int((time.monotonic() - t0) * 1000),
            **attrs,
        )
