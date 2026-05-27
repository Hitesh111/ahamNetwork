from __future__ import annotations
import random
import time
from collections import defaultdict
from typing import Any, Iterable, Sequence

from ..agent.state_machine import CognitiveState
from ..evolution.archive import ArchiveEntry
from ..utils.ids import content_hash


def artifact_priority(artifact: dict[str, Any]) -> float:
    trust = float(artifact.get("trust_score", 0.0))
    novelty = float(artifact.get("novelty_score", 0.0))
    hop_count = int(artifact.get("hop_count", 0))
    return (trust * (1.0 + novelty)) / max(1.0, 1.0 + 0.1 * hop_count)


def make_artifact(
    *,
    artifact_hash: str,
    genome: str,
    trust_score: float,
    novelty_score: float,
    lineage_hash: str = "",
    niche_coords: Sequence[int] = (),
    origin_agent_id: str = "",
    cognitive_state: str = "",
    behavior: Sequence[float] = (),
    codebook_indices: Sequence[int] = (),
    mutation_type: str = "",
    passed: bool | None = None,
    score: float | None = None,
    runtime_ms: float | None = None,
    output: str = "",
    error: str | None = None,
    source: str = "live",
    hop_count: int = 0,
    last_sender_id: str = "",
) -> dict[str, Any]:
    return {
        "artifact_hash": artifact_hash,
        "genome": genome,
        "trust_score": float(trust_score),
        "novelty_score": float(novelty_score),
        "lineage_hash": lineage_hash,
        "niche_coords": [int(v) for v in niche_coords],
        "origin_agent_id": origin_agent_id,
        "cognitive_state": cognitive_state,
        "behavior": [float(v) for v in behavior],
        "codebook_indices": [int(v) for v in codebook_indices],
        "mutation_type": mutation_type,
        "passed": passed,
        "score": score,
        "runtime_ms": runtime_ms,
        "output": output,
        "error": error,
        "source": source,
        "hop_count": int(hop_count),
        "timestamp": time.time(),
        "last_sender_id": last_sender_id,
    }


def artifact_from_entry(entry: ArchiveEntry, cognitive_state: str = "", source: str = "archive") -> dict[str, Any]:
    return make_artifact(
        artifact_hash=entry.artifact_hash or content_hash(entry.genome),
        genome=entry.genome,
        trust_score=entry.trust_score,
        novelty_score=entry.novelty_score,
        lineage_hash=entry.lineage_hash,
        niche_coords=entry.coords,
        origin_agent_id=entry.agent_id,
        cognitive_state=cognitive_state,
        source=source,
    )


def artifact_from_agent(agent, *, novelty_score: float, behavior: Sequence[float], mutation_type: str, passed: bool, score: float, runtime_ms: float, output: str, error: str | None, source: str = "live") -> dict[str, Any]:
    return make_artifact(
        artifact_hash=content_hash(agent.genome),
        genome=agent.genome,
        trust_score=agent.trust_score,
        novelty_score=novelty_score,
        lineage_hash=agent.lineage_hash,
        niche_coords=agent.niche_coords,
        origin_agent_id=agent.id,
        cognitive_state=agent.cognitive_state.value,
        behavior=behavior,
        mutation_type=mutation_type,
        passed=passed,
        score=score,
        runtime_ms=runtime_ms,
        output=output,
        error=error,
        source=source,
    )


class GossipBus:
    def __init__(self, fanout: int = 3, rumor_limit: int = 20, exploration_rate: float = 0.3):
        self.fanout = fanout
        self.rumor_limit = rumor_limit
        self.exploration_rate = exploration_rate
        self._pending: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def sync_population(self, agents: Sequence[Any]) -> None:
        active_ids = {agent.id for agent in agents}
        for agent in agents:
            if not isinstance(getattr(agent, "rumor_mill", None), dict):
                agent.rumor_mill = {}
            if not isinstance(getattr(agent, "outgoing_messages", None), list):
                agent.outgoing_messages = []
            if not isinstance(getattr(agent, "neighbor_weights", None), dict):
                agent.neighbor_weights = {}
            if getattr(agent, "gossip_enabled", True) is None:
                agent.gossip_enabled = True

            for peer in active_ids:
                if peer == agent.id:
                    continue
                agent.neighbor_weights.setdefault(peer, 1.0)

            for peer in list(agent.neighbor_weights):
                if peer not in active_ids or peer == agent.id:
                    agent.neighbor_weights.pop(peer, None)

            self._trim_rumor_mill(agent)

        for recipient in list(self._pending):
            if recipient not in active_ids:
                self._pending.pop(recipient, None)

    def snapshot(self) -> dict[str, Any]:
        return {
            "fanout": self.fanout,
            "rumor_limit": self.rumor_limit,
            "exploration_rate": self.exploration_rate,
            "pending": {recipient: [dict(message) for message in messages] for recipient, messages in self._pending.items()},
        }

    def restore(self, snapshot: dict[str, Any] | None) -> None:
        snapshot = snapshot or {}
        self.fanout = int(snapshot.get("fanout", self.fanout))
        self.rumor_limit = int(snapshot.get("rumor_limit", self.rumor_limit))
        self.exploration_rate = float(snapshot.get("exploration_rate", self.exploration_rate))
        pending = snapshot.get("pending", {})
        self._pending = defaultdict(list)
        for recipient, messages in pending.items():
            self._pending[recipient] = [dict(message) for message in messages]

    def pending_count(self) -> int:
        return sum(len(messages) for messages in self._pending.values())

    def drain(self, recipient_id: str) -> list[dict[str, Any]]:
        messages = self._pending.pop(recipient_id, [])
        return [dict(message) for message in messages]

    def _trim_rumor_mill(self, agent) -> None:
        if len(agent.rumor_mill) <= self.rumor_limit:
            return
        ordered = sorted(agent.rumor_mill.values(), key=artifact_priority, reverse=True)
        agent.rumor_mill = {entry["artifact_hash"]: entry for entry in ordered[: self.rumor_limit]}

    def ingest(self, agent, messages: Iterable[dict[str, Any]]) -> None:
        for message in messages:
            artifact = dict(message)
            artifact_hash = artifact.get("artifact_hash") or content_hash(str(artifact.get("genome", "")))
            artifact["artifact_hash"] = artifact_hash
            artifact["hop_count"] = int(artifact.get("hop_count", 0))
            existing = agent.rumor_mill.get(artifact_hash)
            if existing is None or artifact_priority(artifact) >= artifact_priority(existing):
                agent.rumor_mill[artifact_hash] = artifact

            sender_id = artifact.get("last_sender_id") or artifact.get("origin_agent_id") or ""
            if sender_id and sender_id in agent.neighbor_weights:
                current = float(agent.neighbor_weights.get(sender_id, 1.0))
                if artifact_priority(artifact) >= float(agent.trust_score):
                    agent.neighbor_weights[sender_id] = min(8.0, current + 0.1)
                else:
                    agent.neighbor_weights[sender_id] = max(0.05, current * 0.995)

        self._trim_rumor_mill(agent)

    def best_rumor(self, agent) -> dict[str, Any] | None:
        if not agent.rumor_mill:
            return None
        return max(agent.rumor_mill.values(), key=artifact_priority)

    def select_recipients(self, agent, agents: Sequence[Any]) -> list[str]:
        peers = [
            other
            for other in agents
            if other.id != agent.id and getattr(other, "gossip_enabled", True) and other.cognitive_state != CognitiveState.TAMAS
        ]
        if not peers:
            return []
        fanout = min(self.fanout, len(peers))
        weights = [max(0.05, float(agent.neighbor_weights.get(peer.id, 1.0))) for peer in peers]
        if random.random() < max(0.0, min(1.0, 1.0 - self.exploration_rate)):
            ranked = sorted(zip(peers, weights), key=lambda item: item[1], reverse=True)
            pool = ranked[: max(fanout, min(len(ranked), fanout * 2))]
            if not pool:
                return []
            return self._weighted_sample([peer.id for peer, _ in pool], [weight for _, weight in pool], fanout)
        return [peer.id for peer in random.sample(peers, fanout)]

    @staticmethod
    def _weighted_sample(candidates: Sequence[str], weights: Sequence[float], k: int) -> list[str]:
        pool = list(zip(candidates, weights))
        chosen: list[str] = []
        while pool and len(chosen) < k:
            total = sum(max(0.0, weight) for _, weight in pool)
            if total <= 0:
                chosen.extend([candidate for candidate, _ in pool[: k - len(chosen)]])
                break
            pivot = random.random() * total
            running = 0.0
            for index, (candidate, weight) in enumerate(pool):
                running += max(0.0, weight)
                if running >= pivot:
                    chosen.append(candidate)
                    pool.pop(index)
                    break
        return chosen[:k]

    def emit(self, agent, artifact: dict[str, Any], agents: Sequence[Any]) -> list[str]:
        recipients = self.select_recipients(agent, agents)
        if not recipients:
            return []

        payload = dict(artifact)
        payload["hop_count"] = int(payload.get("hop_count", 0)) + 1
        payload["last_sender_id"] = agent.id
        payload["timestamp"] = time.time()

        for recipient in recipients:
            self._pending[recipient].append(dict(payload))

        agent.outgoing_messages.append(
            {
                "artifact_hash": payload["artifact_hash"],
                "recipients": list(recipients),
                "trust_score": payload.get("trust_score", 0.0),
                "timestamp": payload["timestamp"],
            }
        )
        if len(agent.outgoing_messages) > self.rumor_limit:
            agent.outgoing_messages = agent.outgoing_messages[-self.rumor_limit :]
        return recipients

    def seed_from_archive(self, agents: Sequence[Any], archive) -> None:
        elite = archive.get_elite()
        if elite is None:
            return
        for agent in agents:
            if not agent.rumor_mill:
                entry = artifact_from_entry(elite, cognitive_state=agent.cognitive_state.value, source="archive")
                agent.rumor_mill[entry["artifact_hash"]] = entry

    def describe_agent(self, agent) -> dict[str, Any]:
        best = self.best_rumor(agent)
        return {
            "agent_id": agent.id,
            "state": agent.cognitive_state.value,
            "trust_score": agent.trust_score,
            "neighbors": len(agent.neighbor_weights),
            "rumors": len(agent.rumor_mill),
            "outgoing": len(agent.outgoing_messages),
            "gossip_enabled": agent.gossip_enabled,
            "best_rumor": None if best is None else {
                "artifact_hash": best.get("artifact_hash", ""),
                "priority": round(artifact_priority(best), 3),
                "trust_score": best.get("trust_score", 0.0),
                "source": best.get("source", ""),
            },
        }
