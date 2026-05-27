from __future__ import annotations
import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    rounds: int = 1000
    parallel: bool = False
    checkpoint_interval: int = 50
    checkpoint_dir: str = ".checkpoints"
    log_level: str = "INFO"
    seed: int = 42

    initial_population: int = 2
    initial_population_jitter: int = 1
    growth_check_interval: int = 10
    shrink_check_interval: int = 20
    growth_stagnation_rounds: int = 10
    growth_high_failure_rate: float = 0.5
    growth_shallow_lineage_depth: int = 5
    growth_archive_saturation_trust: float = 0.5
    shrink_plateau_rounds: int = 20
    shrink_trim_fraction: float = 0.2
    shrink_verification_pop: int = 3

    default_cognitive_state: str = "RAJAS"
    trust_init: float = 0.5
    trust_max: float = 1.0
    trust_min: float = 0.0
    neighbor_fanout: int = 3
    rumor_mill_size: int = 20

    mutation_rate_sattva: float = 0.05
    mutation_rate_rajas: float = 0.30
    mutation_rate_tamas: float = 0.50
    recombination_rate_sattva: float = 0.05
    recombination_rate_rajas: float = 0.30
    recombination_rate_tamas: float = 0.10

    archive_dimensions: int = 2
    archive_resolution: int = 10
    selection_epsilon: float = 0.3

    execution_timeout_ms: int = 5000
    max_output_size: int = 65536
    cache_max_size: int = 10000

    llm_provider: str = ""  # "" = no LLM (local mutations only)
    llm_model: str = ""
    llm_temperature: float = 0.8
    llm_max_tokens: int = 1024
    llm_fallback_enabled: bool = False

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    grok_api_key: str = ""
    grok_model: str = "grok-2-latest"
    local_base_url: str = ""
    local_model: str = "llama3.2"

    l1_ttl_default: int = 100
    l2_compaction_interval: int = 50
    l2_archive_threshold: float = 0.1
    l2_delete_threshold: float = 0.01
    l3_freeze_depth: int = 50
    l4_enabled: bool = False
    l5_enabled: bool = False

    trust_hop_decay: float = 0.9
    trust_propagation_factor: float = 0.05
    trust_decay_per_round: float = 0.001
    contradiction_threshold: float = 0.7

    workspace_novelty_sigma: float = 3.0
    workspace_trust_multiplier: float = 1.5
    workspace_broadcast_ttl: int = 3

    _domain_module: str = ""

    def resolve_llm_provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider
        if self.local_base_url:
            return "local"
        for candidate in ("openai", "gemini", "deepseek", "grok"):
            if getattr(self, f"{candidate}_api_key"):
                return candidate
        return ""

    def resolve_llm_model(self, provider: str | None = None) -> str:
        provider = provider or self.resolve_llm_provider()
        if provider == "openai":
            return self.openai_model or self.llm_model
        if provider == "gemini":
            return self.gemini_model or self.llm_model
        if provider == "deepseek":
            return self.deepseek_model or self.llm_model
        if provider == "grok":
            return self.grok_model or self.llm_model
        if provider == "local":
            return self.local_model or self.llm_model
        return self.llm_model

    @classmethod
    def load(cls, path: Optional[str] = None, validate: bool = True) -> "Config":
        c = cls()
        c._load_env()
        if path and Path(path).exists():
            c._load_file(path)
        if validate:
            c._validate()
        return c

    def _load_env(self):
        env_map = {
            "GOSSIP_ROUNDS": ("rounds", int),
            "GOSSIP_INITIAL_POPULATION": ("initial_population", int),
            "GOSSIP_LLM_PROVIDER": ("llm_provider", str),
            "GOSSIP_LLM_TEMPERATURE": ("llm_temperature", float),
            "GOSSIP_LLM_MAX_TOKENS": ("llm_max_tokens", int),
            "GOSSIP_OPENAI_KEY": ("openai_api_key", str),
            "GOSSIP_OPENAI_MODEL": ("openai_model", str),
            "GOSSIP_GEMINI_KEY": ("gemini_api_key", str),
            "GOSSIP_GEMINI_MODEL": ("gemini_model", str),
            "GOSSIP_DEEPSEEK_KEY": ("deepseek_api_key", str),
            "GOSSIP_DEEPSEEK_MODEL": ("deepseek_model", str),
            "GOSSIP_GROK_KEY": ("grok_api_key", str),
            "GOSSIP_GROK_MODEL": ("grok_model", str),
            "GOSSIP_LOCAL_BASE_URL": ("local_base_url", str),
            "GOSSIP_LOCAL_MODEL": ("local_model", str),
            "GOSSIP_DOMAIN": ("_domain_module", str),
            "GOSSIP_CHECKPOINT_DIR": ("checkpoint_dir", str),
            "GOSSIP_LOG_LEVEL": ("log_level", str),
            "GOSSIP_SEED": ("seed", int),
            "OPENAI_API_KEY": ("openai_api_key", str),
            "GEMINI_API_KEY": ("gemini_api_key", str),
            "DEEPSEEK_API_KEY": ("deepseek_api_key", str),
            "GROK_API_KEY": ("grok_api_key", str),
        }
        for env_key, (attr, typ) in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                setattr(self, attr, typ(val))

    def _load_file(self, path: str):
        p = Path(path)
        if p.suffix == ".json":
            data = json.loads(p.read_text())
        elif p.suffix in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(p.read_text())
        else:
            return
        if not data:
            return

        flat_data = dict(data)
        llm_block = flat_data.pop("llm", None)
        if isinstance(llm_block, dict):
            provider = llm_block.get("provider")
            if provider and not flat_data.get("llm_provider"):
                flat_data["llm_provider"] = provider
            for provider_name in ("openai", "gemini", "deepseek", "grok", "local"):
                provider_cfg = llm_block.get(provider_name)
                if isinstance(provider_cfg, dict):
                    key = provider_cfg.get("key")
                    model = provider_cfg.get("model")
                    base_url = provider_cfg.get("base_url")
                    if key is not None and hasattr(self, f"{provider_name}_api_key"):
                        setattr(self, f"{provider_name}_api_key", key)
                    if model is not None and hasattr(self, f"{provider_name}_model"):
                        setattr(self, f"{provider_name}_model", model)
                    if base_url is not None and provider_name == "local":
                        self.local_base_url = base_url

        for k, v in flat_data.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def _validate(self):
        provider = self.resolve_llm_provider()
        if not provider:
            return
        providers = {
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
            "deepseek": self.deepseek_api_key,
            "grok": self.grok_api_key,
            "local": True,
        }
        if provider not in providers:
            raise ValueError(f"Unknown LLM provider: {provider}. Choose: {list(providers.keys())}")
        if provider != "local" and not providers.get(provider):
            raise ValueError(
                f"LLM provider '{provider}' selected but no API key found. "
                f"Set {provider.upper()}_API_KEY or GOSSIP_{provider.upper()}_KEY."
            )
