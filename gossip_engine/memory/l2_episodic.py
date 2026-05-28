from __future__ import annotations
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence


@dataclass
class ArtifactRecord:
    artifact_hash: str
    content: str
    agent_id: str
    trust_score: float
    validation_results: dict[str, Any] = field(default_factory=dict)
    niche_coords: tuple[int, ...] = field(default_factory=tuple)
    timestamp: float = field(default_factory=time.time)
    parent_hash: str = ""
    lineage_depth: int = 0
    mutation_type: str = "mutate"
    novelty_score: float = 0.0
    behavior: tuple[float, ...] = field(default_factory=tuple)


@dataclass
class RetrievalQuery:
    embedding: Optional[Sequence[float]] = None
    niche_coords: Optional[Sequence[int]] = None
    min_trust: float = 0.0
    limit: int = 10
    prefer_recent: bool = False


class ArtifactStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_hash TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                trust_score REAL NOT NULL,
                validation_results TEXT NOT NULL,
                niche_coords TEXT NOT NULL,
                timestamp REAL NOT NULL,
                parent_hash TEXT NOT NULL,
                lineage_depth INTEGER NOT NULL,
                mutation_type TEXT NOT NULL,
                novelty_score REAL NOT NULL,
                behavior TEXT NOT NULL
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_parent ON artifacts(parent_hash)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_trust ON artifacts(trust_score)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_niche ON artifacts(niche_coords)")
        self.conn.commit()

    @staticmethod
    def _serialize_tuple(values: Sequence[Any]) -> str:
        return json.dumps(list(values))

    @staticmethod
    def _deserialize_tuple(value: str) -> tuple:
        if not value:
            return tuple()
        return tuple(json.loads(value))

    def store(self, artifact: ArtifactRecord) -> str:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO artifacts (
                artifact_hash, content, agent_id, trust_score, validation_results,
                niche_coords, timestamp, parent_hash, lineage_depth, mutation_type,
                novelty_score, behavior
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_hash,
                artifact.content,
                artifact.agent_id,
                artifact.trust_score,
                json.dumps(artifact.validation_results),
                self._serialize_tuple(artifact.niche_coords),
                artifact.timestamp,
                artifact.parent_hash,
                artifact.lineage_depth,
                artifact.mutation_type,
                artifact.novelty_score,
                self._serialize_tuple(artifact.behavior),
            ),
        )
        self.conn.commit()
        return artifact.artifact_hash

    def _row_to_record(self, row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_hash=row["artifact_hash"],
            content=row["content"],
            agent_id=row["agent_id"],
            trust_score=row["trust_score"],
            validation_results=json.loads(row["validation_results"]),
            niche_coords=tuple(json.loads(row["niche_coords"])),
            timestamp=row["timestamp"],
            parent_hash=row["parent_hash"],
            lineage_depth=row["lineage_depth"],
            mutation_type=row["mutation_type"],
            novelty_score=row["novelty_score"],
            behavior=tuple(json.loads(row["behavior"])),
        )

    def retrieve_by_hash(self, artifact_hash: str) -> ArtifactRecord | None:
        row = self.conn.execute(
            "SELECT * FROM artifacts WHERE artifact_hash = ?",
            (artifact_hash,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def retrieve(self, query: RetrievalQuery) -> list[ArtifactRecord]:
        rows = self.conn.execute(
            "SELECT * FROM artifacts WHERE trust_score >= ?",
            (query.min_trust,),
        ).fetchall()
        records = [self._row_to_record(row) for row in rows]

        if query.niche_coords is not None:
            niche = tuple(int(x) for x in query.niche_coords)
            records = [r for r in records if r.niche_coords == niche]

        if query.embedding is not None:
            target = list(query.embedding)

            def dist(record: ArtifactRecord) -> float:
                vec = list(record.behavior) or [0.0] * len(target)
                length = min(len(target), len(vec))
                if length == 0:
                    return float("inf")
                return sum((target[i] - vec[i]) ** 2 for i in range(length)) ** 0.5

            records.sort(key=dist)
        elif query.prefer_recent:
            records.sort(key=lambda r: (r.timestamp, r.trust_score), reverse=True)
        else:
            records.sort(key=lambda r: (r.trust_score, r.timestamp), reverse=True)

        return records[: max(1, query.limit)]

    def retrieve_lineage(self, artifact_hash: str, direction: str = "ANCESTORS", depth: int = 10) -> list[ArtifactRecord]:
        direction = direction.upper()
        if direction == "ANCESTORS":
            sql = """
                WITH RECURSIVE chain(level, artifact_hash) AS (
                    SELECT 0, artifact_hash FROM artifacts WHERE artifact_hash = ?
                    UNION ALL
                    SELECT chain.level + 1, artifacts.parent_hash
                    FROM artifacts
                    JOIN chain ON artifacts.artifact_hash = chain.artifact_hash
                    WHERE chain.level < ? AND artifacts.parent_hash != ''
                )
                SELECT DISTINCT artifacts.*
                FROM artifacts
                JOIN chain ON artifacts.artifact_hash = chain.artifact_hash
                ORDER BY chain.level ASC
            """
            rows = self.conn.execute(sql, (artifact_hash, depth)).fetchall()
            return [self._row_to_record(row) for row in rows]

        sql = """
            WITH RECURSIVE chain(level, artifact_hash) AS (
                SELECT 0, artifact_hash FROM artifacts WHERE artifact_hash = ?
                UNION ALL
                SELECT chain.level + 1, artifacts.artifact_hash
                FROM artifacts
                JOIN chain ON artifacts.parent_hash = chain.artifact_hash
                WHERE chain.level < ?
            )
            SELECT DISTINCT artifacts.*
            FROM artifacts
            JOIN chain ON artifacts.artifact_hash = chain.artifact_hash
            ORDER BY chain.level ASC
        """
        rows = self.conn.execute(sql, (artifact_hash, depth)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_niche_inventory(self, niche_id: Sequence[int]) -> list[ArtifactRecord]:
        niche_json = self._serialize_tuple(tuple(int(x) for x in niche_id))
        rows = self.conn.execute(
            "SELECT * FROM artifacts WHERE niche_coords = ? ORDER BY trust_score DESC, timestamp DESC",
            (niche_json,),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def summarize_niche(self, niche_id: Sequence[int]) -> dict[str, Any]:
        niche_json = self._serialize_tuple(tuple(int(x) for x in niche_id))
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count, AVG(trust_score) AS avg_trust, MAX(trust_score) AS max_trust,
                   MAX(timestamp) AS last_seen
            FROM artifacts
            WHERE niche_coords = ?
            """,
            (niche_json,),
        ).fetchone()
        return {
            "niche_id": tuple(int(x) for x in niche_id),
            "count": int(row["count"] or 0),
            "avg_trust": float(row["avg_trust"] or 0.0),
            "max_trust": float(row["max_trust"] or 0.0),
            "last_seen": float(row["last_seen"] or 0.0),
        }

    def update_trust(self, artifact_hash: str, new_trust: float) -> None:
        self.conn.execute(
            "UPDATE artifacts SET trust_score = ? WHERE artifact_hash = ?",
            (new_trust, artifact_hash),
        )
        self.conn.commit()

    def compact(
        self,
        trust_threshold: float = 0.05,
        age_threshold_seconds: float = 3600.0,
    ) -> int:
        cutoff = time.time() - age_threshold_seconds
        cursor = self.conn.execute(
            "DELETE FROM artifacts WHERE trust_score <= ? AND timestamp <= ?",
            (trust_threshold, cutoff),
        )
        self.conn.commit()
        return cursor.rowcount or 0

    def best_per_niche(self, min_trust: float = 0.0) -> list[tuple]:
        """Return the highest-trust artifact per unique niche bucket.

        Each tuple: (genome, trust_score, novelty_score, agent_id, parent_hash, behavior, artifact_hash).
        """
        rows = self.conn.execute(
            """
            SELECT a.* FROM artifacts a
            INNER JOIN (
                SELECT niche_coords, MAX(trust_score) AS max_trust
                FROM artifacts
                WHERE trust_score >= ?
                GROUP BY niche_coords
            ) b ON a.niche_coords = b.niche_coords AND a.trust_score = b.max_trust
            WHERE a.trust_score >= ?
            ORDER BY a.trust_score DESC
            """,
            (min_trust, min_trust),
        ).fetchall()
        return [
            (
                row["content"],
                row["trust_score"],
                row["novelty_score"],
                row["agent_id"],
                row["parent_hash"],
                tuple(json.loads(row["behavior"])),
                row["artifact_hash"],
            )
            for row in rows
        ]

    def close(self):
        self.conn.close()
