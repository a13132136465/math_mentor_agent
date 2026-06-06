"""DeepSeek API exception hierarchy — mirrors VertexError shape for shared retry logic."""

from app.services.vertex_exceptions import VertexError


class DeepSeekError(VertexError):
    """Base for all DeepSeek API errors."""


class DeepSeekTimeoutError(DeepSeekError):
    def __init__(self, model: str, timeout_s: float) -> None:
        super().__init__(
            f"DeepSeek model '{model}' timed out after {timeout_s}s",
            retryable=True,
        )
        self.model = model
        self.timeout_s = timeout_s


class DeepSeekQuotaError(DeepSeekError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(f"DeepSeek quota exceeded: {detail}", retryable=True)


class DeepSeekSchemaError(DeepSeekError):
    def __init__(self, model: str, raw: str, detail: str = "") -> None:
        super().__init__(
            f"Schema validation failed for model '{model}': {detail} | raw={raw[:200]}",
            retryable=True,
        )
        self.raw = raw


class DeepSeekUnavailableError(DeepSeekError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(f"DeepSeek API unavailable: {detail}", retryable=True)


class DeepSeekAuthError(DeepSeekError):
    def __init__(self, detail: str = "") -> None:
        super().__init__(f"DeepSeek auth error: {detail}", retryable=False)
