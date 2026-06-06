from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import WriteConcern

from app.repositories.base import BaseRepository


class AgentMemoryRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)
        # Unacknowledged collection for fire-and-forget trace writes
        self._col_fast = collection.with_options(
            write_concern=WriteConcern(w=0)
        )

    async def write_turn_trace(
        self,
        agent_name: str,
        session_id: str,
        student_id: str,
        turn_index: int,
        trace: dict,
    ) -> None:
        """Fire-and-forget — does not wait for write acknowledgement."""
        from app.repositories.base import _utcnow
        doc = {
            "agent_name": agent_name,
            "memory_type": "turn_trace",
            "session_id": self.to_oid(session_id),
            "student_id": self.to_oid(student_id),
            "turn_index": turn_index,
            "turn_trace": trace,
            "session_summary": None,
            "profile_memory": None,
            "error_analysis": None,
            "schema_version": 1,
            "created_at": _utcnow(),
        }
        # w=0 — returns immediately, no exception on failure
        await self._col_fast.insert_one(doc)

    async def write_session_summary(
        self,
        session_id: str,
        student_id: str,
        summary: dict,
    ) -> ObjectId:
        from app.repositories.base import _utcnow
        return await self.insert_one({
            "agent_name": "student_model",
            "memory_type": "session_summary",
            "session_id": self.to_oid(session_id),
            "student_id": self.to_oid(student_id),
            "turn_index": None,
            "turn_trace": None,
            "session_summary": summary,
            "profile_memory": None,
            "error_analysis": None,
        })

    async def write_profile_memory(
        self,
        session_id: str,
        student_id: str,
        profile: dict,
    ) -> ObjectId:
        return await self.insert_one({
            "agent_name": "student_model",
            "memory_type": "profile_memory",
            "session_id": self.to_oid(session_id),
            "student_id": self.to_oid(student_id),
            "turn_index": None,
            "turn_trace": None,
            "session_summary": None,
            "profile_memory": profile,
            "error_analysis": None,
        })

    async def get_latest_profile_memory(self, student_id: str) -> dict | None:
        return await self.col.find_one(
            {"student_id": self.to_oid(student_id), "memory_type": "profile_memory"},
            sort=[("created_at", -1)],
        )

    async def get_session_traces(self, session_id: str) -> list[dict]:
        return await self.find_many(
            {"session_id": self.to_oid(session_id), "memory_type": "turn_trace"},
            sort=[("turn_index", 1)],
            limit=200,
        )
