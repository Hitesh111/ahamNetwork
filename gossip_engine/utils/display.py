from __future__ import annotations


def format_kv(items: dict[str, object]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in items.items())
