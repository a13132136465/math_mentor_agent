from fastapi import APIRouter

from app.api.v1 import analytics, analyze, auth, exercises, health, me, messages, sessions

api_router = APIRouter(prefix="/v1")

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(analyze.router)
api_router.include_router(sessions.router)
api_router.include_router(messages.router)
api_router.include_router(exercises.router)
api_router.include_router(analytics.router)
