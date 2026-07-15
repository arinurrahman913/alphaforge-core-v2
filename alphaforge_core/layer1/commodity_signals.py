"""
Commodity Signals — 02_LAYER1_SPECS/11_COMMODITY_SIGNALS.md
Sumber: Yahoo Finance futures (GC=F emas, CL=F minyak) -> direct.
"""
from __future__ import annotations

from .. import config
from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .common import error_reading, make_reading

COMPONENT = "commodity_signals"


def _trend(hist) -> dict | None:
    if hist is None or hist.empty or len(hist) < 22:
        return None
    latest = float(hist["Close"].iloc[-1])
    chg_1m = round((latest / float(hist["Close"].iloc[-22]) - 1) * 100, 3)
    volatility = round(float(hist["Close"].pct_change().std() * 100), 3)
    return {"latest": round(latest, 2), "change_1m_pct": chg_1m, "volatility_daily_pct": volatility}


def compute() -> dict:
    try:
        gold_hist = yf_provider.get_price_history(config.GOLD_TICKER, period="6mo")
        oil_hist = yf_provider.get_price_history(config.OIL_TICKER, period="6mo")
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "direct", str(exc))

    gold = _trend(gold_hist)
    oil = _trend(oil_hist)

    risk_tone = "unknown"
    if gold and oil:
        if gold["change_1m_pct"] > 2 and oil["change_1m_pct"] < 0:
            risk_tone = "risk_off_flight_to_safety"
        elif oil["change_1m_pct"] > 2 and gold["change_1m_pct"] < 1:
            risk_tone = "risk_on_growth_demand"
        else:
            risk_tone = "mixed"

    return make_reading(
        COMPONENT, "direct",
        value=risk_tone,
        detail={"gold": gold, "oil": oil},
    )
