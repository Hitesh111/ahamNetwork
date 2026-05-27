from __future__ import annotations
import math


class Scorer:
    def __init__(self, trust_init: float = 0.5, trust_max: float = 1.0, trust_min: float = 0.0):
        self.trust_init = trust_init
        self.trust_max = trust_max
        self.trust_min = trust_min

    def compute_trust(
        self,
        passed: bool,
        runtime_ms: float,
        novelty_score: float = 0.0,
        trust_decay: float = 0.0,
        quality_score: float = 0.0,
    ) -> float:
        if not passed:
            return max(self.trust_min, self.trust_init * 0.2 - trust_decay)

        base = 0.65 + (0.25 * max(0.0, min(1.0, quality_score)))
        speed_bonus = max(0, 0.1 * (1 - min(runtime_ms, 5000) / 5000))
        novelty_bonus = min(0.2, novelty_score * 0.15)
        result = base + speed_bonus + novelty_bonus - trust_decay
        return min(self.trust_max, max(self.trust_min, result))

    @staticmethod
    def compute_novelty(embedding: list[float], archive_embeddings: list[list[float]]) -> float:
        if not archive_embeddings:
            return 1.0
        min_dist = min(
            math.sqrt(sum((a - b) ** 2 for a, b in zip(embedding, e)))
            for e in archive_embeddings
        )
        return min(1.0, min_dist / 2.0)
