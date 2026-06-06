from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class AttemptRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def record(
        self,
        session_id: str,
        student_id: str,
        content: str,
        turn_index: int,
        milestone_id: int,
        verdict: str,
        error_tag: str | None,
        critic_output: dict,
        mastery_impact: dict | None,
        hint_level: int,
        message_id: str | None = None,
    ) -> ObjectId:
        return await self.insert_one({
            "session_id": self.to_oid(session_id),
            "student_id": self.to_oid(student_id),
            "message_id": self.to_oid(message_id) if message_id else None,
            "content": content,
            "turn_index": turn_index,
            "milestone_id": milestone_id,
            "verdict": verdict,
            "error_tag": error_tag,
            "critic_output": critic_output,
            "mastery_impact": mastery_impact,
            "hint_level_at_attempt": hint_level,
        })

    async def get_session_attempts(self, session_id: str) -> list[dict]:
        return await self.find_many(
            {"session_id": self.to_oid(session_id)},
            sort=[("turn_index", 1)],
            limit=200,
        )

    async def get_error_tags_for_session(self, session_id: str) -> list[str]:
        docs = await self.find_many(
            {"session_id": self.to_oid(session_id), "error_tag": {"$ne": None}},
            projection={"error_tag": 1, "_id": 0},
            limit=200,
        )
        return [d["error_tag"] for d in docs if d.get("error_tag")]

    async def get_recent_for_student(
        self, student_id: str, limit: int = 50
    ) -> list[dict]:
        """
        Fetch the most recent `limit` attempt documents for a student across
        all sessions, sorted newest-first.  Used by the Analytics Agent.
        """
        return await self.find_many(
            {"student_id": self.to_oid(student_id)},
            sort=[("created_at", -1)],
            limit=limit,
        )
