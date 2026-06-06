from datetime import datetime, timezone
from typing import Any, TypeVar

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.models.common import MongoBase

T = TypeVar("T", bound=MongoBase)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BaseRepository:
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        self.col = collection

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def to_oid(doc_id: str | ObjectId) -> ObjectId:
        return doc_id if isinstance(doc_id, ObjectId) else ObjectId(doc_id)

    @staticmethod
    def _prep_insert(doc: dict) -> dict:
        doc.setdefault("created_at", _utcnow())
        doc.setdefault("schema_version", 1)
        doc.pop("id", None)  # let MongoDB generate _id
        return doc

    # ── CRUD ───────────────────────────────────────────────────

    async def find_by_id(self, doc_id: str | ObjectId) -> dict | None:
        return await self.col.find_one({"_id": self.to_oid(doc_id)})

    async def insert_one(self, doc: dict) -> ObjectId:
        prepared = self._prep_insert(doc.copy())
        result = await self.col.insert_one(prepared)
        return result.inserted_id

    async def update_one(
        self, doc_id: str | ObjectId, update: dict, upsert: bool = False
    ) -> bool:
        update.setdefault("$set", {})["updated_at"] = _utcnow()
        result = await self.col.update_one(
            {"_id": self.to_oid(doc_id)}, update, upsert=upsert
        )
        return result.modified_count > 0 or result.upserted_id is not None

    async def delete_one(self, doc_id: str | ObjectId) -> bool:
        result = await self.col.delete_one({"_id": self.to_oid(doc_id)})
        return result.deleted_count > 0

    async def count(self, query: dict) -> int:
        return await self.col.count_documents(query)

    async def find_many(
        self,
        query: dict,
        sort: list[tuple] | None = None,
        limit: int = 50,
        skip: int = 0,
        projection: dict | None = None,
    ) -> list[dict]:
        cursor = self.col.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)
