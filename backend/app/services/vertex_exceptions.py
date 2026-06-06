"""
Vertex AI exception hierarchy for MathMentor.

All internal Vertex errors are translated into one of these typed exceptions
so callers never need to import google-cloud-aiplatform directly.
"""


class VertexError(Exception):
    """Base for all Vertex AI / Gemini errors."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class VertexTimeoutError(VertexError):
    """Request exceeded its timeout budget."""

    def __init__(self, model: str, timeout_s: float) -> None:
        super().__init__(
            f"Gemini model '{model}' timed out after {timeout_s}s",
            retryable=True,
        )
        self.model = model
        self.timeout_s = timeout_s


class VertexQuotaError(VertexError):
    """429 / quota exceeded — back off and retry."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(f"Vertex AI quota exceeded: {detail}", retryable=True)


class VertexSchemaError(VertexError):
    """Model returned output that failed JSON / Pydantic validation."""

    def __init__(self, model: str, raw: str, detail: str = "") -> None:
        super().__init__(
            f"Schema validation failed for model '{model}': {detail} | raw={raw[:200]}",
            retryable=True,  # worth one retry with stricter prompt
        )
        self.raw = raw


class VertexSafetyError(VertexError):
    """Response was blocked by Gemini safety filters."""

    def __init__(self, reason: str = "") -> None:
        super().__init__(f"Response blocked by safety filter: {reason}", retryable=False)
        self.reason = reason


class VertexUnavailableError(VertexError):
    """503 / 502 — transient backend error."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(f"Vertex AI unavailable: {detail}", retryable=True)


class VertexAuthError(VertexError):
    """401 / credential error — non-retryable, needs operator action."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(f"Vertex AI auth error: {detail}", retryable=False)


class VertexApiDisabledError(VertexError):
    """Vertex AI API not enabled on the GCP project — enable in Cloud Console."""

    def __init__(self, project: str, activation_url: str = "") -> None:
        msg = (
            f"Vertex AI API (aiplatform.googleapis.com) is not enabled for project "
            f"'{project}'. Enable it in Google Cloud Console"
        )
        if activation_url:
            msg += f": {activation_url}"
        super().__init__(msg, retryable=False)
        self.project = project
        self.activation_url = activation_url
