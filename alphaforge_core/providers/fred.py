"""
Provider FRED (Federal Reserve Economic Data) — 04_DATA_SOURCES/04_MACRO_DATA_SOURCES.md

Butuh FRED_API_KEY (gratis, daftar di https://fred.stlouisfed.org/docs/api/api_key.html).
Kalau key tidak ada, fungsi di sini melempar DataUnavailableError secara eksplisit —
tidak pernah diam-diam mengembalikan angka dummy.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from .. import config
from ..cache import default_cache
from ..config import DataUnavailableError

FRED_BASE_URL = "https://api.stlouisfed.org/fred"


def _require_api_key():
    if not config.FRED_API_KEY:
        raise DataUnavailableError(
            "FRED_API_KEY belum diset. Daftar gratis di "
            "https://fred.stlouisfed.org/docs/api/api_key.html lalu set env var FRED_API_KEY."
        )


def get_series(series_id: str, limit: int = 60, use_cache: bool = True) -> list[dict]:
    """Ambil observasi terbaru untuk satu FRED series id.
    Return list of {"date": "YYYY-MM-DD", "value": float|None}, terurut terbaru dulu.
    """
    _require_api_key()
    cache_key = f"fred_series:{series_id}:{limit}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    params = {
        "series_id": series_id,
        "api_key": config.FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(
                f"{FRED_BASE_URL}/series/observations",
                params=params,
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            payload = resp.json()
            observations = payload.get("observations", [])
            result = []
            for obs in observations:
                val = obs.get("value")
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    val = None
                result.append({"date": obs.get("date"), "value": val})
            if use_cache:
                cache.set(cache_key, result, config.TTL_SECONDS["macro_series"])
            return result
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1.5 * (2 ** attempt))
    raise DataUnavailableError(f"FRED series '{series_id}' gagal diambil: {last_exc}")


def get_release_calendar(limit: int = 20) -> list[dict]:
    """Jadwal rilis data ekonomi resmi — dipakai Macro Economic Calendar.
    Lihat 02_LAYER1_SPECS/09_MACRO_CALENDAR.md (hindari scraping ala Investing.com).
    """
    _require_api_key()
    params = {
        "api_key": config.FRED_API_KEY,
        "file_type": "json",
        "include_release_dates_with_no_data": "true",
        "limit": limit,
        "sort_order": "asc",
    }
    try:
        resp = requests.get(
            f"{FRED_BASE_URL}/releases/dates",
            params=params,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("release_dates", [])
    except Exception as exc:  # noqa: BLE001
        raise DataUnavailableError(f"FRED release calendar gagal diambil: {exc}")
