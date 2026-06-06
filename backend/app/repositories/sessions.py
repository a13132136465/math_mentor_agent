from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository, _utcnow


class SessionRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def create(self, student_id: str, problem_text: str) -> ObjectId:
        now = _utcnow()
        return await self.insert_one({
            "student_id": self.to_oid(student_id),
            "status": "active",
            "phase": "intake",
            "problem_text": problem_text,
            "analysis": None,
            "plan": None,
            "progress": {
                "current_milestone": 0,
                "hint_level": 0,
                "solution_ready": False,
                "turn_count": 0,
                "message_count": 0,
                "stuck_count": 0,
            },
            "session_summary": None,
            "flags": {
                "degraded_mode": False,
                "circuit_breaker": False,
                "integrity_flagged": False,
            },
            "started_at": now,
            "ended_at": None,
            "updated_at": now,
        })

    async def get_for_client(self, session_id: str) -> dict | None:
        """Load session with plan stripped — never expose plan to client."""
        doc = await self.find_by_id(session_id)
        if doc:
            doc.pop("plan", None)
        return doc

    async def get_for_agent(self, session_id: str) -> dict | None:
        """Load session including plan — server-side agent use only."""
        return await self.find_by_id(session_id)

    async def list_for_student(
        self,
        student_id: str,
        status: str | None = None,
        limit: int = 20,
        skip: int = 0,
    ) -> list[dict]:
        query: dict = {"student_id": self.to_oid(student_id)}
        if status:
            query["status"] = status
        return await self.find_many(
            query,
            sort=[("started_at", -1)],
            limit=limit,
            skip=skip,
            projection={"plan": 0},
        )

    async def save_analysis_and_plan(
        self, session_id: str, analysis: dict, plan: dict
    ) -> None:
        await self.update_one(
            session_id,
            {"$set": {"analysis": analysis, "plan": plan, "phase": "tutoring"}},
        )

    async def update_progress(
        self,
        session_id: str,
        milestone: int,
        hint_level: int,
        phase: str,
        solution_ready: bool = False,
        response_locale: str | None = None,
    ) -> None:
        progress_set: dict = {
            "progress.current_milestone": milestone,
            "progress.hint_level": hint_level,
            "progress.solution_ready": solution_ready,
            "phase": phase,
        }
        if response_locale is not None:
            progress_set["progress.response_locale"] = response_locale

        await self.update_one(
            session_id,
            {
                "$set": progress_set,
                "$inc": {"progress.turn_count": 1, "progress.message_count": 2},
            },
        )

    async def increment_stuck(self, session_id: str, new_hint_level: int) -> None:
        await self.update_one(
            session_id,
            {
                "$inc": {"progress.stuck_count": 1},
                "$set": {"progress.hint_level": new_hint_level},
            },
        )

    async def complete_session(self, session_id: str, summary: dict) -> None:
        now = _utcnow()
        await self.update_one(
            session_id,
            {
                "$set": {
                    "status": "completed",
                    "phase": "completed",
                    "session_summary": summary,
                    "ended_at": now,
                }
            },
        )

    async def set_flag(self, session_id: str, flag: str, value: bool) -> None:
        await self.update_one(session_id, {"$set": {f"flags.{flag}": value}})

    async def mark_degraded(self, session_id: str) -> None:
        await self.set_flag(session_id, "degraded_mode", True)

    async def mark_circuit_breaker(self, session_id: str) -> None:
        await self.set_flag(session_id, "circuit_breaker", True)
