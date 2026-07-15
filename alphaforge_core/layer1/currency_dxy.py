"""
Currency / Dollar Index (DXY) — 02_LAYER1_SPECS/10_CURRENCY_DXY.md
Sumber: Yahoo Finance DX-Y.NYB -> direct.
"""
from __future__ import annotations

from .. import config
from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .common import error_reading, make_reading

COMPONENT = "currency_dxy"


def compute() -> dict:
    try:
        hist = yf_provider.get_price_history(config.DXY_TICKER, period="2y")
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "direct", str(exc))

    if hist is None or hist.empty:
        return error_reading(COMPONENT, "direct", "Data DXY kosong dari Yahoo Finance")

    latest = float(hist["Close"].iloc[-1])
    avg = float(hist["Close"].mean())
    chg_3m = None
    if len(hist) > 63:
        chg_3m = round((latest / float(hist["Close"].iloc[-64]) - 1) * 100, 3)

    trend = "strengthening" if (chg_3m or 0) > 1 else "weakening" if (chg_3m or 0) < -1 else "flat"

    return make_reading(
        COMPONENT, "direct",
        value=trend,
        detail={
            "dxy_latest": round(latest, 2),
            "dxy_2y_average": round(avg, 2),
            "change_3m_pct": chg_3m,
        },
    )
