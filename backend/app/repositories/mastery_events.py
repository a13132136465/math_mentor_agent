from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class MasteryEventRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def append(
        self,
        student_id: str,
        session_id: str,
        topic: str,
        subtopic: str | None,
        event_type: str,
        delta: float,
        score_after: float,
        context: dict,
        attempt_id: str | None = None,
    ) -> ObjectId:
        return await self.insert_one({
            "student_id": self.to_oid(student_id),
            "session_id": self.to_oid(session_id),
            "attempt_id": self.to_oid(attempt_id) if attempt_id else None,
            "topic": topic,
            "subtopic": subtopic,
            "event_type": event_type,
            "delta": round(delta, 6),
            "score_after": round(max(0.0, min(1.0, score_after)), 4),
            "context": context,
        })

    async def get_topic_history(
        self, student_id: str, topic: str, limit: int = 100
    ) -> list[dict]:
        return await self.find_many(
            {"student_id": self.to_oid(student_id), "topic": topic},
            sort=[("created_at", -1)],
            limit=limit,
        )

    async def get_session_events(self, session_id: str) -> list[dict]:
        return await self.find_many(
            {"session_id": self.to_oid(session_id)},
            sort=[("created_at", 1)],
            limit=500,
        )
