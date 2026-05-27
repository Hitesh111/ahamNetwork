from __future__ import annotations
from typing import Any

GRADIENT = " .:-=+*#%@"


def format_kv(items: dict[str, object]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in items.items())


def shorten(value: str, width: int = 8) -> str:
    value = value or ""
    if len(value) <= width:
        return value
    return value[:width]


def bar(value: float, width: int = 20, fill: str = "#", empty: str = ".") -> str:
    clamped = max(0.0, min(1.0, float(value)))
    filled = int(round(clamped * width))
    return fill * filled + empty * max(0, width - filled)


def trust_char(score: float) -> str:
    idx = int(max(0.0, min(1.0, score)) * (len(GRADIENT) - 1))
    return GRADIENT[idx]


def format_population_states(states: dict[str, int]) -> str:
    if not states:
        return "(no agents)"
    total = sum(states.values()) or 1
    lines = []
    for state, count in sorted(states.items()):
        share = count / total
        lines.append(f"{state:>8}  {count:>3}  {bar(share, width=12)}")
    return "\n".join(lines)


def format_archive_heatmap(archive) -> str:
    if not getattr(archive, "_cells", None):
        return "(archive empty)"
    dims = getattr(archive, "dimensions", 0)
    resolution = getattr(archive, "resolution", 0)
    if dims != 2 or resolution <= 0:
        cells = sorted(getattr(archive, "_cells", {}).values(), key=lambda entry: entry.trust_score, reverse=True)
        lines = [f"{shorten(entry.artifact_hash)} {trust_char(entry.trust_score)} {entry.trust_score:.3f}" for entry in cells[: min(10, len(cells))]]
        return "\n".join(lines)

    rows = []
    for y in reversed(range(resolution)):
        row = []
        for x in range(resolution):
            entry = archive._cells.get((x, y))
            row.append(trust_char(entry.trust_score) if entry else ".")
        rows.append("".join(row))
    return "\n".join(rows)


def format_top_archive_entries(archive, limit: int = 5) -> str:
    cells = sorted(getattr(archive, "_cells", {}).values(), key=lambda entry: (entry.trust_score, entry.novelty_score), reverse=True)
    if not cells:
        return "(archive empty)"
    lines = []
    for entry in cells[:limit]:
        lines.append(
            f"{shorten(entry.artifact_hash)}  trust={entry.trust_score:.3f}  novelty={entry.novelty_score:.3f}  "
            f"cell={entry.coords}  age={entry.age}"
        )
    return "\n".join(lines)


def format_agent_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(no agents)"
    lines = []
    for row in rows:
        best = row.get("best_rumor") or {}
        best_hash = shorten(str(best.get("artifact_hash", "")))
        lines.append(
            f"{shorten(str(row.get('agent_id', ''))):>8}  {row.get('state', ''):<7}  "
            f"trust={float(row.get('trust_score', 0.0)):.3f}  "
            f"neighbors={row.get('neighbors', 0):>2}  rumors={row.get('rumors', 0):>2}  "
            f"out={row.get('outgoing', 0):>2}  best={best_hash or '-'}"
        )
    return "\n".join(lines)
