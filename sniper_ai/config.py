from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    admin_ids: frozenset[int]
    database_path: Path
    min_score: int = 70

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("SNIPER_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("SNIPER_BOT_TOKEN is not set")
        raw_ids = os.getenv("SNIPER_ADMIN_IDS", "").strip()
        try:
            admin_ids = frozenset(int(value.strip()) for value in raw_ids.split(",") if value.strip())
        except ValueError as exc:
            raise RuntimeError("SNIPER_ADMIN_IDS must be comma-separated Telegram numeric IDs") from exc
        db_path = Path(os.getenv("SNIPER_DATABASE_PATH", "data/sniper.sqlite3"))
        try:
            min_score = int(os.getenv("SNIPER_MIN_SCORE", "70"))
        except ValueError as exc:
            raise RuntimeError("SNIPER_MIN_SCORE must be an integer") from exc
        if not 0 <= min_score <= 100:
            raise RuntimeError("SNIPER_MIN_SCORE must be between 0 and 100")
        return cls(token, admin_ids, db_path, min_score)
