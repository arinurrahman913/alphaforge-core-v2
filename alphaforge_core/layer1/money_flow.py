"""
Money Flow — 02_LAYER1_SPECS/03_MONEY_FLOW.md
Proxy dari volume abnormal + price action sector ETF (EPFR/Lipper resmi berbayar).
"""
from __future__ import annotations

from .. import config
from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .common import error_reading, make_reading

COMPONENT = "money_flow"


def compute() -> dict:
    try:
        per_sector = {}
        for etf, sector_name in config.SECTOR_ETFS.items():
            hist = yf_provider.get_price_history(etf, period="3mo")
            if hist is None or hist.empty or len(hist) < 21:
                continue
            recent_vol = hist["Volume"].iloc[-5:].mean()
            baseline_vol = hist["Volume"].iloc[-21:-5].mean()
            vol_ratio = round(recent_vol / baseline_vol, 3) if baseline_vol else None
            price_chg_5d = round((hist["Close"].iloc[-1] / hist["Close"].iloc[-6] - 1) * 100, 3) \
                if len(hist) > 6 else None

            if vol_ratio is not None and price_chg_5d is not None:
                if vol_ratio > 1.2 and price_chg_5d > 0:
                    direction = "inflow"
                elif vol_ratio > 1.2 and price_chg_5d < 0:
                    direction = "outflow"
                else:
                    direction = "neutral"
            else:
                direction = "unknown"

            per_sector[etf] = {
                "sector": sector_name,
                "volume_ratio_recent_vs_baseline": vol_ratio,
                "price_change_5d_pct": price_chg_5d,
                "direction_proxy": direction,
            }
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "derived_approximated", str(exc))

    inflow_sectors = [d["sector"] for d in per_sector.values() if d["direction_proxy"] == "inflow"]
    outflow_sectors = [d["sector"] for d in per_sector.values() if d["direction_proxy"] == "outflow"]

    return make_reading(
        COMPONENT, "derived_approximated",
        value={"inflow_sectors": inflow_sectors, "outflow_sectors": outflow_sectors},
        detail={
            "per_sector": per_sector,
            "note": "Proxy dari volume abnormal + price action sector ETF -- BUKAN data flow "
                    "granular resmi (EPFR/Lipper berbayar). Lihat Prinsip #5.",
        },
    )
