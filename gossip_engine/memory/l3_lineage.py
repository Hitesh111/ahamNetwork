from __future__ import annotations
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence


@dataclass
class DAGNode:
    artifact_hash: str
    parent_hashes: tuple[str, ...] = field(default_factory=tuple)
    agent_id: str = ""
    mutation_type: str = "mutate"
    mutation_params: dict[str, Any] = field(default_factory=dict)
    trust_score: float = 0.0
    lineage_depth: int = 0
    niche_bucket: tuple[int, ...] = field(default_factory=tuple)
    timestamp: float = field(default_factory=time.time)
    frozen: bool = False
    compressed: bool = False
    summary_json: str = ""


class LineageStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                node_id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_hash TEXT UNIQUE NOT NULL,
                parent_hashes TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                mutation_type TEXT NOT NULL,
                mutation_params TEXT NOT NULL,
                trust_score REAL NOT NULL,
                lineage_depth INTEGER NOT NULL,
                niche_bucket TEXT NOT NULL,
                timestamp REAL NOT NULL,
                frozen INTEGER NOT NULL DEFAULT 0,
                compressed INTEGER NOT NULL DEFAULT 0,
                summary_json TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                parent_hash TEXT NOT NULL,
                child_hash TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_parent ON edges(parent_hash)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_child ON edges(child_hash)")
        self.conn.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value)

    def _node_to_dag(self, row: sqlite3.Row) -> DAGNode:
        return DAGNode(
            artifact_hash=row["artifact_hash"],
            parent_hashes=tuple(json.loads(row["parent_hashes"])),
            agent_id=row["agent_id"],
            mutation_type=row["mutation_type"],
            mutation_params=json.loads(row["mutation_params"]),
            trust_score=row["trust_score"],
            lineage_depth=row["lineage_depth"],
            niche_bucket=tuple(json.loads(row["niche_bucket"])),
            timestamp=row["timestamp"],
            frozen=bool(row["frozen"]),
            compressed=bool(row["compressed"]),
            summary_json=row["summary_json"],
        )

    def _depth_for_parent(self, parent_hashes: Sequence[str]) -> int:
        depths = []
        for parent in parent_hashes:
            if not parent:
                continue
            row = self.conn.execute(
                "SELECT lineage_depth FROM nodes WHERE artifact_hash = ?",
                (parent,),
            ).fetchone()
            depths.append(int(row["lineage_depth"]) if row else 0)
        return (max(depths) if depths else -1) + 1

    def record_mutation(
        self,
        parent_hash: str,
        artifact_hash: str,
        agent_id: str,
        mutation_type: str,
        params: dict[str, Any] | None = None,
        trust_score: float = 0.0,
        niche_bucket: Sequence[int] = (),
    ) -> int:
        params = params or {}
        depth = self._depth_for_parent([parent_hash])
        self.conn.execute(
            """
            INSERT OR REPLACE INTO nodes (
                artifact_hash, parent_hashes, agent_id, mutation_type, mutation_params,
                trust_score, lineage_depth, niche_bucket, timestamp, frozen, compressed, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, '')
            """,
            (
                artifact_hash,
                self._json([parent_hash] if parent_hash else []),
                agent_id,
                mutation_type,
                self._json(params),
                trust_score,
                depth,
                self._json(list(niche_bucket)),
                time.time(),
            ),
        )
        if parent_hash:
            self.conn.execute(
                """
                INSERT INTO edges (parent_hash, child_hash, edge_type, weight)
                VALUES (?, ?, ?, ?)
                """,
                (parent_hash, artifact_hash, "parent_of", max(0.01, trust_score or 1.0)),
            )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT node_id FROM nodes WHERE artifact_hash = ?",
            (artifact_hash,),
        ).fetchone()
        return int(row["node_id"])

    def record_recombination(
        self,
        parent_hash_a: str,
        parent_hash_b: str,
        artifact_hash: str,
        agent_id: str,
        params: dict[str, Any] | None = None,
        trust_score: float = 0.0,
        niche_bucket: Sequence[int] = (),
    ) -> int:
        params = params or {}
        depth = self._depth_for_parent([parent_hash_a, parent_hash_b])
        self.conn.execute(
            """
            INSERT OR REPLACE INTO nodes (
                artifact_hash, parent_hashes, agent_id, mutation_type, mutation_params,
                trust_score, lineage_depth, niche_bucket, timestamp, frozen, compressed, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, '')
            """,
            (
                artifact_hash,
                self._json([parent_hash_a, parent_hash_b]),
                agent_id,
                "recombine",
                self._json(params),
                trust_score,
                depth,
                self._json(list(niche_bucket)),
                time.time(),
            ),
        )
        for parent in (parent_hash_a, parent_hash_b):
            if parent:
                self.conn.execute(
                    """
                    INSERT INTO edges (parent_hash, child_hash, edge_type, weight)
                    VALUES (?, ?, ?, ?)
                    """,
                    (parent, artifact_hash, "recombined_from", max(0.01, trust_score or 1.0)),
                )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT node_id FROM nodes WHERE artifact_hash = ?",
            (artifact_hash,),
        ).fetchone()
        return int(row["node_id"])

    def get_node(self, artifact_hash: str) -> DAGNode | None:
        row = self.conn.execute(
            "SELECT * FROM nodes WHERE artifact_hash = ?",
            (artifact_hash,),
        ).fetchone()
        return self._node_to_dag(row) if row else None

    def get_ancestors(self, artifact_hash: str, depth: int = 10) -> list[DAGNode]:
        rows = self.conn.execute(
            """
            WITH RECURSIVE chain(level, artifact_hash) AS (
                SELECT 0, ?
                UNION ALL
                SELECT chain.level + 1, edges.parent_hash
                FROM edges
                JOIN chain ON edges.child_hash = chain.artifact_hash
                WHERE chain.level < ?
            )
            SELECT DISTINCT nodes.*
            FROM nodes
            JOIN chain ON nodes.artifact_hash = chain.artifact_hash
            ORDER BY chain.level ASC
            """,
            (artifact_hash, depth),
        ).fetchall()
        return [self._node_to_dag(row) for row in rows]

    def get_descendants(self, artifact_hash: str, depth: int = 10) -> list[DAGNode]:
        rows = self.conn.execute(
            """
            WITH RECURSIVE chain(level, artifact_hash) AS (
                SELECT 0, ?
                UNION ALL
                SELECT chain.level + 1, edges.child_hash
                FROM edges
                JOIN chain ON edges.parent_hash = chain.artifact_hash
                WHERE chain.level < ?
            )
            SELECT DISTINCT nodes.*
            FROM nodes
            JOIN chain ON nodes.artifact_hash = chain.artifact_hash
            ORDER BY chain.level ASC
            """,
            (artifact_hash, depth),
        ).fetchall()
        return [self._node_to_dag(row) for row in rows]

    def find_common_ancestor(self, hash_a: str, hash_b: str) -> DAGNode | None:
        ancestors_a = {node.artifact_hash: node.lineage_depth for node in self.get_ancestors(hash_a, depth=50)}
        ancestors_b = {node.artifact_hash: node.lineage_depth for node in self.get_ancestors(hash_b, depth=50)}
        common = set(ancestors_a).intersection(ancestors_b)
        if not common:
            return None
        best = min(common, key=lambda h: (ancestors_a[h] + ancestors_b[h], -ancestors_a[h]))
        return self.get_node(best)

    def get_lineage_stats(self, artifact_hash: str) -> dict[str, Any]:
        node = self.get_node(artifact_hash)
        if not node:
            return {
                "artifact_hash": artifact_hash,
                "depth": 0,
                "nodes": 0,
                "branches": 0,
                "avg_trust": 0.0,
                "max_trust": 0.0,
            }
        descendants = self.get_descendants(artifact_hash, depth=50)
        branch_count = self.conn.execute(
            "SELECT COUNT(*) AS count FROM edges WHERE parent_hash = ?",
            (artifact_hash,),
        ).fetchone()["count"]
        trust_values = [n.trust_score for n in descendants]
        return {
            "artifact_hash": artifact_hash,
            "depth": node.lineage_depth,
            "nodes": len(descendants),
            "branches": int(branch_count),
            "avg_trust": sum(trust_values) / max(1, len(trust_values)),
            "max_trust": max(trust_values) if trust_values else 0.0,
        }

    def get_surviving_lineages(self, min_depth: int = 0, min_trust: float = 0.0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM nodes
            WHERE lineage_depth >= ? AND trust_score >= ? AND frozen = 0
            ORDER BY trust_score DESC, lineage_depth DESC
            """,
            (min_depth, min_trust),
        ).fetchall()
        return [
            {
                "artifact_hash": row["artifact_hash"],
                "depth": row["lineage_depth"],
                "trust_score": row["trust_score"],
                "agent_id": row["agent_id"],
                "mutation_type": row["mutation_type"],
            }
            for row in rows
        ]

    def freeze_branch(self, artifact_hash: str) -> None:
        for node in self.get_descendants(artifact_hash, depth=1000):
            self.conn.execute(
                "UPDATE nodes SET frozen = 1 WHERE artifact_hash = ?",
                (node.artifact_hash,),
            )
        self.conn.commit()

    def compress_branch(self, artifact_hash: str) -> dict[str, Any]:
        nodes = self.get_descendants(artifact_hash, depth=1000)
        if not nodes:
            return {"artifact_hash": artifact_hash, "compressed": False, "nodes": 0}
        summary = {
            "artifact_hash": artifact_hash,
            "compressed": True,
            "nodes": len(nodes),
            "max_depth": max(node.lineage_depth for node in nodes),
            "max_trust": max(node.trust_score for node in nodes),
            "avg_trust": sum(node.trust_score for node in nodes) / len(nodes),
        }
        self.conn.execute(
            "UPDATE nodes SET compressed = 1, summary_json = ? WHERE artifact_hash = ?",
            (json.dumps(summary), artifact_hash),
        )
        self.conn.commit()
        return summary

    def update_trust(self, artifact_hash: str, new_trust: float) -> None:
        self.conn.execute(
            "UPDATE nodes SET trust_score = ? WHERE artifact_hash = ?",
            (new_trust, artifact_hash),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
