from __future__ import annotations
import re as _re
import shlex
from typing import Any

from .checkpoint.save import save_checkpoint
from .utils.display import (
    format_agent_table,
    format_archive_heatmap,
    format_kv,
    format_population_states,
    format_top_archive_entries,
    shorten,
)


def _print_summary(result: dict[str, Any]) -> None:
    print("=== Results ===")
    print(f"  Rounds:         {result['rounds']}")
    print(f"  Time:           {result['elapsed_seconds']:.1f}s")
    print(f"  Final pop:      {result['population_size']}")
    print(f"  Archive cells:  {result['archive_cells']}")
    print(f"  Max trust:      {result['max_trust']:.3f}")
    print(f"  Solved:         {result['solved']}")
    if result.get("best_genome"):
        print()
        print("Best genome:")
        print(result["best_genome"][:500])


def _status_block(orch) -> str:
    snapshot = orch.status_snapshot()
    elite_hash = snapshot["best_hash"] or "-"
    summary = {
        "round": snapshot["generation"],
        "population": snapshot["population_size"],
        "archive_cells": snapshot["archive_cells"],
        "archive_occupancy": f"{snapshot['archive_occupancy']:.2f}",
        "max_trust": f"{snapshot['max_trust']:.3f}",
        "pending_gossip": snapshot["gossip_pending"],
        "best_hash": shorten(elite_hash),
    }
    return format_kv(summary)


def print_status(orch) -> None:
    snapshot = orch.status_snapshot()
    print("=== Status ===")
    print(_status_block(orch))
    print()
    print("Population states")
    print(format_population_states(snapshot["population_states"]))
    print()
    print("Archive heatmap")
    print(format_archive_heatmap(orch.archive))
    print()
    print("Top archive entries")
    print(format_top_archive_entries(orch.archive, limit=5))
    print()
    print("Agents")
    print(format_agent_table(snapshot["agents"]))


def print_elite(orch) -> None:
    elite = orch.archive.get_elite()
    if elite is None:
        print("(archive empty)")
        return
    print("=== Elite ===")
    print(format_kv(
        {
            "hash": elite.artifact_hash or "-",
            "trust": f"{elite.trust_score:.3f}",
            "novelty": f"{elite.novelty_score:.3f}",
            "cell": elite.coords,
            "age": elite.age,
            "lineage": elite.lineage_hash or "-",
        }
    ))
    print()
    print(elite.genome[:2000])


def print_lineage(orch, artifact_hash: str) -> None:
    node = orch.lineage_store.get_node(artifact_hash)
    if node is None:
        print(f"No lineage node found for {artifact_hash}")
        return
    stats = orch.lineage_store.get_lineage_stats(artifact_hash)
    ancestors = orch.lineage_store.get_ancestors(artifact_hash, depth=8)
    descendants = orch.lineage_store.get_descendants(artifact_hash, depth=8)
    print("=== Lineage ===")
    print(format_kv(
        {
            "artifact": stats["artifact_hash"],
            "depth": stats["depth"],
            "nodes": stats["nodes"],
            "branches": stats["branches"],
            "avg_trust": f"{stats['avg_trust']:.3f}",
            "max_trust": f"{stats['max_trust']:.3f}",
            "frozen": node.frozen,
            "compressed": node.compressed,
        }
    ))
    print()
    print("Ancestors")
    for item in ancestors[:8]:
        print(f"  {shorten(item.artifact_hash)} depth={item.lineage_depth} trust={item.trust_score:.3f} type={item.mutation_type}")
    print()
    print("Descendants")
    for item in descendants[:8]:
        print(f"  {shorten(item.artifact_hash)} depth={item.lineage_depth} trust={item.trust_score:.3f} type={item.mutation_type}")


def print_help() -> None:
    print(
        "\n".join(
            [
                "Commands:",
                "  status / s                      Show population, archive, and gossip summaries",
                "  run [n] / step [n] / tick [n]   Advance n rounds (default 1)",
                "  elite / best                    Show the best archive entry",
                "  archive [n]                     Show the top n archive entries",
                "  agents / pop                    Show agent gossip/state table",
                "  lineage <hash>                  Show lineage stats for an artifact hash",
                "  save                            Write a checkpoint to disk",
                "  help / ?                        Show this help",
                "  quit / exit / q                 Leave interactive mode",
                "",
                "Natural language examples:",
                "  run 10 rounds",
                "  show me the best solution",
                "  what's the status",
                "  advance 5 steps",
            ]
        )
    )


def _parse_natural_command(raw: str) -> tuple[str, list[str]]:
    """Parse a natural language input into command + args."""
    raw_lower = raw.lower().strip()

    aliases: dict[str, str] = {
        "show me the best solution": "elite",
        "what's the best": "elite",
        "show elite": "elite",
        "show best": "elite",
        "what is the status": "status",
        "what's the status": "status",
        "show status": "status",
        "show me the status": "status",
        "what are the agents": "agents",
        "show agents": "agents",
        "show pop": "agents",
        "show population": "agents",
    }

    for phrase, cmd in aliases.items():
        if raw_lower.strip() == phrase:
            return cmd, []

    patterns: list[tuple[str, str]] = [
        (_re.compile(r"run\s+(\d+)(?:\s*rounds?)?"), "run"),
        (_re.compile(r"run\s+(\d+)\s*steps?"), "run"),
        (_re.compile(r"advance\s+(\d+)"), "run"),
        (_re.compile(r"step\s+(\d+)"), "run"),
        (_re.compile(r"tick\s+(\d+)"), "run"),
        (_re.compile(r"archive\s+(\d+)"), "archive"),
        (_re.compile(r"lineage\s+(\S+)"), "lineage"),
    ]

    for pattern, command in patterns:
        m = pattern.match(raw_lower)
        if m:
            return command, [m.group(1)]

    return raw, []


def run_interactive(orch, default_step_rounds: int = 1) -> None:
    print("Interactive mode. Type 'help' for commands, or just chat naturally.")
    print("Examples: run 10 rounds, show best, what's the status")
    if not orch.population.agents:
        orch.population.initialize()
        orch._seed_population()
        orch._sync_gossip_state()
    print_status(orch)
    while True:
        try:
            raw = input("gossip> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            raw = "status"

        command, args = _parse_natural_command(raw)
        parts = _re.split(r"\s+", raw.strip().lower()) if command == raw else [command] + args
        if not parts:
            continue

        command = parts[0].lower()
        args = parts[1:]

        if command in {"quit", "exit"}:
            break
        if command in {"help", "?"}:
            print_help()
            continue
        if command in {"status", "s"}:
            print_status(orch)
            continue
        if command in {"elite"}:
            print_elite(orch)
            continue
        if command in {"archive"}:
            limit = int(args[0]) if args else 5
            print(format_top_archive_entries(orch.archive, limit=limit))
            continue
        if command in {"agents"}:
            print(format_agent_table(orch.status_snapshot()["agents"]))
            continue
        if command in {"lineage"}:
            if not args:
                elite = orch.archive.get_elite()
                if elite is None:
                    print("(archive empty)")
                    continue
                args = [elite.artifact_hash]
            print_lineage(orch, args[0])
            continue
        if command in {"save"}:
            snapshot = orch.status_snapshot()
            path = save_checkpoint(orch.checkpoint_path, orch, orch.generation, bool(snapshot["solved"]))
            print(f"Checkpoint saved: {path}")
            continue
        if command in {"run", "step", "tick"}:
            rounds = int(args[0]) if args else max(1, default_step_rounds)
            result = orch.run(rounds=max(1, rounds))
            _print_summary(result)
            continue

        print(f"Unknown command: {command}")
        print_help()
