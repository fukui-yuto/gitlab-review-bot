from __future__ import annotations

from typing import TYPE_CHECKING

from google import genai
from google.genai import types

from review_bot.services.llm.base import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from review_bot.core.config import Settings


class GeminiProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._model = settings.llm.gemini.model
        api_key = settings.llm.gemini.api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=api_key)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
    ) -> LLMResponse:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
        )
        text = response.text or ""
        input_tokens = None
        output_tokens = None
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
        return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
