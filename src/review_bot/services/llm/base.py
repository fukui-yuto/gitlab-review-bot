from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
    ) -> LLMResponse: ...
