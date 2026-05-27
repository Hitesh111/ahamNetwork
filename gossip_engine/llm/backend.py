from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResult:
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0


class LLMBackend(ABC):
    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.8, max_tokens: int = 1024) -> LLMResult:
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...


def create_backend(provider: str, config) -> LLMBackend:
    if provider == "openai":
        from .openai_backend import OpenAIBackend
        return OpenAIBackend(api_key=config.openai_api_key, model=config.openai_model, base_url=None)
    elif provider == "gemini":
        from .gemini_backend import GeminiBackend
        return GeminiBackend(api_key=config.gemini_api_key, model=config.gemini_model)
    elif provider == "deepseek":
        from .openai_backend import OpenAIBackend
        return OpenAIBackend(
            api_key=config.deepseek_api_key,
            model=config.deepseek_model,
            base_url="https://api.deepseek.com/v1",
        )
    elif provider == "grok":
        from .openai_backend import OpenAIBackend
        return OpenAIBackend(
            api_key=config.grok_api_key,
            model=config.grok_model,
            base_url="https://api.x.ai/v1",
        )
    elif provider == "local":
        from .ollama_backend import OllamaBackend
        return OllamaBackend(
            model=config.local_model,
            base_url=(config.local_base_url or "http://localhost:11434").rstrip("/v1").rstrip("/"),
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
