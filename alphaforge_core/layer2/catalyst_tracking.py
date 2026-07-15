"""
Catalyst Tracking — 03_LAYER2_SPECS/10_CATALYST_TRACKING.md
Identifikasi peristiwa mendatang (earnings, dsb) yang relevan untuk Speculative Module.
"""
from __future__ import annotations

from datetime import date, datetime

from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .evidence import Evidence


def identify_catalysts(ticker: str, ev: Evidence) -> list[dict]:
    catalysts = []

    try:
        cal = yf_provider.get_calendar(ticker)
    except DataUnavailableError:
        cal = None

    if cal:
        earnings_dates = cal.get("Earnings Date") or cal.get("earnings_date")
        if earnings_dates:
            dates = earnings_dates if isinstance(earnings_dates, list) else [earnings_dates]
            for d in dates:
                d_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
                catalysts.append({
                    "type": "earnings_report",
                    "estimated_date": d_str,
                    "impact_note": "Volatilitas biasanya meningkat di sekitar tanggal earnings.",
                    "source": "yahoo_finance_calendar",
                })

    news = ev.fields.get("news", {}).get("value") or []
    catalyst_keywords = ["fda approval", "phase 3", "acquisition", "merger", "product launch",
                         "partnership", "contract award", "patent"]
    for item in news:
        headline = str(item.get("headline", "")).lower()
        if any(kw in headline for kw in catalyst_keywords):
            catalysts.append({
                "type": "news_derived_catalyst",
                "estimated_date": None,
                "headline": item.get("headline"),
                "published_at": item.get("datetime"),
                "source": "finnhub_news",
            })

    return catalysts
