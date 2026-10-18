from __future__ import annotations

from ..config import Settings
from .repository import Repository


def create_repository(settings: Settings) -> Repository:
    if settings.storage == "postgres":
        from .postgres import PostgresRepository
        if not settings.database_url:
            raise RuntimeError("STORAGE=postgres needs DATABASE_URL (set it in backend/.env)")
        return PostgresRepository(settings.database_url)
    from .memory import InMemoryRepository
    return InMemoryRepository()
