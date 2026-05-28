#!/usr/bin/env python3
from __future__ import annotations
import sys
import argparse
from pathlib import Path

from .config import Config
from .cli import run_interactive, _print_summary
from .problem_studio import run_problem_studio
from .orchestrator import Orchestrator


def main():
    parser = argparse.ArgumentParser(
        description="Gossip Engine — evolutionary AI cognition substrate"
    )
    parser.add_argument("--domain", "-d", type=str, default="",
                        help="Path to domain module (Python file)")
    parser.add_argument("--config", "-c", type=str, default="",
                        help="Config file (.json or .yaml)")
    parser.add_argument("--rounds", "-r", type=int, default=0,
                        help="Max rounds (overrides config)")
    parser.add_argument("--provider", "-p", type=str, default="",
                        help="LLM provider (overrides config)")
    parser.add_argument("--model", "-m", type=str, default="",
                        help="LLM model (overrides config)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Open an interactive CLI after initialization")
    parser.add_argument("--studio", action="store_true",
                        help="Launch the structured problem-definition studio")
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

    domain_value = args.domain
    studio_mode = bool(args.studio or (args.interactive and not domain_value))
    if studio_mode:
        if not sys.stdin.isatty():
            print("Error: structured problem studio requires an interactive terminal.", file=sys.stderr)
            sys.exit(1)
        generated_domain = run_problem_studio(config)
        if not generated_domain:
            sys.exit(1)
        domain_value = generated_domain
    if not domain_value:
        print("Error: domain module not provided. Use --domain, --interactive, or --studio.", file=sys.stderr)
        sys.exit(1)

    domain_path = Path(domain_value)
    if not domain_path.exists():
        print(f"Error: domain module not found: {domain_value}", file=sys.stderr)
        sys.exit(1)

    orch = Orchestrator(config)
    orch.load_domain(domain_value)

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

    if args.interactive and not studio_mode:
        run_interactive(orch, default_step_rounds=max(1, args.rounds or 1))
        return

    result = orch.run()

    print()
    _print_summary(result)


if __name__ == "__main__":
    main()
