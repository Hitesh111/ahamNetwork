from __future__ import annotations


def random_genome(prompt: str = "") -> str:
    if prompt:
        return "def solve(x):\n    return x"
    return "def solve(x): return x"
