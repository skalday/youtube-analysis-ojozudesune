from __future__ import annotations

import json
from abc import ABC, abstractmethod

CHUNK_CHARS = 60_000


class BaseLLMClient(ABC):
    """Common interface for all LLM backends."""

    @abstractmethod
    def analyze(self, system_prompt: str, user_prompt: str) -> str:
        """Single LLM call. Returns raw text response."""

    def analyze_json(self, system_prompt: str, user_prompt: str) -> dict | list | None:
        """Call LLM and parse response as JSON. Returns parsed object or None on failure."""
        raw = self.analyze(system_prompt, user_prompt)
        text = raw.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        import re
        m = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n```", text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def chunk_texts(self, texts: list, max_chars: int = CHUNK_CHARS) -> list:
        """Split a list of texts into chunks that fit within max_chars."""
        chunks = []
        current: list[str] = []
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
