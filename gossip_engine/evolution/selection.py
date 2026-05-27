from __future__ import annotations
import random


def select_parent(archive, epsilon: float = 0.3):
    return archive.select_parent(epsilon=epsilon)


def tournament_select(entries, k: int = 3):
    if not entries:
        return None
    sample = random.sample(entries, min(k, len(entries)))
    return max(sample, key=lambda entry: entry.trust_score)
