from __future__ import annotations

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'Вся Россия',
    max_price INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_searches_owner ON searches(owner_id, enabled);
CREATE TABLE IF NOT EXISTS user_settings (
    owner_id INTEGER PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    min_score INTEGER NOT NULL DEFAULT 70 CHECK(min_score BETWEEN 0 AND 100),
    categories_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    search_id INTEGER REFERENCES searches(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    price INTEGER,
    market_price INTEGER,
    condition_note TEXT,
    risk_note TEXT,
    score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
    source TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_listings_score ON listings(score DESC, first_seen_at DESC);
CREATE TABLE IF NOT EXISTS notification_log (
    listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(listing_id, telegram_id)
);
"""

class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def register_user(self, telegram_id: int, username: str | None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO users(telegram_id, username) VALUES(?, ?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username",
                (telegram_id, username),
            )

    def add_search(self, owner_id: int, query: str, region: str, max_price: int | None) -> int:
        with self.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO searches(owner_id, query, region, max_price) VALUES(?,?,?,?)",
                (owner_id, query, region, max_price),
            )
            return int(cur.lastrowid)

    def list_searches(self, owner_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(conn.execute(
                "SELECT id, query, region, max_price, enabled FROM searches "
                "WHERE owner_id=? ORDER BY id DESC", (owner_id,)
            ))

    def get_search(self, owner_id: int, search_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, query, region, max_price, enabled FROM searches WHERE owner_id=? AND id=?",
                (owner_id, search_id),
            ).fetchone()

    def set_search_enabled(self, owner_id: int, search_id: int, enabled: bool) -> bool:
        with self.transaction() as conn:
            cur = conn.execute(
                "UPDATE searches SET enabled=? WHERE owner_id=? AND id=?",
                (int(enabled), owner_id, search_id),
            )
            return cur.rowcount > 0

    def delete_search(self, owner_id: int, search_id: int) -> bool:
        with self.transaction() as conn:
            cur = conn.execute("DELETE FROM searches WHERE owner_id=? AND id=?", (owner_id, search_id))
            return cur.rowcount > 0

    def set_searches_enabled(self, owner_id: int, enabled: bool) -> int:
        with self.transaction() as conn:
            cur = conn.execute("UPDATE searches SET enabled=? WHERE owner_id=?", (int(enabled), owner_id))
            return cur.rowcount

    def get_settings(self, owner_id: int) -> dict:
        import json
        with self.connect() as conn:
            row = conn.execute(
                "SELECT min_score, categories_json FROM user_settings WHERE owner_id=?",
                (owner_id,),
            ).fetchone()
        if not row:
            return {"min_score": 70, "categories": ["Телефоны", "Компьютеры", "Электроника"]}
        try:
            categories = json.loads(row["categories_json"])
        except (TypeError, ValueError):
            categories = []
        return {"min_score": int(row["min_score"]), "categories": categories}

    def set_settings(self, owner_id: int, *, min_score: int, categories: list[str]) -> None:
        import json
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO user_settings(owner_id, min_score, categories_json) VALUES(?,?,?) "
                "ON CONFLICT(owner_id) DO UPDATE SET min_score=excluded.min_score, categories_json=excluded.categories_json",
                (owner_id, min_score, json.dumps(categories, ensure_ascii=False)),
            )

    def stats(self, owner_id: int) -> tuple[int, int]:
        with self.connect() as conn:
            searches = conn.execute("SELECT COUNT(*) FROM searches WHERE owner_id=? AND enabled=1", (owner_id,)).fetchone()[0]
            alerts = conn.execute("SELECT COUNT(*) FROM notification_log WHERE telegram_id=?", (owner_id,)).fetchone()[0]
            return int(searches), int(alerts)
