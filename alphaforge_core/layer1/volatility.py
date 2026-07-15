"""
Volatility Index (VIX) — 02_LAYER1_SPECS/07_VOLATILITY_INDEX.md
Sumber: Yahoo Finance ^VIX -> direct API.
"""
from __future__ import annotations

from .. import config
from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .common import error_reading, make_reading

COMPONENT = "volatility_index"


def compute() -> dict:
    try:
        hist = yf_provider.get_price_history(config.VIX_TICKER, period="2y")
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "direct", str(exc))

    if hist is None or hist.empty:
        return error_reading(COMPONENT, "direct", "Data VIX kosong dari Yahoo Finance")

    latest = float(hist["Close"].iloc[-1])
    historical_avg = float(hist["Close"].mean())

    if latest < 15:
        level = "low_risk_on"
    elif latest < 25:
        level = "normal"
    else:
        level = "high_risk_off"

    return make_reading(
        COMPONENT, "direct",
        value=level,
        detail={
            "vix_latest": round(latest, 2),
            "vix_2y_average": round(historical_avg, 2),
            "vs_average": round(latest - historical_avg, 2),
        },
    )
