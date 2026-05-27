#!/usr/bin/env python3
from __future__ import annotations
import sys
import argparse
from pathlib import Path

from .config import Config
from .orchestrator import Orchestrator


def main():
    parser = argparse.ArgumentParser(
        description="Gossip Engine — evolutionary AI cognition substrate"
    )
    parser.add_argument("--domain", "-d", type=str, required=True,
                        help="Path to domain module (Python file)")
    parser.add_argument("--config", "-c", type=str, default="",
                        help="Config file (.json or .yaml)")
    parser.add_argument("--rounds", "-r", type=int, default=0,
                        help="Max rounds (overrides config)")
    parser.add_argument("--provider", "-p", type=str, default="",
                        help="LLM provider (overrides config)")
    parser.add_argument("--model", "-m", type=str, default="",
                        help="LLM model (overrides config)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose logging")
    args = parser.parse_args()

    config = Config.load(args.config or None, validate=False)

    if args.rounds:
        config.rounds = args.rounds
    if args.provider:
        config.llm_provider = args.provider
    if args.verbose:
        config.log_level = "DEBUG"
    if args.model:
        config.llm_model = args.model

    resolved_provider = config.resolve_llm_provider()
    if resolved_provider and not config.llm_provider:
        config.llm_provider = resolved_provider

    if args.model:
        if resolved_provider == "openai":
            config.openai_model = args.model
        elif resolved_provider == "gemini":
            config.gemini_model = args.model
        elif resolved_provider == "deepseek":
            config.deepseek_model = args.model
        elif resolved_provider == "grok":
            config.grok_model = args.model
        elif resolved_provider == "local":
            config.local_model = args.model

    config._validate()

    domain_path = Path(args.domain)
    if not domain_path.exists():
        print(f"Error: domain module not found: {args.domain}", file=sys.stderr)
        sys.exit(1)

    orch = Orchestrator(config)
    orch.load_domain(args.domain)

    print(f"=== Gossip Engine ===")
    provider = config.resolve_llm_provider()
    if provider:
        print(f"Provider: {provider}")
        print(f"Model: {config.resolve_llm_model(provider)}")
    else:
        print(f"Provider: none (local mutations only)")
    print(f"Domain: {domain_path.name}")
    print(f"Rounds: {config.rounds}")
    print(f"Initial pop: {config.initial_population}-{config.initial_population + config.initial_population_jitter}")
    print()

    result = orch.run()

    print()
    print("=== Results ===")
    print(f"  Rounds:         {result['rounds']}")
    print(f"  Time:           {result['elapsed_seconds']:.1f}s")
    print(f"  Final pop:      {result['population_size']}")
    print(f"  Archive cells:  {result['archive_cells']}")
    print(f"  Max trust:      {result['max_trust']:.3f}")
    print(f"  Solved:         {result['solved']}")
    if result['best_genome']:
        print()
        print("Best genome:")
        print(result['best_genome'][:500])


if __name__ == "__main__":
    main()
