"""
Low-level async Vertex AI / Gemini client.

Responsibilities:
- One-shot calls (structured JSON + free-text)
- Streaming calls (token-by-token)
- Exception translation (google SDK → VertexError hierarchy)
- Timeout enforcement via asyncio.wait_for
- No retry logic here — that lives in GeminiService
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Type

import structlog
import vertexai
from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPIError,
    PermissionDenied,
    ResourceExhausted,
    ServiceUnavailable,
)
from pydantic import BaseModel, ValidationError
from vertexai.generative_models import (
    GenerationConfig as VertexGenerationConfig,
    GenerativeModel,
    HarmBlockThreshold,
    HarmCategory,
    Part,
    SafetySetting,
)

from app.config import get_settings
from app.services.vertex_exceptions import (
    VertexApiDisabledError,
    VertexAuthError,
    VertexError,
    VertexQuotaError,
    VertexSafetyError,
    VertexSchemaError,
    VertexTimeoutError,
    VertexUnavailableError,
)
from app.services.vertex_types import (
    GeminiModel,
    GeminiResponse,
    GenerationConfig,
    PromptMessage,
    StreamChunk,
)

logger = structlog.get_logger(__name__)

# Safety settings: block only HIGH-severity harm in an educational context
_SAFETY_SETTINGS = [
    SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                  threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
    SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                  threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
    SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                  threshold=HarmBlockThreshold.BLOCK_LOW_AND_ABOVE),
    SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                  threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
]


def _init_vertex() -> None:
    """Idempotent Vertex AI SDK initialisation."""
    settings = get_settings()
    vertexai.init(project=settings.gcp_project, location=settings.vertex_location)


class GeminiClient:
    """
    Thin async wrapper around vertexai.GenerativeModel.

    One instance per model endpoint — obtain via GeminiClientFactory.
    """

    def __init__(self, model_name: str, timeout: float) -> None:
        _init_vertex()
        self._model_name = model_name
        self._timeout = timeout
        logger.info("gemini_client_ready", model=model_name, timeout=timeout)

    def _model_for(self, system_prompt: str) -> GenerativeModel:
        """Build a model handle; system_instruction is set on the model, not per call."""
        return GenerativeModel(
            self._model_name,
            system_instruction=system_prompt or None,
        )

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _build_gen_config(cfg: GenerationConfig) -> VertexGenerationConfig:
        return VertexGenerationConfig(
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            top_k=cfg.top_k,
            max_output_tokens=cfg.max_output_tokens,
            candidate_count=cfg.candidate_count,
        )

    @staticmethod
    def _translate_error(exc: Exception, model: str, timeout: float) -> VertexError:
        """Map SDK exception → typed VertexError."""
        if isinstance(exc, (asyncio.TimeoutError, DeadlineExceeded)):
            return VertexTimeoutError(model, timeout)
        if isinstance(exc, ResourceExhausted):
            return VertexQuotaError(str(exc))
        if isinstance(exc, PermissionDenied):
            detail = str(exc)
            if "SERVICE_DISABLED" in detail or "has not been used in project" in detail:
                settings = get_settings()
                return VertexApiDisabledError(
                    project=settings.gcp_project,
                    activation_url=(
                        "https://console.cloud.google.com/apis/library/"
                        "aiplatform.googleapis.com"
                        f"?project={settings.gcp_project}"
                    ),
                )
            return VertexAuthError(detail)
        if isinstance(exc, ServiceUnavailable):
            return VertexUnavailableError(str(exc))
        if isinstance(exc, GoogleAPIError):
            return VertexUnavailableError(str(exc))
        return VertexError(f"Unexpected Vertex error: {exc}", retryable=True)

    @staticmethod
    def _extract_usage(response: Any) -> tuple[int, int]:
        try:
            meta = response.usage_metadata
            return meta.prompt_token_count or 0, meta.candidates_token_count or 0
        except Exception:
            return 0, 0

    @staticmethod
    def _check_safety(response: Any) -> None:
        try:
            for candidate in response.candidates:
                if candidate.finish_reason and candidate.finish_reason.name == "SAFETY":
                    ratings = {
                        r.category.name: r.probability.name
                        for r in candidate.safety_ratings
                    }
                    raise VertexSafetyError(str(ratings))
        except VertexSafetyError:
            raise
        except Exception:
            pass

    def _parse_json_text(self, text: str) -> dict:
        """Strip markdown fences and parse JSON."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # Drop first fence line (```json) and last (```)
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
        return json.loads(cleaned)

    # ── Public API ────────────────────────────────────────────────

    async def generate(
        self,
        system_prompt: str,
        messages: list[PromptMessage],
        config: GenerationConfig = GenerationConfig(),
    ) -> GeminiResponse:
        """Single-turn or multi-turn free-text generation."""
        gen_cfg = self._build_gen_config(config)
        contents = [Part.from_text(m.content) for m in messages]

        model = self._model_for(system_prompt)
        t0 = time.monotonic()
        try:
            response = await asyncio.wait_for(
                model.generate_content_async(
                    contents,
                    generation_config=gen_cfg,
                    safety_settings=_SAFETY_SETTINGS,
                ),
                timeout=self._timeout,
            )
        except VertexSafetyError:
            raise
        except Exception as exc:
            raise self._translate_error(exc, self._model_name, self._timeout) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        self._check_safety(response)

        text = response.text or ""
        in_tok, out_tok = self._extract_usage(response)

        logger.debug(
            "gemini_generate_ok",
            model=self._model_name,
            latency_ms=latency_ms,
            in_tokens=in_tok,
            out_tokens=out_tok,
        )
        return GeminiResponse(
            text=text,
            parsed=None,
            model=self._model_name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=latency_ms,
        )

    async def generate_json(
        self,
        system_prompt: str,
        messages: list[PromptMessage],
        schema: Type[BaseModel],
        config: GenerationConfig = GenerationConfig(),
    ) -> GeminiResponse:
        """
        Generate and validate a structured JSON response.

        Instructs the model via the system prompt to return JSON only,
        then validates the output against the provided Pydantic schema.
        Raises VertexSchemaError if validation fails.
        """
        json_system = (
            f"{system_prompt}\n\n"
            "## Output format\n"
            "Respond with valid JSON only. No markdown, no explanation, no prose.\n"
            f"Schema:\n```json\n{schema.model_json_schema()}\n```"
        )

        from app.utils.coerce import as_float

        temp = as_float(config.temperature, 0.2)
        json_config = GenerationConfig(
            temperature=min(temp, 0.1),
            top_p=as_float(config.top_p, 0.95),
            top_k=int(as_float(config.top_k, 40)),
            max_output_tokens=int(as_float(config.max_output_tokens, 2048)),
            candidate_count=int(as_float(config.candidate_count, 1)),
        )

        response = await self.generate(json_system, messages, json_config)

        try:
            raw_dict = self._parse_json_text(response.text)
            parsed = schema.model_validate(raw_dict)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise VertexSchemaError(
                model=self._model_name,
                raw=response.text,
                detail=str(exc),
            ) from exc

        return GeminiResponse(
            text=response.text,
            parsed=parsed,
            model=self._model_name,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
        )

    async def stream(
        self,
        system_prompt: str,
        messages: list[PromptMessage],
        config: GenerationConfig = GenerationConfig(),
    ) -> AsyncIterator[StreamChunk]:
        """
        Yield token chunks as they arrive from the model.
        Raises VertexError subclasses on failure.
        """
        gen_cfg = self._build_gen_config(config)
        contents = [Part.from_text(m.content) for m in messages]

        model = self._model_for(system_prompt)
        try:
            stream = await asyncio.wait_for(
                model.generate_content_async(
                    contents,
                    generation_config=gen_cfg,
                    safety_settings=_SAFETY_SETTINGS,
                    stream=True,
                ),
                timeout=self._timeout,
            )
        except Exception as exc:
            raise self._translate_error(exc, self._model_name, self._timeout) from exc

        try:
            async for chunk in stream:
                self._check_safety(chunk)
                text = ""
                finish = None
                try:
                    text = chunk.text or ""
                except Exception:
                    pass
                try:
                    finish = chunk.candidates[0].finish_reason.name
                except Exception:
                    pass

                is_final = finish is not None and finish != "FINISH_REASON_UNSPECIFIED"
                in_tok, out_tok = self._extract_usage(chunk)
                yield StreamChunk(
                    text=text,
                    is_final=is_final,
                    finish_reason=finish,
                    usage={"input_tokens": in_tok, "output_tokens": out_tok},
                )
        except VertexSafetyError:
            raise
        except Exception as exc:
            raise self._translate_error(exc, self._model_name, self._timeout) from exc
