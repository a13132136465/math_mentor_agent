from motor.motor_asyncio import AsyncIOMotorCollection

from app.repositories.base import BaseRepository


class ProblemLibraryRepository(BaseRepository):
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def find_by_topic(
        self,
        topic: str,
        *,
        subtopic: str | None = None,
        difficulty: int | None = None,
        limit: int = 3,
    ) -> list[dict]:
        query: dict = {"topic": topic}
        if subtopic:
            query["subtopic"] = subtopic
        if difficulty is not None:
            query["difficulty"] = difficulty
        return await self.find_many(query, sort=[("difficulty", 1)], limit=limit)

    async def get_recent_prompts(self, limit: int = 20) -> list[str]:
        docs = await self.find_many({}, sort=[("created_at", -1)], limit=limit)
        return [d.get("prompt", "") for d in docs if d.get("prompt")]
