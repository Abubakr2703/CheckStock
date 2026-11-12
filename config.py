from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# По умолчанию проект запускается на SQLite, чтобы его можно было проверить
# одной командой. docker-compose задаёт PostgreSQL через DATABASE_URL.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{(BASE_DIR / 'checkstock.db').as_posix()}",
)

# Демо-данные создаются только в пустой базе. В docker-compose включено.
AUTO_SEED = os.getenv("AUTO_SEED", "true").strip().lower() in {"1", "true", "yes", "on"}

APP_TITLE = "CheckStock"
