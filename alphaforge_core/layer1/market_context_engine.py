"""
Market Context Engine — orkestrator Layer 1.

Menggabungkan 12 komponen jadi satu Market Context Package, sesuai
01_ARCHITECTURE/02_LAYER1_MARKET_CONTEXT.md. Dihitung SEKALI per sesi analisa
(lihat docstring `build_market_context_package` untuk cara pakai yang benar).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from . import (
    business_cycle,
    commodity_signals,
    currency_dxy,
    liquidity,
    macro_calendar,
    market_breadth,
    market_regime,
    market_sentiment,
    money_flow,
    sector_rotation,
    volatility,
    yield_curve,
)


def build_market_context_package(
    breadth_constituents: Optional[Iterable[str]] = None,
    breadth_constituents_provider: Optional[Callable[[], Iterable[str]]] = None,
    aaii_bull_bear_spread: Optional[float] = None,
    put_call_ratio: Optional[float] = None,
) -> dict:
    """Hitung Market Context Package sekali, lalu pakai hasilnya untuk SEMUA
    saham yang dianalisa di sesi yang sama (jangan panggil ulang per ticker --
    lihat 01_ARCHITECTURE/02_LAYER1_MARKET_CONTEXT.md bagian 4).

    breadth_constituents: daftar ticker index (mis. S&P 500) untuk Market Breadth.
        Kalau tidak disuplai, komponen breadth akan error_reading secara eksplisit
        (bukan angka dikira-kira).
    aaii_bull_bear_spread, put_call_ratio: input manual opsional untuk Market
        Sentiment (lihat docstring market_sentiment.py kenapa ini tidak
        di-scrape otomatis).
    """
    components = {}

    components["business_cycle_stage"] = _safe(business_cycle.compute)
    components["sector_rotation"] = _safe(sector_rotation.compute)
    components["money_flow"] = _safe(money_flow.compute)
    components["liquidity_conditions"] = _safe(liquidity.compute)
    components["yield_curve"] = _safe(yield_curve.compute)
    components["market_breadth"] = _safe(
        lambda: market_breadth.compute(breadth_constituents, breadth_constituents_provider)
    )
    components["volatility_index"] = _safe(volatility.compute)
    components["market_regime"] = _safe(market_regime.compute)
    components["macro_calendar"] = _safe(macro_calendar.compute)
    components["currency_dxy"] = _safe(currency_dxy.compute)
    components["commodity_signals"] = _safe(commodity_signals.compute)

    breadth_health = components["market_breadth"].get("value")
    components["market_sentiment"] = _safe(
        lambda: market_sentiment.compute(aaii_bull_bear_spread, put_call_ratio, breadth_health)
    )

    n_errors = sum(1 for c in components.values() if c.get("error"))

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
        "components_with_errors": n_errors,
        "components_total": len(components),
    }


def _safe(fn) -> dict:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - orkestrator tidak boleh crash total karena 1 komponen gagal
        return {
            "component": "unknown",
            "kind": "unknown",
            "value": None,
            "detail": {},
            "as_of": datetime.now(timezone.utc).isoformat(),
            "error": f"Kegagalan tak terduga: {exc}",
        }
