from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository, _utcnow


class MessageRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def insert_student_message(
        self,
        session_id: str,
        student_id: str,
        content: str,
        turn_index: int,
        client_message_id: str | None = None,
    ) -> ObjectId:
        doc: dict = {
            "session_id": self.to_oid(session_id),
            "student_id": self.to_oid(student_id),
            "role": "student",
            "content": content,
            "turn_index": turn_index,
            "agent_trace": None,
            "metadata": None,
        }
        # Omit field when unset — sparse idempotency index treats null as a value.
        if client_message_id:
            doc["client_message_id"] = client_message_id
        return await self.insert_one(doc)

    async def insert_assistant_message(
        self,
        session_id: str,
        student_id: str,
        content: str,
        turn_index: int,
        agent_trace: dict | None = None,
        metadata: dict | None = None,
    ) -> ObjectId:
        return await self.insert_one({
            "session_id": self.to_oid(session_id),
            "student_id": self.to_oid(student_id),
            "role": "assistant",
            "content": content,
            "turn_index": turn_index,
            "agent_trace": agent_trace,
            "metadata": metadata,
        })

    async def get_session_history(
        self, session_id: str, limit: int = 50
    ) -> list[dict]:
        return await self.find_many(
            {"session_id": self.to_oid(session_id)},
            sort=[("created_at", 1)],
            limit=limit,
        )

    async def get_recent_for_context(
        self, session_id: str, n: int = 6
    ) -> list[dict]:
        """Return the n most recent messages for LLM context injection."""
        docs = await self.find_many(
            {"session_id": self.to_oid(session_id)},
            sort=[("created_at", -1)],
            limit=n,
            projection={"role": 1, "content": 1, "_id": 0},
        )
        return list(reversed(docs))

    async def is_duplicate(
        self, session_id: str, client_message_id: str
    ) -> bool:
        doc = await self.col.find_one({
            "session_id": self.to_oid(session_id),
            "client_message_id": client_message_id,
        })
        return doc is not None
