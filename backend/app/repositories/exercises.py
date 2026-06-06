from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository, _utcnow


class ExerciseRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def create(
        self,
        student_id: str,
        session_id: str,
        problems: list[dict],
        generation_meta: dict,
        due_at: datetime,
        interval_hours: int = 24,
    ) -> ObjectId:
        now = _utcnow()
        from datetime import timedelta
        return await self.insert_one({
            "student_id": self.to_oid(student_id),
            "session_id": self.to_oid(session_id),
            "status": "pending",
            "generation_meta": generation_meta,
            "problems": problems,
            "spaced_repetition": {
                "due_at": due_at,
                "interval_hours": interval_hours,
                "repetition_number": 1,
            },
            "completed_at": None,
            "expires_at": now + timedelta(days=180),
        })

    async def get_pending_for_student(
        self, student_id: str, limit: int = 10
    ) -> list[dict]:
        return await self.find_many(
            {
                "student_id": self.to_oid(student_id),
                "status": {"$in": ["pending", "in_progress"]},
                "spaced_repetition.due_at": {"$lte": _utcnow()},
            },
            sort=[("spaced_repetition.due_at", 1)],
            limit=limit,
        )

    async def get_all_for_student(
        self, student_id: str, limit: int = 20
    ) -> list[dict]:
        return await self.find_many(
            {"student_id": self.to_oid(student_id)},
            sort=[("created_at", -1)],
            limit=limit,
        )

    async def update_problem_status(
        self,
        exercise_id: str,
        problem_id: str,
        status: str,
        student_answer: str | None = None,
    ) -> bool:
        update: dict = {
            "$set": {
                "problems.$[elem].status": status,
                "problems.$[elem].completed_at": _utcnow() if status == "completed" else None,
            }
        }
        if student_answer is not None:
            update["$set"]["problems.$[elem].student_answer"] = student_answer

        result = await self.col.update_one(
            {"_id": self.to_oid(exercise_id)},
            update,
            array_filters=[{"elem.id": problem_id}],
        )
        return result.modified_count > 0

    async def mark_completed(self, exercise_id: str) -> None:
        await self.update_one(
            exercise_id,
            {"$set": {"status": "completed", "completed_at": _utcnow()}},
        )

    async def get_recent_problem_prompts(
        self, student_id: str, limit: int = 10
    ) -> list[str]:
        """Return recent exercise prompts for diversity checking."""
        docs = await self.find_many(
            {"student_id": self.to_oid(student_id)},
            sort=[("created_at", -1)],
            limit=5,
            projection={"problems": 1},
        )
        prompts: list[str] = []
        for doc in docs:
            for p in doc.get("problems", []):
                prompts.append(p.get("prompt", ""))
                if len(prompts) >= limit:
                    return prompts
        return prompts
