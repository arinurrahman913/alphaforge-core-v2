"""
Provider Finnhub — 03_LAYER2_SPECS/02_EVIDENCE.md bagian 1.3-1.5.

Free tier: 60 calls/menit, tanpa kartu kredit. Dipakai untuk:
- institutional-ownership (13F yang sudah dirapikan)
- company-news
- SEC filings umum
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import requests

from .. import config
from ..cache import default_cache
from ..config import DataUnavailableError

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _require_api_key():
    if not config.FINNHUB_API_KEY:
        raise DataUnavailableError(
            "FINNHUB_API_KEY belum diset. Daftar gratis di https://finnhub.io/register "
            "lalu set env var FINNHUB_API_KEY."
        )


def _get(endpoint: str, params: dict) -> dict | list:
    _require_api_key()
    params = {**params, "token": config.FINNHUB_API_KEY}
    last_exc = None
    for attempt in range(config.FINNHUB_MAX_RETRIES):
        try:
            resp = requests.get(
                f"{FINNHUB_BASE_URL}/{endpoint}",
                params=params,
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
            if resp.status_code == 403:
                # 403 di Finnhub berarti endpoint ini butuh paket berbayar --
                # retry tidak akan pernah berhasil, jadi langsung gagal dengan
                # pesan yang jelas (bukan diam-diam retry 3x sia-sia).
                raise DataUnavailableError(
                    f"Endpoint Finnhub '{endpoint}' butuh paket berbayar (403 Forbidden) "
                    "-- tidak tersedia di free tier untuk akun ini. Field terkait akan "
                    "ditandai 'missing', bukan dianggap gagal sementara."
                )
            if resp.status_code == 429:
                # rate limited -> backoff dan retry, bukan gagal permanen
                time.sleep(2.0 * (2 ** attempt))
                continue
            resp.raise_for_status()
            return resp.json()
        except DataUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1.0 * (2 ** attempt))
    raise DataUnavailableError(f"Finnhub '{endpoint}' gagal diambil: {last_exc}")


def get_institutional_ownership(ticker: str, use_cache: bool = True) -> dict:
    """Kepemilikan institusional 13F yang sudah dirapikan (Jalur B di spec Evidence)."""
    cache_key = f"finnhub_inst_own:{ticker}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    data = _get("institutional/ownership", {"symbol": ticker})
    if use_cache and data:
        cache.set(cache_key, data, config.TTL_SECONDS["institutional"])
    return data if isinstance(data, dict) else {"data": data}


def get_company_news(ticker: str, days_back: int = 90, use_cache: bool = True) -> list:
    """Berita perusahaan terbaru. Jendela default 90 hari — lihat catatan
    'Yang Masih Perlu Diputuskan' di 03_LAYER2_SPECS/02_EVIDENCE.md; Speculative
    Module boleh memakai jendela lebih pendek saat memanggil (lihat modules/speculative.py).
    """
    cache_key = f"finnhub_news:{ticker}:{days_back}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    to_date = date.today()
    from_date = to_date - timedelta(days=days_back)
    data = _get("company-news", {
        "symbol": ticker,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
    })
    result = data if isinstance(data, list) else []
    if use_cache:
        cache.set(cache_key, result, config.TTL_SECONDS["news"])
    return result


def get_company_filings(ticker: str, use_cache: bool = True) -> list:
    """SEC filings umum (bukan cuma 13F) — dipakai Risk/Red-Flag Check untuk
    mendeteksi restatement / pergantian auditor dsb."""
    cache_key = f"finnhub_filings:{ticker}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    data = _get("stock/filings", {"symbol": ticker})
    result = data if isinstance(data, list) else []
    if use_cache:
        cache.set(cache_key, result, config.TTL_SECONDS["institutional"])
    return result
