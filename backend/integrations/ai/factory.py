from typing import Optional

from backend.core.config import get_settings
from backend.integrations.ai.base import AIProviderInterface
from backend.integrations.ai.mock_provider import MockAIProvider


def get_ai_provider(provider_override: Optional[str] = None) -> AIProviderInterface:
    """
    Factory function returning the configured AI provider.
    Defaults to deterministic MockAIProvider for offline testing and local development.
    """
    settings = get_settings()
    provider_name = (provider_override or settings.ai_provider or "mock").lower()

    if provider_name == "mock":
        return MockAIProvider(
            provider_name="mock",
            model_name=settings.ai_model,
            prompt_version=settings.ai_prompt_version,
        )

    # Live external providers can be added here (e.g. OpenAI, Google Gemini)
    # Default fallback to mock provider to preserve sandbox and test isolation
    return MockAIProvider(
        provider_name=provider_name,
        model_name=settings.ai_model,
        prompt_version=settings.ai_prompt_version,
    )
