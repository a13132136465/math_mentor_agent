"""
MathMentor FastAPI application entrypoint.
"""
from __future__ import annotations

import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import get_settings
from app.db.client import close_database, create_indexes, ping_database
from app.middleware.rate_limit import RateLimitMiddleware

logger = structlog.get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("startup", env=settings.app_env, version="1.0.0")

    # Verify DB connectivity
    ok = await ping_database()
    if not ok:
        logger.warning("mongo_unreachable_on_startup")
    else:
        await create_indexes()
        logger.info("mongo_indexes_ready")

    yield

    await close_database()
    logger.info("shutdown_complete")


# ── App factory ───────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="MathMentor API",
        description="Socratic Calculus Tutor — Vertex AI · MongoDB · FastAPI",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(RateLimitMiddleware)

    # ── CORS ──────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "internal_error",
                "title": "Internal Server Error",
                "detail": "An unexpected error occurred.",
                "status": 500,
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "type": "validation_error",
                "title": "Validation Error",
                "detail": str(exc),
                "status": 422,
            },
        )

    # ── Routers ───────────────────────────────────────────────────
    app.include_router(api_router)

    return app


app = create_app()
