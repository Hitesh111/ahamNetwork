from __future__ import annotations
import time
import logging
import httpx
from .backend import LLMBackend, LLMResult

logger = logging.getLogger("gossip_engine.llm")


class OllamaBackend(LLMBackend):
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=120.0)

    @property
    def name(self) -> str:
        return f"ollama/{self.model}"

    def generate(self, prompt: str, temperature: float = 0.8, max_tokens: int = 1024) -> LLMResult:
        start = time.time()
        try:
            resp = self._client.post(f"{self.base_url}/api/generate", json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            })
            resp.raise_for_status()
            data = resp.json()
            content = data.get("response", "")
            duration = (time.time() - start) * 1000
            return LLMResult(
                content=content.strip(),
                provider="ollama",
                model=self.model,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
                duration_ms=duration,
            )
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            raise

    def test_connection(self) -> bool:
        try:
            resp = self._client.get(f"{self.base_url}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False
