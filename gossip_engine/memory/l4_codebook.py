from __future__ import annotations
import json
import math
import sqlite3
import time
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ..utils.ids import content_hash

EMBEDDING_DIM = 128
NGRAM_MIN = 2
NGRAM_MAX = 4
MINT_THRESHOLD = 0.35
MERGE_COACTIVATION_THRESHOLD = 0.9
SPLIT_PURITY_THRESHOLD = 0.3
RETIRE_AGE_ROUNDS = 100
EVOLVE_INTERVAL = 20


@dataclass
class CodebookEntry:
    index: int
    centroid: list[float]
    label: str = ""
    parent_index: int = -1
    birth_round: int = 0
    usage_count: int = 0
    frozen: bool = False


def _ngram_embed(code: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Character n-gram hash embedding — deterministic, no deps."""
    vec = [0.0] * dim
    cleaned = "".join(c for c in code if c.isprintable())
    for n in range(NGRAM_MIN, NGRAM_MAX + 1):
        for i in range(len(cleaned) - n + 1):
            gram = cleaned[i : i + n]
            h = hash(gram)
            idx = abs(h) % dim
            vec[idx] += 1.0
    mag = math.sqrt(sum(v * v for v in vec))
    if mag > 0:
        vec = [v / mag for v in vec]
    return vec


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(ai * bi for ai, bi in zip(a, b))
    na = math.sqrt(sum(ai * ai for ai in a))
    nb = math.sqrt(sum(bi * bi for bi in b))
    if na * nb == 0:
        return 0.0
    return dot / (na * nb)


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return [0.0] * EMBEDDING_DIM
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]


def _gen_label(code: str, max_words: int = 4) -> str:
    """Extract a short semantic label from source code."""
    import ast
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                parts = node.name.split("_")
                return "_".join(parts[:max_words]) if parts else node.name
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        parts = t.id.split("_")
                        return "_".join(parts[:max_words]) if parts else t.id
    except SyntaxError:
        pass
    # fallback: extract first meaningful word
    for token in code.replace("(", " ").replace(")", " ").replace(":", " ").split():
        if token not in ("def", "return", "import", "pass", "if", "else", "for", "in", ""):
            return token[:20]
    return "auto"


class CodebookStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS codebook (
                idx INTEGER PRIMARY KEY AUTOINCREMENT,
                centroid TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                parent_index INTEGER NOT NULL DEFAULT -1,
                birth_round INTEGER NOT NULL DEFAULT 0,
                usage_count INTEGER NOT NULL DEFAULT 0,
                frozen INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS codebook_activations (
                artifact_hash TEXT NOT NULL,
                code_index INTEGER NOT NULL,
                similarity REAL NOT NULL,
                round INTEGER NOT NULL,
                code_sample TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # Add code_sample column if it doesn't exist (migration)
        try:
            self.conn.execute("ALTER TABLE codebook_activations ADD COLUMN code_sample TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        self.conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_activations_hash_code
            ON codebook_activations(artifact_hash, code_index)
            """
        )
        self.conn.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> CodebookEntry:
        return CodebookEntry(
            index=row["idx"],
            centroid=json.loads(row["centroid"]),
            label=row["label"],
            parent_index=row["parent_index"],
            birth_round=row["birth_round"],
            usage_count=row["usage_count"],
            frozen=bool(row["frozen"]),
        )

    def mint(self, centroid: list[float], label: str = "", parent: int = -1, round: int = 0) -> int:
        cursor = self.conn.execute(
            "INSERT INTO codebook (centroid, label, parent_index, birth_round) VALUES (?, ?, ?, ?)",
            (json.dumps(centroid), label, parent, round),
        )
        self.conn.commit()
        return cursor.lastrowid or 0

    def get(self, index: int) -> CodebookEntry | None:
        row = self.conn.execute("SELECT * FROM codebook WHERE idx = ?", (index,)).fetchone()
        return self._row_to_entry(row) if row else None

    def all_entries(self) -> list[CodebookEntry]:
        rows = self.conn.execute("SELECT * FROM codebook ORDER BY idx").fetchall()
        return [self._row_to_entry(r) for r in rows]

    def entry_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS c FROM codebook").fetchone()
        return int(row["c"]) if row else 0

    def delete(self, index: int) -> None:
        self.conn.execute("DELETE FROM codebook WHERE idx = ?", (index,))
        self.conn.execute("DELETE FROM codebook_activations WHERE code_index = ?", (index,))
        self.conn.commit()

    def increment_usage(self, index: int) -> None:
        self.conn.execute("UPDATE codebook SET usage_count = usage_count + 1 WHERE idx = ?", (index,))
        self.conn.commit()

    def update_centroid(self, index: int, centroid: list[float]) -> None:
        self.conn.execute(
            "UPDATE codebook SET centroid = ? WHERE idx = ?",
            (json.dumps(centroid), index),
        )
        self.conn.commit()

    # ── ENCODE / DECODE ─────────────────────────────────────────

    def encode(self, code: str, round: int = 0) -> tuple[int, float, CodebookEntry | None]:
        """Find nearest codebook entry for a code artifact.

        If distance > MINT_THRESHOLD, triggers MINT automatically.
        Returns: (index, similarity, entry_or_None_if_minted)
        """
        vec = _ngram_embed(code)
        entries = self.all_entries()
        if not entries:
            label = _gen_label(code)
            idx = self.mint(vec, label=label, round=round)
            return idx, 1.0, self.get(idx)

        best = max(entries, key=lambda e: _cosine_sim(vec, e.centroid))
        sim = _cosine_sim(vec, best.centroid)

        if sim < MINT_THRESHOLD:
            label = _gen_label(code)
            idx = self.mint(vec, label=label, parent=best.index, round=round)
            self.increment_usage(idx)
            self._log_activation(idx, code, sim, round)
            return idx, 1.0, self.get(idx)

        self.increment_usage(best.index)
        self._log_activation(best.index, code, sim, round)
        return best.index, sim, best

    def encode_batch(self, artifacts: Sequence[tuple[str, str, int]]) -> list[tuple[str, int, float]]:
        """Encode multiple (artifact_hash, code, round) tuples.

        Returns list of (artifact_hash, code_index, similarity).
        """
        results: list[tuple[str, int, float]] = []
        for hash_, code, round_ in artifacts:
            idx, sim, _ = self.encode(code, round=round_)
            results.append((hash_, idx, sim))
        return results

    def decode(self, index: int) -> list[float]:
        """Return centroid embedding for a codebook index."""
        entry = self.get(index)
        return entry.centroid if entry else [0.0] * EMBEDDING_DIM

    def _log_activation(self, code_index: int, code: str, similarity: float, round: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO codebook_activations (artifact_hash, code_index, similarity, round, code_sample) VALUES (?, ?, ?, ?, ?)",
            (content_hash(code), code_index, similarity, round, code[:200]),
        )
        self.conn.commit()

    # ── CODEBOOK EVOLUTION ───────────────────────────────────────

    def _extract_code_hashes(self, round: int) -> set[int]:
        rows = self.conn.execute(
            "SELECT DISTINCT code_index FROM codebook_activations WHERE round >= ?",
            (round - EVOLVE_INTERVAL,),
        ).fetchall()
        return {int(r["code_index"]) for r in rows}

    def _coactivation_matrix(self, active: set[int]) -> dict[tuple[int, int], float]:
        matrix: dict[tuple[int, int], float] = {}
        activated_together: dict[tuple[int, int], int] = {}
        total_activations: dict[int, int] = {}

        rows = self.conn.execute(
            "SELECT artifact_hash, code_index FROM codebook_activations"
        ).fetchall()
        artifact_codes: dict[str, list[int]] = {}
        for r in rows:
            artifact_codes.setdefault(r["artifact_hash"], []).append(r["code_index"])

        for codes in artifact_codes.values():
            unique = list(set(codes))
            for c in unique:
                total_activations[c] = total_activations.get(c, 0) + 1
            for i in range(len(unique)):
                for j in range(i + 1, len(unique)):
                    a, b = unique[i], unique[j]
                    if a > b:
                        a, b = b, a
                    key = (a, b)
                    activated_together[key] = activated_together.get(key, 0) + 1

        for (a, b), together in activated_together.items():
            denom = max(total_activations.get(a, 0), total_activations.get(b, 0), 1)
            matrix[(a, b)] = together / denom
        return matrix

    def _cluster_embeddings(self, round: int) -> dict[int, list[list[float]]]:
        """Group embeddings of artifacts that activated each code.

        Returns {code_index: [embedding_vec, ...]} for active codes.
        Uses actual code samples stored in activation records.
        """
        clusters: dict[int, list[list[float]]] = {}
        rows = self.conn.execute(
            """
            SELECT code_index, code_sample
            FROM codebook_activations
            WHERE round >= ?
            """,
            (round - EVOLVE_INTERVAL,),
        ).fetchall()

        for r in rows:
            cidx = int(r["code_index"])
            sample = r["code_sample"]
            if not sample:
                continue
            vec = _ngram_embed(sample)
            clusters.setdefault(cidx, []).append(vec)

        # Fill in entries with no activation records using their centroids
        entries = self.all_entries()
        for entry in entries:
            if entry.index not in clusters:
                clusters[entry.index] = [entry.centroid]

        return clusters

    def evolve(self, round: int) -> dict[str, Any]:
        """Run one codebook evolution cycle.

        Returns summary of operations performed.
        """
        if self.entry_count() < 2:
            return {"minted": 0, "merged": 0, "split": 0, "retired": 0}

        ops: dict[str, int] = {"minted": 0, "merged": 0, "split": 0, "retired": 0}
        active = self._extract_code_hashes(round)
        entries = self.all_entries()

        # RETIRE: codes with zero usage for RETIRE_AGE_ROUNDS
        for entry in entries:
            if entry.frozen:
                continue
            if round - entry.birth_round > RETIRE_AGE_ROUNDS and entry.usage_count == 0:
                self.delete(entry.index)
                ops["retired"] += 1

        # MERGE: if two codes are co-activated >90% of the time
        coact = self._coactivation_matrix(active)
        merged: set[int] = set()
        for (a, b), rate in sorted(coact.items(), key=lambda x: -x[1]):
            if a in merged or b in merged:
                continue
            if rate >= MERGE_COACTIVATION_THRESHOLD:
                ea = self.get(a)
                eb = self.get(b)
                if ea and eb and not ea.frozen and not eb.frozen:
                    combined = _centroid([ea.centroid, eb.centroid])
                    label = f"merge({ea.label},{eb.label})"
                    parent = a if ea.birth_round < eb.birth_round else b
                    self.mint(combined, label=label, parent=parent, round=round)
                    self.delete(a)
                    self.delete(b)
                    merged.add(a)
                    merged.add(b)
                    ops["merged"] += 1

        # SPLIT: if a code has low internal purity, split into two
        clusters = self._cluster_embeddings(round)
        for entry in entries:
            if entry.index in merged or entry.frozen:
                continue
            vectors = clusters.get(entry.index, [])
            if len(vectors) < 4:
                continue
            avg_sim = sum(_cosine_sim(v, entry.centroid) for v in vectors) / len(vectors)
            if avg_sim < SPLIT_PURITY_THRESHOLD:
                # Split into two by random partitioning of vectors
                random.shuffle(vectors)
                mid = len(vectors) // 2
                c1 = _centroid(vectors[:mid])
                c2 = _centroid(vectors[mid:])
                self.mint(c1, label=f"split_a({entry.label})", parent=entry.index, round=round)
                self.mint(c2, label=f"split_b({entry.label})", parent=entry.index, round=round)
                self.delete(entry.index)
                ops["split"] += 1

        return ops

    def get_activation_context(self, code: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Return top-K codebook entries for a piece of code (for gossip enrichment)."""
        vec = _ngram_embed(code)
        entries = self.all_entries()
        scored = sorted(
            [(e, _cosine_sim(vec, e.centroid)) for e in entries],
            key=lambda x: -x[1],
        )
        return [
            {"index": e.index, "label": e.label, "similarity": round(s, 3)}
            for e, s in scored[:top_k]
            if s > MINT_THRESHOLD
        ]

    def close(self):
        self.conn.close()
