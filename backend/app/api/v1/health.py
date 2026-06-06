from fastapi import APIRouter
from pydantic import BaseModel

from app.db.client import ping_database
from app.services.vertex_health import probe_vertex

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    mongo: bool
    vertex: bool
    detail: dict


@router.get("/health", response_model=HealthResponse)
async def liveness():
    return {"status": "ok"}


@router.get("/ready", response_model=ReadyResponse)
async def readiness():
    mongo_ok = await ping_database()
    vertex_ok, vertex_detail = await probe_vertex(timeout=5.0)

    overall = "ok" if (mongo_ok and vertex_ok) else "degraded"
    return ReadyResponse(
        status=overall,
        mongo=mongo_ok,
        vertex=vertex_ok,
        detail={"vertex_response": vertex_detail},
    )
