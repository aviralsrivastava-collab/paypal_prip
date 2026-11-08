from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from backend.schemas.diagnosis import RawDiagnosisPayload

if TYPE_CHECKING:
    from backend.integrations.ai.context import DiagnosisPromptContext


class AIProviderError(Exception):
    """Base exception for AI provider failures."""

    pass


class AIProviderTimeoutError(AIProviderError):
    """Raised when an AI provider call times out."""

    pass


class AIProviderRateLimitError(AIProviderError):
    """Raised when an AI provider returns HTTP 429 Too Many Requests."""

    pass


class AIProviderOutageError(AIProviderError):
    """Raised when an AI provider returns 5xx or connection refused."""

    pass


class AIStructuredOutputError(AIProviderError):
    """Raised when the AI provider returns unparseable or schema-invalid JSON."""

    pass


class AIProviderInterface(ABC):
    """
    Abstract interface for AI diagnostic providers.
    Isolates external model SDKs and HTTP clients from business logic.
    """

    provider_name: str
    model_name: str
    prompt_version: str

    @abstractmethod
    def generate_diagnosis(self, prompt_context: "DiagnosisPromptContext") -> RawDiagnosisPayload:  # type: ignore[name-defined]
        """
        Generates a schema-validated diagnosis from normalized inspection context.
        Raises AIProviderError subclasses on operational or formatting failures.
        """
        raise NotImplementedError
