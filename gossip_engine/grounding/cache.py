from __future__ import annotations
from ..utils.ids import content_hash


class ExecutionCache:
    def __init__(self, max_size: int = 10000):
        self._cache: dict[str, tuple] = {}
        self.max_size = max_size

    def get(self, code: str) -> tuple | None:
        h = content_hash(code)
        return self._cache.get(h)

    def put(self, code: str, result: tuple):
        h = content_hash(code)
        if len(self._cache) >= self.max_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[h] = result

    def clear(self):
        self._cache.clear()
