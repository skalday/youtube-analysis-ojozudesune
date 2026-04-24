from __future__ import annotations

from openai import OpenAI

from modules.llm_providers.base import BaseLLMClient


class LocalLLMClient(BaseLLMClient):
    """LLM client for Ollama (or any OpenAI-compatible local endpoint)."""

    def __init__(
        self,
        model: str = "qwen2.5:latest",
        base_url: str = "http://localhost:11434/v1",
        max_tokens: int = 8096,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key="ollama", base_url=base_url)

    def analyze(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
