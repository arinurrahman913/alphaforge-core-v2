"""
Sumber daftar ticker NASDAQ + NYSE — 04_DATA_SOURCES/03_MARKET_LISTING_SOURCES.md

Yahoo Finance tidak punya endpoint "semua ticker", jadi kita pakai NASDAQ Trader
listing files publik. Hasilnya di-cache lama (TTL mingguan) karena daftar ticker
tidak berubah drastis harian.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd
import requests

from .. import config
from ..cache import default_cache
from ..config import DataUnavailableError


@dataclass(frozen=True)
class ListedSecurity:
    symbol: str
    name: str
    exchange: str          # 'Q' Nasdaq, 'N' NYSE, dst (dari otherlisted.txt), atau market-tier dari nasdaqlisted.txt
    is_test_issue: bool
    is_etf: bool
    security_type: str     # 'common_stock', 'etf', 'warrant', 'unit', 'preferred', 'unknown', dst.


def _classify_security_type(name: str, is_etf_flag: bool, symbol: str) -> str:
    """Klasifikasi kasar tipe instrumen dari nama & suffix simbol, dipakai untuk
    Hard Exclude 'bukan saham biasa' di Screening (03_LAYER2_SPECS/01_SCREENING.md)."""
    name_lower = (name or "").lower()
    if is_etf_flag:
        return "etf"
    if "warrant" in name_lower or symbol.endswith("W") and "." in symbol:
        return "warrant"
    if "right" in name_lower or symbol.endswith(("R", ".R")):
        return "right"
    if "unit" in name_lower and ("acquisition" in name_lower or "spac" in name_lower):
        return "spac_unit"
    if "preferred" in name_lower or " pfd" in name_lower:
        return "preferred"
    return "common_stock"


def _parse_nasdaqlisted(text: str) -> list[ListedSecurity]:
    df = pd.read_csv(io.StringIO(text), sep="|")
    df = df[~df["Symbol"].isna()]
    df = df[df["Symbol"] != "File Creation Time"]  # baris footer khas file ini
    out = []
    for _, row in df.iterrows():
        is_etf = str(row.get("ETF", "N")).strip().upper() == "Y"
        is_test = str(row.get("Test Issue", "N")).strip().upper() == "Y"
        symbol = str(row["Symbol"]).strip()
        name = str(row.get("Security Name", "")).strip()
        out.append(ListedSecurity(
            symbol=symbol,
            name=name,
            exchange="NASDAQ",
            is_test_issue=is_test,
            is_etf=is_etf,
            security_type=_classify_security_type(name, is_etf, symbol),
        ))
    return out


def _parse_otherlisted(text: str) -> list[ListedSecurity]:
    df = pd.read_csv(io.StringIO(text), sep="|")
    df = df[~df["ACT Symbol"].isna()]
    df = df[df["ACT Symbol"] != "File Creation Time"]
    exch_map = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca", "Z": "BATS", "V": "IEX"}
    out = []
    for _, row in df.iterrows():
        is_etf = str(row.get("ETF", "N")).strip().upper() == "Y"
        is_test = str(row.get("Test Issue", "N")).strip().upper() == "Y"
        symbol = str(row["ACT Symbol"]).strip()
        name = str(row.get("Security Name", "")).strip()
        exch_code = str(row.get("Exchange", "")).strip()
        out.append(ListedSecurity(
            symbol=symbol,
            name=name,
            exchange=exch_map.get(exch_code, exch_code or "OTHER"),
            is_test_issue=is_test,
            is_etf=is_etf,
            security_type=_classify_security_type(name, is_etf, symbol),
        ))
    return out


def get_universe(use_cache: bool = True, nyse_only_relevant: bool = True) -> list[ListedSecurity]:
    """Gabungan universe NASDAQ + NYSE (lewat otherlisted.txt), sesuai spec.

    nyse_only_relevant=True membuang baris exchange lain yang ikut nebeng di
    otherlisted.txt (mis. BATS/IEX) supaya scope tetap 'NASDAQ + NYSE' sesuai Charter.
    """
    cache = default_cache()
    cache_key = "market_universe:nasdaq+nyse"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return [ListedSecurity(**row) for row in cached]

    try:
        r1 = requests.get(config.NASDAQ_LISTED_URL, timeout=config.REQUEST_TIMEOUT_SECONDS)
        r1.raise_for_status()
        r2 = requests.get(config.OTHER_LISTED_URL, timeout=config.REQUEST_TIMEOUT_SECONDS)
        r2.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise DataUnavailableError(f"Gagal mengunduh listing file NASDAQ Trader: {exc}")

    nasdaq_list = _parse_nasdaqlisted(r1.text)
    other_list = _parse_otherlisted(r2.text)
    if nyse_only_relevant:
        other_list = [s for s in other_list if s.exchange in ("NYSE", "NYSE American", "NYSE Arca")]

    universe = nasdaq_list + other_list
    if use_cache:
        cache.set(
            cache_key,
            [s.__dict__ for s in universe],
            config.TTL_SECONDS["ticker_listing"],
        )
    return universe
