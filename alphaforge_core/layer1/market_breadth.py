"""
Market Breadth — 02_LAYER1_SPECS/06_MARKET_BREADTH.md
Derived dari advance/decline ratio + % saham di atas MA200 dari konstituen index.

Catatan implementasi: menghitung breadth "penuh" butuh daftar konstituen index
resmi (S&P 500 / NASDAQ) + harga tiap saham -- mahal secara panggilan API kalau
dilakukan tiap sesi. Modul ini menyediakan constituents_provider yang bisa
disuplai dari luar (mis. daftar S&P 500 dari cache/CSV) supaya tidak terikat
1 sumber data konstituen tunggal di kode inti.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from ..config import DataUnavailableError
from ..providers import yahoo_finance as yf_provider
from .common import error_reading, make_reading

COMPONENT = "market_breadth"


def compute(constituents: Optional[Iterable[str]] = None,
            constituents_provider: Optional[Callable[[], Iterable[str]]] = None) -> dict:
    if constituents is None and constituents_provider is not None:
        constituents = constituents_provider()
    if not constituents:
        return error_reading(
            COMPONENT, "derived_approximated",
            "Daftar konstituen index tidak disuplai. Market Breadth butuh daftar "
            "ticker S&P 500/NASDAQ (constituents) untuk dihitung -- lihat "
            "02_LAYER1_SPECS/06_MARKET_BREADTH.md.",
        )

    advancing, declining, above_ma200, total_with_data = 0, 0, 0, 0
    try:
        for ticker in constituents:
            hist = yf_provider.get_price_history(ticker, period="1y")
            if hist is None or hist.empty or len(hist) < 2:
                continue
            total_with_data += 1
            last_close = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[-2]
            if last_close > prev_close:
                advancing += 1
            elif last_close < prev_close:
                declining += 1
            if len(hist) >= 200:
                ma200 = hist["Close"].rolling(200).mean().iloc[-1]
                if last_close > ma200:
                    above_ma200 += 1
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "derived_approximated", str(exc))

    if total_with_data == 0:
        return error_reading(COMPONENT, "derived_approximated", "Tidak ada data harga yang berhasil ditarik untuk konstituen.")

    ad_ratio = round(advancing / declining, 3) if declining > 0 else None
    pct_above_ma200 = round(above_ma200 / total_with_data * 100, 2)

    if pct_above_ma200 >= 60:
        health = "broad_strength"
    elif pct_above_ma200 <= 35:
        health = "narrow_weak"
    else:
        health = "mixed"

    return make_reading(
        COMPONENT, "derived_approximated",
        value=health,
        detail={
            "advancing": advancing,
            "declining": declining,
            "advance_decline_ratio": ad_ratio,
            "pct_above_ma200": pct_above_ma200,
            "constituents_evaluated": total_with_data,
            "note": "Dihitung dari sampel konstituen yang disuplai caller, bukan endpoint breadth siap pakai.",
        },
    )
