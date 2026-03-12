import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from analyzers.base_client import BaseLLMClient


def _is_retryable(exc):
    return isinstance(exc, (anthropic.RateLimitError, anthropic.InternalServerError))


class ClaudeClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", max_tokens: int = 8096):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    @retry(
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.InternalServerError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
    )
    def analyze(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
