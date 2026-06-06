from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings


@lru_cache(maxsize=1)
def _get_motor_client() -> AsyncIOMotorClient:
    settings = get_settings()
    return AsyncIOMotorClient(
        settings.mongodb_uri,
        maxPoolSize=settings.mongodb_max_pool_size,
        minPoolSize=settings.mongodb_min_pool_size,
        serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        connectTimeoutMS=settings.mongodb_connect_timeout_ms,
        socketTimeoutMS=settings.mongodb_socket_timeout_ms,
        uuidRepresentation="standard",
    )


def get_database() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return _get_motor_client()[settings.mongodb_db_name]


async def ping_database() -> bool:
    try:
        client = _get_motor_client()
        await client.admin.command("ping")
        return True
    except Exception:
        return False


async def close_database() -> None:
    try:
        client = _get_motor_client()
        client.close()
        _get_motor_client.cache_clear()
    except Exception:
        pass


async def create_indexes() -> None:
    """Create all collection indexes on startup."""
    db = get_database()

    # students
    await db.students.create_index("auth_sub", unique=True, name="idx_auth_sub_unique")
    await db.students.create_index(
        "email", unique=True, sparse=True, name="idx_email_unique"
    )
    await db.students.create_index(
        "stats.last_active_at", name="idx_last_active"
    )

    # sessions
    await db.sessions.create_index(
        [("student_id", 1), ("started_at", -1)], name="idx_student_sessions_time"
    )
    await db.sessions.create_index(
        [("status", 1), ("started_at", -1)], name="idx_status_time"
    )

    # messages
    await db.messages.create_index(
        [("session_id", 1), ("created_at", 1)], name="idx_session_chat_order"
    )
    # Idempotency: only student messages with a client_message_id (omit field otherwise).
    try:
        await db.messages.drop_index("idx_idempotency")
    except Exception:
        pass
    await db.messages.create_index(
        [("session_id", 1), ("client_message_id", 1)],
        unique=True,
        name="idx_idempotency",
        partialFilterExpression={
            "client_message_id": {"$exists": True, "$type": "string"},
        },
    )
    await db.messages.create_index(
        "created_at",
        expireAfterSeconds=7_776_000,  # 90 days
        name="ttl_messages_90d",
    )

    # attempts
    await db.attempts.create_index(
        [("session_id", 1), ("turn_index", 1)], name="idx_session_attempts_order"
    )
    await db.attempts.create_index(
        [("student_id", 1), ("error_tag", 1)],
        sparse=True,
        name="idx_student_error_tags",
    )
    await db.attempts.create_index(
        "created_at",
        expireAfterSeconds=31_536_000,  # 1 year
        name="ttl_attempts_1yr",
    )

    # mastery_events
    await db.mastery_events.create_index(
        [("student_id", 1), ("topic", 1), ("created_at", -1)],
        name="idx_student_topic_time",
    )
    await db.mastery_events.create_index("session_id", name="idx_session_events")

    # exercises
    await db.exercises.create_index(
        [("student_id", 1), ("status", 1), ("spaced_repetition.due_at", 1)],
        name="idx_student_pending_due",
    )
    await db.exercises.create_index(
        "expires_at", expireAfterSeconds=0, name="ttl_exercises_expiry"
    )

    # problem_library
    await db.problem_library.create_index(
        [("topic", 1), ("subtopic", 1), ("difficulty", 1)],
        name="idx_topic_subtopic_difficulty",
    )

    # agent_memory
    await db.agent_memory.create_index(
        [("session_id", 1), ("turn_index", 1), ("agent_name", 1)],
        name="idx_session_turn_agent",
    )
    await db.agent_memory.create_index(
        [("student_id", 1), ("memory_type", 1), ("created_at", -1)],
        name="idx_student_memory_type",
    )
    await db.agent_memory.create_index(
        "created_at",
        expireAfterSeconds=2_592_000,  # 30 days (volatile types only)
        partialFilterExpression={"memory_type": {"$in": ["turn_trace", "error_analysis"]}},
        name="ttl_agent_memory_volatile_30d",
    )
