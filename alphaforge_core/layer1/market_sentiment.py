"""
Market Sentiment — 02_LAYER1_SPECS/12_MARKET_SENTIMENT.md
Derived dari AAII survey + CBOE put/call ratio + VIX + breadth.

AAII (mingguan, XLS download) dan CBOE put/call ratio TIDAK punya endpoint JSON
resmi gratis yang stabil untuk di-scrape otomatis secara aman (lihat catatan ToS
di 02_LAYER1_SPECS/09_MACRO_CALENDAR.md yang berlaku semangatnya juga di sini).
Supaya kode ini tidak diam-diam melakukan scraping situs pihak ketiga, kedua
angka itu disuplai sebagai parameter opsional oleh caller (mis. diinput manual
mingguan, atau dari sumber yang sudah dilanggan/diverifikasi terpisah). Kalau
tidak disuplai, komponen tetap menghasilkan pembacaan dari VIX + breadth saja
dan menandai bagian yang hilang secara eksplisit.
"""
from __future__ import annotations

from typing import Optional

from .common import make_reading
from .volatility import compute as compute_vix

COMPONENT = "market_sentiment"


def compute(aaii_bull_bear_spread: Optional[float] = None,
            put_call_ratio: Optional[float] = None,
            breadth_health: Optional[str] = None) -> dict:
    vix_reading = compute_vix()
    vix_level = vix_reading.get("value")

    votes_fear, votes_greed, votes_total = 0, 0, 0

    if vix_level is not None and vix_reading.get("error") is None:
        votes_total += 1
        if vix_level == "high_risk_off":
            votes_fear += 1
        elif vix_level == "low_risk_on":
            votes_greed += 1

    if aaii_bull_bear_spread is not None:
        votes_total += 1
        if aaii_bull_bear_spread < -10:
            votes_fear += 1
        elif aaii_bull_bear_spread > 10:
            votes_greed += 1

    if put_call_ratio is not None:
        votes_total += 1
        if put_call_ratio > 1.0:
            votes_fear += 1
        elif put_call_ratio < 0.7:
            votes_greed += 1

    if breadth_health is not None:
        votes_total += 1
        if breadth_health == "narrow_weak":
            votes_fear += 1
        elif breadth_health == "broad_strength":
            votes_greed += 1

    if votes_total == 0:
        sentiment = "unknown"
    elif votes_fear > votes_greed:
        sentiment = "fear"
    elif votes_greed > votes_fear:
        sentiment = "greed"
    else:
        sentiment = "neutral"

    missing_inputs = [
        name for name, val in (
            ("aaii_bull_bear_spread", aaii_bull_bear_spread),
            ("put_call_ratio", put_call_ratio),
            ("breadth_health", breadth_health),
        ) if val is None
    ]

    return make_reading(
        COMPONENT, "derived_approximated",
        value=sentiment,
        detail={
            "vix_component": vix_reading.get("value"),
            "aaii_bull_bear_spread": aaii_bull_bear_spread,
            "put_call_ratio": put_call_ratio,
            "breadth_health": breadth_health,
            "inputs_missing": missing_inputs,
            "note": "Bukan versi identik Fear & Greed Index CNN. AAII/put-call tidak "
                    "punya API resmi gratis stabil -- harus disuplai caller kalau ingin dipakai.",
        },
    )
