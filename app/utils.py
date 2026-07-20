from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def format_uptime(seconds: int | float | None) -> str:
    try:
        total = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        return "—"
    if total == 0:
        return "—"

    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours:02d}h")
    parts.append(f"{minutes:02d}m")
    return " ".join(parts)


def state_display(status: str | None) -> tuple[str, str]:
    normalized = (status or "").lower()
    if normalized == "running":
        return "running", "Ligado"
    if normalized == "stopped":
        return "stopped", "Desligado"
    return "unknown", "Desconhecido"


def utc_from_epoch(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def pick(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return default
