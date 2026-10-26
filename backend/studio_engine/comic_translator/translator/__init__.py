"""Translation provider factory."""

from __future__ import annotations

from comic_translator.config import TranslatorConfig
from comic_translator.exceptions import TranslationError
from comic_translator.translator.base import TranslationProvider
from comic_translator.translator.custom_provider import CustomProvider
from comic_translator.translator.gemini_provider import GeminiProvider
from comic_translator.translator.openrouter_provider import OpenRouterProvider


def create_provider(config: TranslatorConfig) -> TranslationProvider:
    """Create the appropriate translation provider based on config."""
    providers = {
        "custom": lambda: CustomProvider(config),
        "gemini": lambda: GeminiProvider(config),
        "openrouter": lambda: OpenRouterProvider(config),
    }

    factory = providers.get(config.provider)
    if factory is None:
        raise TranslationError(
            f"Unknown provider: {config.provider!r}. "
            f"Available: {', '.join(providers.keys())}"
        )
    return factory()
