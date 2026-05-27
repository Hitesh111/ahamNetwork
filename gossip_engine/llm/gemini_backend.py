from __future__ import annotations
import time
import logging
import httpx
from .backend import LLMBackend, LLMResult

logger = logging.getLogger("gossip_engine.llm")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiBackend(LLMBackend):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=30.0)

    @property
    def name(self) -> str:
        return f"gemini/{self.model}"

    def generate(self, prompt: str, temperature: float = 0.8, max_tokens: int = 1024) -> LLMResult:
        start = time.time()
        try:
            url = f"{GEMINI_BASE}/models/{self.model}:generateContent?key={self.api_key}"
            resp = self._client.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            })
            resp.raise_for_status()
            data = resp.json()
            candidate = data["candidates"][0]
            content = candidate["content"]["parts"][0]["text"]
            duration = (time.time() - start) * 1000
            return LLMResult(
                content=content,
                provider="gemini",
                model=self.model,
                duration_ms=duration,
            )
        except Exception as e:
            logger.error(f"Gemini call failed: {e}")
            raise

    def test_connection(self) -> bool:
        try:
            url = f"{GEMINI_BASE}/models?key={self.api_key}"
            resp = self._client.get(url)
            return resp.status_code < 500
        except Exception:
            return False
