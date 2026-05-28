from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ArchiveEntry:
    artifact_hash: str
    genome: str
    trust_score: float
    novelty_score: float
    agent_id: str
    lineage_hash: str
    age: int
    coords: tuple[int, ...]


class MAPElitesArchive:
    def __init__(self, dimensions: int = 2, resolution: int = 10):
        self.dimensions = dimensions
        self.resolution = resolution
        self._cells: dict[tuple[int, ...], ArchiveEntry] = {}
        self._all_embeddings: list[list[float]] = []
        self._age_counter = 0

    def _discretize(self, behavior: tuple[float, ...]) -> tuple[int, ...]:
        return tuple(
            min(self.resolution - 1, max(0, int(b * self.resolution)))
            for b in behavior
        )

    def insert(self, genome: str, trust_score: float, novelty_score: float,
               agent_id: str, lineage_hash: str,
               behavior: tuple[float, ...],
               artifact_hash: str = "") -> bool:
        self._age_counter += 1
        coords = self._discretize(behavior)
        existing = self._cells.get(coords)
        if existing is None or trust_score > existing.trust_score:
            self._cells[coords] = ArchiveEntry(
                artifact_hash=artifact_hash,
                genome=genome,
                trust_score=trust_score,
                novelty_score=novelty_score,
                agent_id=agent_id,
                lineage_hash=lineage_hash,
                age=self._age_counter,
                coords=coords,
            )
            return True
        return False

    def get_best(self, coords: tuple[int, ...]) -> Optional[ArchiveEntry]:
        key = tuple(coords)
        if key in self._cells:
            return self._cells.get(key)
        return self._cells.get(self._discretize(key))

    def get_random(self) -> Optional[ArchiveEntry]:
        if not self._cells:
            return None
        return random.choice(list(self._cells.values()))

    def get_random_from_random_cell(self) -> Optional[ArchiveEntry]:
        if not self._cells:
            return None
        cell = random.choice(list(self._cells.keys()))
        return self._cells[cell]

    def get_elite(self) -> Optional[ArchiveEntry]:
        if not self._cells:
            return None
        return max(self._cells.values(), key=lambda e: e.trust_score)

    def get_novel(self, n: int = 5) -> list[ArchiveEntry]:
        sorted_entries = sorted(self._cells.values(), key=lambda e: e.novelty_score, reverse=True)
        return sorted_entries[:n]

    def occupancy(self) -> float:
        total_cells = self.resolution ** self.dimensions
        return len(self._cells) / max(1, total_cells)

    def max_trust(self) -> float:
        if not self._cells:
            return 0.0
        return max(e.trust_score for e in self._cells.values())

    def num_cells(self) -> int:
        return len(self._cells)

    def improvement_rate(self, window: int = 10) -> float:
        if self._age_counter < window:
            return 0.0
        recent_count = sum(
            1 for e in self._cells.values()
            if e.age > self._age_counter - window
        )
        return recent_count / max(1, window)

    def select_parent(self, epsilon: float = 0.3) -> Optional[ArchiveEntry]:
        if random.random() < epsilon or not self._cells:
            return self.get_random_from_random_cell()
        entries = list(self._cells.values())
        entries.sort(key=lambda e: e.trust_score, reverse=True)
        return entries[0]

    def reload_from_records(self, records: list[tuple]) -> int:
        """Reload archive from stored (genome, trust, novelty, agent_id, lineage_hash, behavior, artifact_hash) tuples.

        Returns number of cells populated.
        """
        count = 0
        for record in records:
            genome, trust, novelty, agent_id, lineage_hash, behavior, artifact_hash = record[:7]
            inserted = self.insert(
                genome=genome,
                trust_score=trust,
                novelty_score=novelty,
                agent_id=agent_id,
                lineage_hash=lineage_hash,
                behavior=behavior,
                artifact_hash=artifact_hash,
            )
            if inserted:
                count += 1
        return count

    def save_snapshot(self) -> list[dict]:
        """Return serializable snapshot of all archive cells."""
        return [
            {
                "genome": entry.genome,
                "trust_score": entry.trust_score,
                "novelty_score": entry.novelty_score,
                "agent_id": entry.agent_id,
                "lineage_hash": entry.lineage_hash,
                "artifact_hash": entry.artifact_hash,
                "coords": list(entry.coords),
                "age": entry.age,
            }
            for entry in self._cells.values()
        ]
