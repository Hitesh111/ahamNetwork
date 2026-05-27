from __future__ import annotations
import time
from typing import Any, Optional


class AgentLocalMemory:
    def __init__(self, ttl_default: int = 100):
        self._data: dict[str, tuple[Any, float]] = {}
        self.ttl_default = ttl_default

    def read(self, key: str) -> Optional[Any]:
        if key not in self._data:
            return None
        val, expiry = self._data[key]
        if time.time() > expiry:
            del self._data[key]
            return None
        return val

    def write(self, key: str, value: Any, ttl: int | None = None):
        ttl = ttl if ttl is not None else self.ttl_default
        self._data[key] = (value, time.time() + ttl)

    def expire(self, prefix: str = ""):
        if not prefix:
            self._data.clear()
            return
        self._data = {k: v for k, v in self._data.items() if not k.startswith(prefix)}

    def get_active_concepts(self) -> list[str]:
        return [k for k in self._data if time.time() <= self._data[k][1]]

    def expire_stale(self):
        now = time.time()
        self._data = {k: v for k, v in self._data.items() if now <= v[1]}

    def snapshot(self) -> dict[str, tuple[Any, float]]:
        return dict(self._data)

    def restore(self, snapshot: dict[str, tuple[Any, float]]):
        self._data = dict(snapshot)
