from __future__ import annotations
import time
import logging
from typing import Optional

import httpx
from .backend import LLMBackend, LLMResult

logger = logging.getLogger("gossip_engine.llm")


class OpenAIBackend(LLMBackend):
    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    @property
    def name(self) -> str:
        return f"openai-compat/{self.model}"

    def generate(self, prompt: str, temperature: float = 0.8, max_tokens: int = 1024) -> LLMResult:
        start = time.time()
        try:
            resp = self._client.post("/chat/completions", json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a code generator. Output ONLY the requested code. No explanation, no reasoning, no thinking."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            })
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content", "") or msg.get("reasoning", "")
            usage = data.get("usage", {})
            duration = (time.time() - start) * 1000
            return LLMResult(
                content=content.strip(),
                provider="openai-compat",
                model=self.model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                duration_ms=duration,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def test_connection(self) -> bool:
        try:
            resp = self._client.get("/models")
            return resp.status_code < 500
        except Exception:
            return False
