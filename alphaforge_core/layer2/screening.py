"""
Screening — 03_LAYER2_SPECS/01_SCREENING.md

Implements Hard Exclude / Soft Flag persis sesuai tabel ambang di spec.
Dirancang supaya bisa dipanggil per-ticker (mode analisa 1 saham) maupun
market-wide (mode full screening, lebih mahal -- lihat `screen_universe`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional

from .. import config
from ..config import DataUnavailableError
from ..providers import market_listings, yahoo_finance as yf_provider


@dataclass
class ScreeningResult:
    ticker: str
    passed: bool
    hard_exclude_reasons: list[str] = field(default_factory=list)
    soft_flags: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _avg_dollar_volume_20d(hist) -> Optional[float]:
    if hist is None or hist.empty or len(hist) < 20:
        return None
    recent = hist.iloc[-20:]
    dollar_vol = (recent["Close"] * recent["Volume"]).mean()
    return float(dollar_vol)


def screen_ticker(ticker: str, security_type: str = "common_stock",
                   is_test_issue: bool = False, is_adr: bool = False) -> ScreeningResult:
    """Terapkan Hard Exclude & Soft Flag untuk satu ticker.

    `security_type` / `is_test_issue` idealnya datang dari
    providers.market_listings (murah, tanpa panggilan live) sesuai spec poin
    "Cara Kerja — Sumber Data per Tahap Filter" #1.
    """
    t = config.SCREENING
    hard_reasons: list[str] = []
    soft_flags: list[str] = []
    metrics: dict = {}

    # --- Hard exclude #1: tipe instrumen & test issue (tanpa panggilan API) ---
    if is_test_issue:
        hard_reasons.append("test_issue")
    if security_type != "common_stock":
        hard_reasons.append(f"not_common_stock:{security_type}")

    if hard_reasons:
        # Tidak perlu tarik data live sama sekali kalau sudah gagal di sini (hemat rate-limit).
        return ScreeningResult(ticker, passed=False, hard_exclude_reasons=hard_reasons)

    # --- Data harga & fundamental (idealnya dari cache, lihat provider) ---
    try:
        hist = yf_provider.get_price_history(ticker, period="2y")
        fast_info = yf_provider.get_fast_info(ticker)
    except DataUnavailableError as exc:
        hard_reasons.append(f"data_unavailable:{exc}")
        return ScreeningResult(ticker, passed=False, hard_exclude_reasons=hard_reasons)

    price_history_days = 0 if hist is None else len(hist)
    metrics["price_history_days"] = price_history_days
    if price_history_days < t.hard_min_price_history_days:
        hard_reasons.append(f"insufficient_price_history:{price_history_days}d")

    last_price = float(hist["Close"].iloc[-1]) if price_history_days else None
    metrics["last_price"] = last_price
    if last_price is not None and last_price < t.hard_min_price_usd:
        hard_reasons.append(f"price_below_min:{last_price}")

    market_cap = fast_info.get("market_cap") or fast_info.get("marketCap")
    metrics["market_cap"] = market_cap
    if market_cap is not None and market_cap < t.hard_min_market_cap_usd:
        hard_reasons.append(f"market_cap_below_min:{market_cap}")

    avg_dollar_vol = _avg_dollar_volume_20d(hist) if price_history_days else None
    metrics["avg_dollar_volume_20d"] = avg_dollar_vol
    if avg_dollar_vol is not None and avg_dollar_vol < t.hard_min_avg_dollar_volume_20d_usd:
        hard_reasons.append(f"avg_dollar_volume_below_min:{avg_dollar_vol:.0f}")

    # NOTE: pengecekan "laporan keuangan kuartalan 2 kuartal terakhir" butuh
    # data fundamental (Evidence-level) -- diverifikasi ulang saat Evidence
    # ditarik penuh; di sini kita hanya skip kalau fast_info sama sekali kosong
    # (indikasi data tidak tersedia untuk ticker ini).
    if not fast_info:
        hard_reasons.append("no_fundamental_data_available")

    if hard_reasons:
        return ScreeningResult(ticker, passed=False, hard_exclude_reasons=hard_reasons, metrics=metrics)

    # --- Soft flags (tidak menggugurkan) ---
    if market_cap is not None:
        if t.hard_min_market_cap_usd <= market_cap < t.soft_micro_cap_max_usd:
            soft_flags.append("micro_cap")
        elif t.soft_micro_cap_max_usd <= market_cap < t.soft_small_cap_max_usd:
            soft_flags.append("small_cap")

    if price_history_days < t.soft_recent_ipo_max_days:
        soft_flags.append("recent_ipo")

    if is_adr:
        soft_flags.append("adr")

    if avg_dollar_vol is not None and t.hard_min_avg_dollar_volume_20d_usd <= avg_dollar_vol < t.soft_low_liquidity_max_usd:
        soft_flags.append("low_liquidity")

    return ScreeningResult(ticker, passed=True, soft_flags=soft_flags, metrics=metrics)


def screen_universe(use_cache: bool = True, limit: Optional[int] = None) -> list[ScreeningResult]:
    """Screening market-wide penuh (NASDAQ + NYSE). Mahal -- jalankan berkala,
    bukan per request analisa. `limit` berguna untuk uji coba/dev supaya tidak
    menarik ribuan ticker sekaligus.

    Dibatch sesuai config.YF_BATCH_SIZE dengan jeda config.YF_BATCH_DELAY_SECONDS
    antar-batch, supaya tidak kena rate-limit Yahoo Finance saat memproses
    ribuan ticker sekaligus (lihat 04_DATA_SOURCES/05_RATE_LIMIT_CACHING_STRATEGY.md).
    """
    import time as _time

    universe = market_listings.get_universe(use_cache=use_cache)
    if limit:
        universe = universe[:limit]

    results = []
    batch_size = config.YF_BATCH_SIZE
    for batch_start in range(0, len(universe), batch_size):
        batch = universe[batch_start:batch_start + batch_size]
        for sec in batch:
            is_adr = "adr" in sec.name.lower() or "american depositary" in sec.name.lower()
            result = screen_ticker(
                sec.symbol,
                security_type=sec.security_type,
                is_test_issue=sec.is_test_issue,
                is_adr=is_adr,
            )
            results.append(result)
        if batch_start + batch_size < len(universe):
            _time.sleep(config.YF_BATCH_DELAY_SECONDS)
    return results
