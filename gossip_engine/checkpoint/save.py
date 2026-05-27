from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..agent.model import Agent
from ..agent.state_machine import CognitiveState
from ..evolution.archive import ArchiveEntry


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _serialize_memory(memory) -> dict[str, Any]:
    data = {}
    for key, (value, expiry) in memory.snapshot().items():
        data[key] = {"value": _json_safe(value), "expiry": expiry}
    return data


def _serialize_agent(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "genome": agent.genome,
        "lineage_hash": agent.lineage_hash,
        "trust_score": agent.trust_score,
        "niche_coords": list(agent.niche_coords),
        "age": agent.age,
        "generation": agent.generation,
        "_prev_trust": agent._prev_trust,
        "neighbor_weights": dict(agent.neighbor_weights),
        "state_machine": {
            "state": agent.state_machine.state.value,
            "mutation_rates": {
                "sattva": agent.state_machine._mr[CognitiveState.SATTVA],
                "rajas": agent.state_machine._mr[CognitiveState.RAJAS],
                "tamas": agent.state_machine._mr[CognitiveState.TAMAS],
            },
            "recombination_rates": {
                "sattva": agent.state_machine._rr[CognitiveState.SATTVA],
                "rajas": agent.state_machine._rr[CognitiveState.RAJAS],
                "tamas": agent.state_machine._rr[CognitiveState.TAMAS],
            },
            "stagnation_counter": agent.state_machine.stagnation_counter,
            "success_counter": agent.state_machine.success_counter,
        },
        "l1_memory": _serialize_memory(agent.l1_memory),
    }


def _serialize_archive_entry(entry: ArchiveEntry) -> dict[str, Any]:
    return {
        "artifact_hash": entry.artifact_hash,
        "genome": entry.genome,
        "trust_score": entry.trust_score,
        "novelty_score": entry.novelty_score,
        "agent_id": entry.agent_id,
        "lineage_hash": entry.lineage_hash,
        "age": entry.age,
        "coords": list(entry.coords),
    }


def save_checkpoint(path: str | Path, orchestrator, round_index: int, solved: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "round_index": round_index,
        "solved": solved,
        "config": asdict(orchestrator.cfg),
        "generation": orchestrator.generation,
        "domain": {
            "prompt": orchestrator._domain_prompt,
            "test": orchestrator._domain_test,
            "module_path": getattr(orchestrator._domain_module, "__file__", ""),
        },
        "population": [_serialize_agent(agent) for agent in orchestrator.population.agents],
        "archive": [_serialize_archive_entry(entry) for entry in orchestrator.archive._cells.values()],
        "population_state": orchestrator.population.get_metrics(),
        "failure_window": list(orchestrator.population._failure_window),
        "rounds_since_improvement": orchestrator.population._rounds_since_improvement,
        "prev_best_trust": orchestrator.population._prev_best_trust,
        "artifact_store_path": getattr(orchestrator.artifact_store, "path", ""),
        "lineage_store_path": getattr(orchestrator.lineage_store, "path", ""),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path
