from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.models.student import Student
from app.repositories.base import BaseRepository, _utcnow


class StudentRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def get_by_auth_sub(self, auth_sub: str) -> dict | None:
        return await self.col.find_one({"auth_sub": auth_sub})

    async def get_by_id(self, student_id: str) -> dict | None:
        return await self.find_by_id(student_id)

    async def create(self, student: Student) -> ObjectId:
        doc = student.model_dump(by_alias=False, exclude={"id"})
        return await self.insert_one(doc)

    async def upsert_by_auth_sub(
        self,
        auth_sub: str,
        email: str,
        display_name: str,
        avatar_url: str | None = None,
    ) -> dict:
        """Create or update student on auth login. Returns the student document."""
        now = _utcnow()
        result = await self.col.find_one_and_update(
            {"auth_sub": auth_sub},
            {
                "$setOnInsert": {
                    "auth_sub": auth_sub,
                    "email": email,
                    "preferences": {
                        "hint_style": "balanced",
                        "latex_enabled": True,
                        "notify_exercises": True,
                        "llm_provider": "gemini",
                    },
                    "mastery": {
                        "limits": {"score": 0.5, "attempts": 0, "last_practiced": None},
                        "derivatives": {"score": 0.5, "attempts": 0, "last_practiced": None},
                        "integrals": {"score": 0.5, "attempts": 0, "last_practiced": None},
                    },
                    "error_patterns": [],
                    "stats": {
                        "total_sessions": 0,
                        "total_steps_submitted": 0,
                        "total_exercises_done": 0,
                        "streak_days": 0,
                        "last_active_at": None,
                    },
                    "created_at": now,
                    "schema_version": 1,
                },
                "$set": {
                    "display_name": display_name,
                    "avatar_url": avatar_url,
                    "updated_at": now,
                },
            },
            upsert=True,
            return_document=True,
        )
        return result

    async def update_mastery(
        self,
        student_id: str,
        topic: str,
        new_score: float,
        error_tag: str | None = None,
    ) -> None:
        now = _utcnow()
        update: dict = {
            "$set": {
                f"mastery.{topic}.score": round(max(0.0, min(1.0, new_score)), 4),
                f"mastery.{topic}.last_practiced": now,
                "stats.last_active_at": now,
                "updated_at": now,
            },
            "$inc": {
                f"mastery.{topic}.attempts": 1,
                "stats.total_steps_submitted": 1,
            },
        }
        if error_tag:
            update["$push"] = {
                "error_patterns": {
                    "$each": [{"tag": error_tag, "count": 1, "last_seen": now}],
                    "$slice": -50,
                }
            }
        await self.col.update_one({"_id": self.to_oid(student_id)}, update)

    async def update_preferences(
        self, student_id: str, preferences: dict
    ) -> bool:
        set_fields = {f"preferences.{k}": v for k, v in preferences.items()}
        return await self.update_one(student_id, {"$set": set_fields})

    async def increment_session_count(self, student_id: str) -> None:
        await self.col.update_one(
            {"_id": self.to_oid(student_id)},
            {
                "$inc": {"stats.total_sessions": 1},
                "$set": {"stats.last_active_at": _utcnow(), "updated_at": _utcnow()},
            },
        )

    async def increment_exercise_count(self, student_id: str) -> None:
        await self.col.update_one(
            {"_id": self.to_oid(student_id)},
            {"$inc": {"stats.total_exercises_done": 1}},
        )
