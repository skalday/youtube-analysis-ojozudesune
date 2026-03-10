import json

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Max chars to send in a single prompt (leave room for system prompt + response)
CHUNK_CHARS = 60_000


def _is_retryable(exc):
    return isinstance(exc, (anthropic.RateLimitError, anthropic.InternalServerError))


class ClaudeClient:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", max_tokens: int = 8096):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    @retry(
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.InternalServerError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
    )
    def _call(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    def analyze(self, system_prompt: str, user_prompt: str) -> str:
        """Single call to Claude. Returns raw text response."""
        return self._call(system_prompt, user_prompt)

    def analyze_json(self, system_prompt: str, user_prompt: str) -> dict | list | None:
        """
        Call Claude and parse the response as JSON.
        Returns parsed object or None on parse failure.
        """
        raw = self._call(system_prompt, user_prompt)
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            text = "\n".join(inner).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def chunk_texts(self, texts: list, max_chars: int = CHUNK_CHARS) -> list:
        """
        Split a list of texts into chunks that fit within max_chars.
        Returns list of combined-text strings.
        """
        chunks = []
        current = []
        current_len = 0

        for text in texts:
            text_len = len(text)
            if current_len + text_len > max_chars and current:
                chunks.append("\n\n---\n\n".join(current))
                current = []
                current_len = 0
            current.append(text)
            current_len += text_len

        if current:
            chunks.append("\n\n---\n\n".join(current))

        return chunks
