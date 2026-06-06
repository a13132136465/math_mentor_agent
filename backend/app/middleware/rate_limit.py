"""
In-memory rate limiting (MVP — single Cloud Run instance).

For multi-instance deployments, replace with Redis / API Gateway rate limits.
See docs/ARCHITECTURE.md §7.4.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window counters keyed by student + route scope."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not path.startswith("/v1"):
            return await call_next(request)

        limit_key, max_calls, window = self._resolve_limit(request)
        if limit_key and self._is_over_limit(limit_key, max_calls, window):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "type": "rate_limit_exceeded",
                    "title": "Too Many Requests",
                    "detail": f"Limit: {max_calls} requests per {window}s",
                    "status": 429,
                },
            )

        return await call_next(request)

    def _resolve_limit(self, request: Request) -> tuple[str | None, int, int]:
        path = request.url.path
        method = request.method
        student = self._student_key(request)

        if method == "POST" and (
            path.endswith("/messages") or path.endswith("/stuck")
        ):
            session_id = path.split("/")[-2] if "/sessions/" in path else "unknown"
            return f"msg:{student}:{session_id}", 60, 3600

        if method == "POST" and path == "/v1/sessions":
            return f"sessions:{student}", 20, 86400

        if method == "POST" and path == "/v1/analyze":
            return f"analyze:{student}", 10, 60

        return None, 0, 0

    @staticmethod
    def _student_key(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:][:32]
        return request.client.host if request.client else "anonymous"

    def _is_over_limit(self, key: str, max_calls: int, window: int) -> bool:
        now = time.time()
        cutoff = now - window
        hits = [t for t in self._buckets[key] if t > cutoff]
        if len(hits) >= max_calls:
            self._buckets[key] = hits
            return True
        hits.append(now)
        self._buckets[key] = hits
        return False
