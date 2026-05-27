from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from ..agent.model import Agent
from ..agent.state_machine import CognitiveState, StateMachine
from ..config import Config
from ..evolution.archive import ArchiveEntry
from ..memory.l1_agent_local import AgentLocalMemory


def _restore_memory(payload: dict[str, Any]) -> AgentLocalMemory:
    memory = AgentLocalMemory()
    snapshot = {}
    for key, item in payload.items():
        snapshot[key] = (item["value"], item["expiry"])
    memory.restore(snapshot)
    return memory


def _restore_agent(payload: dict[str, Any]) -> Agent:
    rates = payload["state_machine"]["mutation_rates"]
    recombination_rates = payload["state_machine"]["recombination_rates"]
    state_machine = StateMachine(
        initial=CognitiveState(payload["state_machine"]["state"]),
        mutation_rate_sattva=rates["sattva"],
        mutation_rate_rajas=rates["rajas"],
        mutation_rate_tamas=rates["tamas"],
        recombination_rate_sattva=recombination_rates["sattva"],
        recombination_rate_rajas=recombination_rates["rajas"],
        recombination_rate_tamas=recombination_rates["tamas"],
    )
    state_machine.stagnation_counter = payload["state_machine"]["stagnation_counter"]
    state_machine.success_counter = payload["state_machine"]["success_counter"]
    agent = Agent(
        id=payload["id"],
        genome=payload["genome"],
        lineage_hash=payload["lineage_hash"],
        trust_score=payload["trust_score"],
        niche_coords=tuple(payload["niche_coords"]),
        l1_memory=_restore_memory(payload["l1_memory"]),
        state_machine=state_machine,
        neighbor_weights=dict(payload["neighbor_weights"]),
        age=payload["age"],
        generation=payload["generation"],
        _prev_trust=payload["_prev_trust"],
    )
    return agent


def load_checkpoint(path: str | Path):
    from ..evolution.archive import MAPElitesArchive
    from ..orchestrator import Orchestrator

    path = Path(path)
    data = json.loads(path.read_text())
    config = Config(**data["config"])
    orchestrator = Orchestrator(config)
    orchestrator.generation = data["generation"]
    domain_path = data.get("domain", {}).get("module_path", "")
    if domain_path and Path(domain_path).exists():
        orchestrator.load_domain(domain_path)
    else:
        orchestrator._domain_prompt = data.get("domain", {}).get("prompt", "")
        orchestrator._domain_test = data.get("domain", {}).get("test", "")

    orchestrator.population.agents = [_restore_agent(agent) for agent in data["population"]]
    orchestrator.population._failure_window = list(data.get("failure_window", []))
    orchestrator.population._rounds_since_improvement = data.get("rounds_since_improvement", 0)
    orchestrator.population._prev_best_trust = data.get("prev_best_trust", 0.0)

    archive = MAPElitesArchive(
        dimensions=config.archive_dimensions,
        resolution=config.archive_resolution,
    )
    for entry in data["archive"]:
        archive._cells[tuple(entry["coords"])] = ArchiveEntry(
            artifact_hash=entry.get("artifact_hash", ""),
            genome=entry["genome"],
            trust_score=entry["trust_score"],
            novelty_score=entry["novelty_score"],
            agent_id=entry["agent_id"],
            lineage_hash=entry["lineage_hash"],
            age=entry["age"],
            coords=tuple(entry["coords"]),
        )
    orchestrator.archive = archive
    return orchestrator
