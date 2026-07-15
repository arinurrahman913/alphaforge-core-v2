"""
Sector Rotation — 02_LAYER1_SPECS/02_SECTOR_ROTATION.md
Sumber: Yahoo Finance, sector ETF vs S&P 500 acuan.
"""
from __future__ import annotations

import pandas as pd

from .. import config
from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .common import error_reading, make_reading

COMPONENT = "sector_rotation"


def _relative_return(etf_hist: pd.DataFrame, bench_hist: pd.DataFrame, days: int) -> float | None:
    if etf_hist is None or etf_hist.empty or bench_hist is None or bench_hist.empty:
        return None
    if len(etf_hist) <= days or len(bench_hist) <= days:
        return None
    etf_ret = (etf_hist["Close"].iloc[-1] / etf_hist["Close"].iloc[-days - 1] - 1) * 100
    bench_ret = (bench_hist["Close"].iloc[-1] / bench_hist["Close"].iloc[-days - 1] - 1) * 100
    return round(etf_ret - bench_ret, 3)


def compute() -> dict:
    try:
        bench_hist = yf_provider.get_price_history(config.BENCHMARK_INDEX_TICKER, period="1y")
        etf_results = {}
        for etf, sector_name in config.SECTOR_ETFS.items():
            hist = yf_provider.get_price_history(etf, period="1y")
            etf_results[etf] = {
                "sector": sector_name,
                "relative_return_1m_pct": _relative_return(hist, bench_hist, 21),
                "relative_return_3m_pct": _relative_return(hist, bench_hist, 63),
            }
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "direct", str(exc))

    ranked_3m = sorted(
        ((etf, d) for etf, d in etf_results.items() if d["relative_return_3m_pct"] is not None),
        key=lambda kv: kv[1]["relative_return_3m_pct"], reverse=True,
    )
    inflow = [f"{d['sector']} ({etf})" for etf, d in ranked_3m[:3]]
    outflow = [f"{d['sector']} ({etf})" for etf, d in ranked_3m[-3:]] if ranked_3m else []

    return make_reading(
        COMPONENT, "direct",
        value={"inflow_sectors": inflow, "outflow_sectors": outflow},
        detail={"per_sector": etf_results},
    )
