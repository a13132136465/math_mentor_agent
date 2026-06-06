"""
Unit tests for GeminiService — all Vertex AI calls are mocked.
No real GCP credentials required.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.services.vertex_exceptions import (
    VertexQuotaError,
    VertexSafetyError,
    VertexSchemaError,
    VertexTimeoutError,
)
from app.services.vertex_service import GeminiService
from app.services.vertex_types import GeminiModel, GeminiResponse, StreamChunk


# ── Fixtures ──────────────────────────────────────────────────────


class _SampleSchema(BaseModel):
    topic: str
    confidence: float


def _make_response(text: str) -> GeminiResponse:
    return GeminiResponse(
        text=text,
        parsed=None,
        model="gemini-2.5-flash-preview-05-20",
        input_tokens=50,
        output_tokens=20,
        latency_ms=300,
    )


def _patch_client(response_text: str):
    """Context manager: patches _get_client to return a mock GeminiClient."""
    mock_client = MagicMock()
    mock_client.generate = AsyncMock(return_value=_make_response(response_text))
    mock_client.generate_json = AsyncMock(
        return_value=GeminiResponse(
            text=response_text,
            parsed=_SampleSchema.model_validate(json.loads(response_text)),
            model="gemini-2.5-flash-preview-05-20",
            input_tokens=50,
            output_tokens=30,
            latency_ms=350,
        )
    )
    return patch("app.services.vertex_service._get_client", return_value=mock_client)


# ── Tests ─────────────────────────────────────────────────────────


class TestGeminiServiceGenerate:
    @pytest.mark.asyncio
    async def test_generate_returns_text(self):
        payload = '{"topic": "derivatives", "confidence": 0.9}'
        with _patch_client(payload):
            svc = GeminiService()
            resp = await svc.generate(
                model=GeminiModel.FLASH,
                system_prompt="Test system prompt",
                messages=[],
            )
        assert resp.text == payload
        assert resp.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_generate_json_parses_schema(self):
        payload = '{"topic": "limits", "confidence": 0.85}'
        with _patch_client(payload):
            svc = GeminiService()
            resp = await svc.generate_json(
                model=GeminiModel.FLASH,
                system_prompt="Classify",
                user_message="Find the limit",
                schema=_SampleSchema,
            )
        assert isinstance(resp.parsed, _SampleSchema)
        assert resp.parsed.topic == "limits"
        assert resp.parsed.confidence == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_classify_returns_model_instance(self):
        payload = '{"topic": "integrals", "confidence": 0.75}'
        with _patch_client(payload):
            svc = GeminiService()
            result = await svc.classify(
                system_prompt="Classify",
                user_message="Integrate x^2",
                schema=_SampleSchema,
            )
        assert isinstance(result, _SampleSchema)
        assert result.topic == "integrals"


class TestGeminiServiceRetry:
    @pytest.mark.asyncio
    async def test_retries_on_quota_error(self):
        """Should retry up to max_retries on retryable errors."""
        success_response = _make_response("hello")
        mock_client = MagicMock()
        call_count = 0

        async def flaky_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise VertexQuotaError("rate limited")
            return success_response

        mock_client.generate = flaky_generate

        with patch("app.services.vertex_service._get_client", return_value=mock_client):
            svc = GeminiService()
            resp = await svc.generate(
                model=GeminiModel.FLASH,
                system_prompt="s",
                messages=[],
            )
        assert resp.text == "hello"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_does_not_retry_safety_error(self):
        """Safety errors must NOT be retried — fail immediately."""
        mock_client = MagicMock()
        call_count = 0

        async def safety_blocked(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise VertexSafetyError("HARASSMENT")

        mock_client.generate = safety_blocked

        with patch("app.services.vertex_service._get_client", return_value=mock_client):
            svc = GeminiService()
            with pytest.raises(VertexSafetyError):
                await svc.generate(model=GeminiModel.FLASH, system_prompt="s", messages=[])
        assert call_count == 1


class TestGeminiServiceStreaming:
    @pytest.mark.asyncio
    async def test_stream_to_queue_collects_tokens(self):
        chunks = [
            StreamChunk(text="Hello", is_final=False),
            StreamChunk(text=" world", is_final=False),
            StreamChunk(text="!", is_final=True, finish_reason="STOP"),
        ]

        async def _fake_stream(*args, **kwargs):
            for c in chunks:
                yield c

        with patch.object(GeminiService, "stream", _fake_stream):
            svc = GeminiService()
            queue: asyncio.Queue = asyncio.Queue()
            full_text = await svc.stream_to_queue(
                model=GeminiModel.FLASH,
                system_prompt="Teach",
                user_message="What is a derivative?",
                queue=queue,
            )

        assert full_text == "Hello world!"
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        token_events = [e for e in events if e["type"] == "token"]
        done_events = [e for e in events if e["type"] == "done"]

        assert len(token_events) == 3
        assert len(done_events) == 1
        assert token_events[0]["text"] == "Hello"
        assert token_events[1]["text"] == " world"

    @pytest.mark.asyncio
    async def test_stream_to_queue_puts_error_on_timeout(self):
        async def _timeout_stream(*args, **kwargs):
            raise VertexTimeoutError("gemini-flash", 5.0)
            yield  # make it an async generator

        with patch.object(GeminiService, "stream", _timeout_stream):
            svc = GeminiService()
            queue: asyncio.Queue = asyncio.Queue()
            with pytest.raises(VertexTimeoutError):
                await svc.stream_to_queue(
                    model=GeminiModel.FLASH,
                    system_prompt="s",
                    user_message="u",
                    queue=queue,
                )

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        error_events = [e for e in events if e["type"] == "error"]
        done_events = [e for e in events if e["type"] == "done"]
        assert len(error_events) == 1
        assert error_events[0]["code"] == "timeout"
        assert len(done_events) == 0


class TestLeakCheck:
    @pytest.mark.asyncio
    async def test_leak_check_returns_risk_score(self):
        payload = '{"leak_risk": 0.12, "reason": "no answer revealed"}'
        svc = GeminiService()
        with patch.object(
            svc,
            "generate_json",
            new_callable=AsyncMock,
            return_value=GeminiResponse(
                text=payload,
                parsed=type("_L", (), {"leak_risk": 0.12})(),
                model="flash",
                latency_ms=100,
            ),
        ):
            risk = await svc.leak_check("Good thinking! What is the next step?")
        assert 0.0 <= risk <= 1.0

    @pytest.mark.asyncio
    async def test_leak_check_fails_open(self):
        """Any exception in leak check should return 0.0, not raise."""
        with patch("app.services.vertex_service._get_client", side_effect=Exception("boom")):
            svc = GeminiService()
            risk = await svc.leak_check("some draft")
        assert risk == 0.0


class TestExceptionTranslation:
    def test_vertex_timeout_error_is_retryable(self):
        exc = VertexTimeoutError("gemini-pro", 15.0)
        assert exc.retryable is True
        assert "15.0" in str(exc)

    def test_vertex_safety_error_is_not_retryable(self):
        exc = VertexSafetyError("SEXUAL_CONTENT")
        assert exc.retryable is False

    def test_vertex_schema_error_contains_raw(self):
        exc = VertexSchemaError("gemini-pro", "bad json here", "JSON decode error")
        assert exc.retryable is True
        assert "bad json here" in exc.raw
