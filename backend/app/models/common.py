from datetime import datetime
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, field_serializer, model_validator


class PyObjectId(str):
    """String subclass that validates and serializes MongoDB ObjectIds."""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: Any) -> str:
        if isinstance(v, ObjectId):
            return str(v)
        if isinstance(v, str) and ObjectId.is_valid(v):
            return v
        raise ValueError(f"Invalid ObjectId: {v!r}")

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        from pydantic_core import core_schema
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(),
        )


class MongoBase(BaseModel):
    """Base model for all MongoDB documents. Handles ObjectId ↔ str mapping."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda v: v.isoformat()},
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_object_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "_id" in data and "id" not in data:
                data["id"] = str(data["_id"])
            for key in list(data.keys()):
                if isinstance(data[key], ObjectId):
                    data[key] = str(data[key])
        return data


def utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)
