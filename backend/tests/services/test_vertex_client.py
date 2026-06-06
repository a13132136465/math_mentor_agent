"""
Unit tests for GeminiClient — tests SDK error translation and JSON parsing.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.api_core.exceptions import PermissionDenied, ResourceExhausted, ServiceUnavailable

from app.services.vertex_client import GeminiClient
from app.services.vertex_exceptions import (
    VertexAuthError,
    VertexQuotaError,
    VertexSafetyError,
    VertexSchemaError,
    VertexUnavailableError,
)
from app.services.vertex_types import GenerationConfig, PromptMessage


def _make_mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.candidates = []
    resp.usage_metadata.prompt_token_count = 10
    resp.usage_metadata.candidates_token_count = 20
    return resp


# Patch vertexai.init and GenerativeModel at import time
@pytest.fixture(autouse=True)
def patch_vertexai():
    with (
        patch("app.services.vertex_client.vertexai.init"),
        patch("app.services.vertex_client.GenerativeModel") as mock_model_cls,
    ):
        mock_instance = MagicMock()
        mock_model_cls.return_value = mock_instance
        yield mock_instance


class TestGeminiClientGenerate:
    @pytest.mark.asyncio
    async def test_returns_response_on_success(self, patch_vertexai):
        patch_vertexai.generate_content_async = AsyncMock(
            return_value=_make_mock_response("Great job!")
        )
        client = GeminiClient("gemini-flash", timeout=5.0)
        resp = await client.generate(
            system_prompt="You are a tutor",
            messages=[PromptMessage(role="user", content="help")],
        )
        assert resp.text == "Great job!"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 20

    @pytest.mark.asyncio
    async def test_translates_quota_error(self, patch_vertexai):
        patch_vertexai.generate_content_async = AsyncMock(
            side_effect=ResourceExhausted("rate limit")
        )
        client = GeminiClient("gemini-flash", timeout=5.0)
        with pytest.raises(VertexQuotaError):
            await client.generate("sys", [PromptMessage(role="user", content="q")])

    @pytest.mark.asyncio
    async def test_translates_permission_error(self, patch_vertexai):
        patch_vertexai.generate_content_async = AsyncMock(
            side_effect=PermissionDenied("forbidden")
        )
        client = GeminiClient("gemini-pro", timeout=15.0)
        with pytest.raises(VertexAuthError):
            await client.generate("sys", [PromptMessage(role="user", content="q")])

    @pytest.mark.asyncio
    async def test_translates_unavailable_error(self, patch_vertexai):
        patch_vertexai.generate_content_async = AsyncMock(
            side_effect=ServiceUnavailable("503")
        )
        client = GeminiClient("gemini-pro", timeout=15.0)
        with pytest.raises(VertexUnavailableError):
            await client.generate("sys", [PromptMessage(role="user", content="q")])


class TestGeminiClientGenerateJson:
    @pytest.mark.asyncio
    async def test_parses_valid_json(self, patch_vertexai):
        from pydantic import BaseModel

        class _Out(BaseModel):
            answer: str

        patch_vertexai.generate_content_async = AsyncMock(
            return_value=_make_mock_response('{"answer": "chain_rule"}')
        )
        client = GeminiClient("gemini-pro", timeout=15.0)
        resp = await client.generate_json(
            system_prompt="Classify",
            messages=[PromptMessage(role="user", content="d/dx sin(x)")],
            schema=_Out,
        )
        assert resp.parsed.answer == "chain_rule"  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_strips_markdown_fence(self, patch_vertexai):
        from pydantic import BaseModel

        class _Out(BaseModel):
            value: int

        fenced = "```json\n{\"value\": 42}\n```"
        patch_vertexai.generate_content_async = AsyncMock(
            return_value=_make_mock_response(fenced)
        )
        client = GeminiClient("gemini-flash", timeout=5.0)
        resp = await client.generate_json(
            system_prompt="Output JSON",
            messages=[PromptMessage(role="user", content="give me 42")],
            schema=_Out,
        )
        assert resp.parsed.value == 42  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_raises_schema_error_on_bad_json(self, patch_vertexai):
        from pydantic import BaseModel

        class _Out(BaseModel):
            value: int

        patch_vertexai.generate_content_async = AsyncMock(
            return_value=_make_mock_response("not json at all")
        )
        client = GeminiClient("gemini-flash", timeout=5.0)
        with pytest.raises(VertexSchemaError) as exc_info:
            await client.generate_json(
                system_prompt="JSON only",
                messages=[PromptMessage(role="user", content="hi")],
                schema=_Out,
            )
        assert exc_info.value.retryable is True
