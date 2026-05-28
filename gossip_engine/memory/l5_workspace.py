from __future__ import annotations
import json
import logging
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("gossip_engine")

WORKSPACE_SIZE = 7
ATTENTION_DECAY = 0.95


@dataclass
class WorkspaceSlot:
    index: int
    genome: str
    trust: float
    novelty: float
    attention: float
    promoted_round: int
    last_active_round: int
    diversity_bonus: float = 0.0
    source_agent_id: str = ""
    artifact_hash: str = ""


class GlobalWorkspace:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._candidates: list[dict[str, Any]] = []

    def _init_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                genome TEXT NOT NULL,
                trust REAL NOT NULL DEFAULT 0.0,
                novelty REAL NOT NULL DEFAULT 0.0,
                attention REAL NOT NULL DEFAULT 0.0,
                promoted_round INTEGER NOT NULL DEFAULT 0,
                last_active_round INTEGER NOT NULL DEFAULT 0,
                diversity_bonus REAL NOT NULL DEFAULT 0.0,
                source_agent_id TEXT NOT NULL DEFAULT '',
                artifact_hash TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_history (
                round INTEGER NOT NULL,
                artifact_hash TEXT NOT NULL,
                genome_preview TEXT NOT NULL,
                trust REAL NOT NULL,
                attention REAL NOT NULL
            )
            """
        )
        self.conn.commit()

    def _row_to_slot(self, row: sqlite3.Row) -> WorkspaceSlot:
        return WorkspaceSlot(
            index=row["idx"],
            genome=row["genome"],
            trust=row["trust"],
            novelty=row["novelty"],
            attention=row["attention"],
            promoted_round=row["promoted_round"],
            last_active_round=row["last_active_round"],
            diversity_bonus=row["diversity_bonus"],
            source_agent_id=row["source_agent_id"],
            artifact_hash=row["artifact_hash"],
        )

    _EMBEDDING_CACHE: dict[str, list[float]] = {}

    def _workspace_embed(self, code: str) -> list[float]:
        cached = self._EMBEDDING_CACHE.get(code)
        if cached is not None:
            return cached
        vec = [0.0] * 64
        cleaned = "".join(c for c in code if c.isprintable())
        for n in (2, 3):
            for i in range(len(cleaned) - n + 1):
                h = hash(cleaned[i:i+n])
                vec[abs(h) % 64] += 1.0
        mag = math.sqrt(sum(v*v for v in vec))
        if mag > 0:
            vec = [v / mag for v in vec]
        self._EMBEDDING_CACHE[code] = vec
        return vec

    def _code_sim(self, a: str, b: str) -> float:
        va = self._workspace_embed(a)
        vb = self._workspace_embed(b)
        dot = sum(ai*bi for ai, bi in zip(va, vb))
        return dot

    def contents(self) -> list[WorkspaceSlot]:
        rows = self.conn.execute("SELECT * FROM workspace ORDER BY attention DESC").fetchall()
        return [self._row_to_slot(r) for r in rows]

    def size(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM workspace").fetchone()
        return int(row["c"]) if row else 0

    def push_candidate(self, agent_id: str, genome: str, trust: float, novelty: float, artifact_hash: str, round: int) -> None:
        self._candidates.append({
            "agent_id": agent_id,
            "genome": genome,
            "trust": trust,
            "novelty": novelty,
            "artifact_hash": artifact_hash,
            "round": round,
        })

    def promote(self, round: int) -> list[dict[str, Any]]:
        if not self._candidates:
            return []
        current = self.contents()
        current_genomes = [c.genome for c in current]
        scored: list[dict[str, Any]] = []
        for c in self._candidates:
            max_sim = max((self._code_sim(c["genome"], g) for g in current_genomes), default=0.0)
            diversity_bonus = 1.0 - max_sim
            attention = c["trust"] * (c["novelty"] + 0.1) * (0.5 + 0.5 * diversity_bonus)
            scored.append({**c, "attention": attention, "diversity_bonus": diversity_bonus})
        scored.sort(key=lambda x: -x["attention"])
        self._candidates.clear()
        promoted: list[dict[str, Any]] = []
        n_promote = max(1, WORKSPACE_SIZE // 2)
        for s in scored[:n_promote]:
            existing = [x for x in current if x.artifact_hash == s["artifact_hash"]]
            if existing:
                self._touch(existing[0].index, round)
                continue
            if self.size() >= WORKSPACE_SIZE:
                self._evict_lowest()
            cursor = self.conn.execute(
                """
                INSERT INTO workspace (genome, trust, novelty, attention, promoted_round, last_active_round, diversity_bonus, source_agent_id, artifact_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (s["genome"], s["trust"], s["novelty"], s["attention"], round, round, s["diversity_bonus"], s["agent_id"], s["artifact_hash"]),
            )
            self.conn.execute(
                "INSERT INTO workspace_history (round, artifact_hash, genome_preview, trust, attention) VALUES (?, ?, ?, ?, ?)",
                (round, s["artifact_hash"], s["genome"][:60], s["trust"], s["attention"]),
            )
            promoted.append(s)
            current = self.contents()
        self.conn.commit()
        return promoted

    def _touch(self, index: int, round: int) -> None:
        self.conn.execute("UPDATE workspace SET last_active_round = ? WHERE idx = ?", (round, index))
        self.conn.commit()

    def _evict_lowest(self) -> None:
        self.conn.execute(
            "DELETE FROM workspace WHERE idx = (SELECT idx FROM workspace ORDER BY attention ASC LIMIT 1)"
        )
        self.conn.commit()

    def broadcast(self, promoted: list[dict[str, Any]]) -> list[str]:
        return [p["genome"] for p in promoted]

    def apply_attention_decay(self, round: int) -> None:
        self.conn.execute(
            "UPDATE workspace SET attention = attention * ? WHERE last_active_round < ?",
            (ATTENTION_DECAY, round),
        )
        self.conn.commit()

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM workspace_history ORDER BY round DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
