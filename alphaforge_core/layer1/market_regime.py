"""
Market Regime — 02_LAYER1_SPECS/08_MARKET_REGIME.md
Posisi index utama relatif terhadap MA50/MA200.
"""
from __future__ import annotations

from .. import config
from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .common import error_reading, make_reading

COMPONENT = "market_regime"


def _classify(hist) -> tuple[str, dict]:
    close = hist["Close"]
    last = float(close.iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    if ma50 is None or ma200 is None:
        return "unknown", {"last": last, "ma50": ma50, "ma200": ma200}

    if last > ma50 > ma200:
        regime = "bull_above_ma200"
    elif last < ma50 < ma200:
        regime = "bear_below_ma200"
    else:
        regime = "sideways_mixed"

    return regime, {"last": round(last, 2), "ma50": round(ma50, 2), "ma200": round(ma200, 2)}


def compute() -> dict:
    try:
        results = {}
        for name, ticker in config.MAIN_INDICES.items():
            hist = yf_provider.get_price_history(ticker, period="2y")
            if hist is None or hist.empty:
                results[name] = {"regime": "unknown", "detail": {}}
                continue
            regime, detail = _classify(hist)
            results[name] = {"regime": regime, "detail": detail}
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "direct", str(exc))

    regimes = [v["regime"] for v in results.values() if v["regime"] != "unknown"]
    if regimes and all(r == regimes[0] for r in regimes):
        overall = regimes[0]
    elif regimes:
        overall = "mixed_across_indices"
    else:
        overall = "unknown"

    return make_reading(COMPONENT, "direct", value=overall, detail={"per_index": results})
