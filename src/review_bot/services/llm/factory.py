from __future__ import annotations

from typing import TYPE_CHECKING

from review_bot.services.llm.base import LLMProvider

if TYPE_CHECKING:
    from review_bot.core.config import Settings


def build_llm_provider(settings: Settings) -> LLMProvider:
    match settings.llm.effective_provider:
        case "gemini":
            from review_bot.services.llm.gemini import GeminiProvider

            return GeminiProvider(settings)
        case "openai":
            from review_bot.services.llm.openai_provider import OpenAIProvider

            return OpenAIProvider(settings)
        case "mock":
            from review_bot.services.llm.mock_provider import MockProvider

            return MockProvider()
        case other:
            raise ValueError(f"Unknown LLM provider: {other}")
