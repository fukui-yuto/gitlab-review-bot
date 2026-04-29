from __future__ import annotations

from typing import TYPE_CHECKING

import openai

from review_bot.services.llm.base import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from review_bot.core.config import Settings


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._model = settings.llm.openai.model
        api_key = settings.llm.openai.api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        kwargs: dict[str, str] = {"api_key": api_key}
        if settings.llm.openai.base_url:
            kwargs["base_url"] = settings.llm.openai.base_url
        self._client = openai.AsyncOpenAI(**kwargs)

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        text = response.choices[0].message.content or ""
        input_tokens = None
        output_tokens = None
        if response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
        return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
