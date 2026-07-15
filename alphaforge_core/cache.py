"""
Cache lokal berbasis SQLite dengan TTL per key.

Implementasi dari 04_DATA_SOURCES/05_RATE_LIMIT_CACHING_STRATEGY.md poin #2:
"Caching wajib, bukan opsional." Dipakai oleh semua provider supaya screening
market-wide tidak memicu rate-limit dari Yahoo Finance / Finnhub.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from . import config


class TTLCache:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.CACHE_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL,
                stored_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> Any:
        row = self._conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value_json, expires_at = row
        if time.time() > expires_at:
            self.delete(key)
            return None
        return json.loads(value_json)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at, stored_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value), now + ttl_seconds, now),
        )
        self._conn.commit()

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        self._conn.commit()

    def get_or_set(self, key: str, ttl_seconds: int, compute_fn):
        cached = self.get(key)
        if cached is not None:
            return cached, True  # (value, was_cache_hit)
        value = compute_fn()
        self.set(key, value, ttl_seconds)
        return value, False

    def close(self):
        self._conn.close()


_default_cache: Optional[TTLCache] = None


def default_cache() -> TTLCache:
    global _default_cache
    if _default_cache is None:
        _default_cache = TTLCache()
    return _default_cache
