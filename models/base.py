from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Наивное UTC-время: одинаково хранится в SQLite и PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
