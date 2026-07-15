"""
Liquidity Conditions — 02_LAYER1_SPECS/04_LIQUIDITY_CONDITIONS.md
Sumber: FRED (Fed balance sheet, M2, credit spread) -> "direct" (data resmi),
tapi KESIMPULAN gabungannya (tightening/loosening) tetap butuh logika sendiri,
jadi label akhirnya "derived_approximated" mengikuti semangat komponen ini di
Glosarium walau data mentahnya resmi.
"""
from __future__ import annotations

from ..config import DataUnavailableError
from ..providers import fred
from .common import error_reading, make_reading

COMPONENT = "liquidity_conditions"


def _pct_change(series: list[dict], periods_back: int = 12) -> float | None:
    values = [obs["value"] for obs in series if obs["value"] is not None]
    if len(values) <= periods_back:
        return None
    latest, past = values[0], values[periods_back]
    if past == 0:
        return None
    return round((latest - past) / abs(past) * 100, 3)


def compute() -> dict:
    try:
        fed_bs = fred.get_series(_sid("fed_balance_sheet"), limit=60)
        m2 = fred.get_series(_sid("m2_money_supply"), limit=60)
        credit_spread_series = fred.get_series(_sid("credit_spread_baa10y"), limit=60)
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "derived_approximated", str(exc))

    fed_bs_trend = _pct_change(fed_bs, periods_back=12)   # ~12 minggu (data mingguan)
    m2_growth = _pct_change(m2, periods_back=6)            # ~6 bulan (data bulanan)
    credit_spread = next((o["value"] for o in credit_spread_series if o["value"] is not None), None)

    signals = []
    if fed_bs_trend is not None:
        signals.append("expanding" if fed_bs_trend > 0.5 else "contracting" if fed_bs_trend < -0.5 else "flat")
    if m2_growth is not None:
        signals.append("expanding" if m2_growth > 1 else "contracting" if m2_growth < -1 else "flat")
    if credit_spread is not None:
        signals.append("tight" if credit_spread > 2.5 else "loose")

    contracting_votes = sum(1 for s in signals if s in ("contracting", "tight"))
    expanding_votes = sum(1 for s in signals if s in ("expanding", "loose"))

    if not signals:
        overall = "unknown"
    elif contracting_votes > expanding_votes:
        overall = "tightening"
    elif expanding_votes > contracting_votes:
        overall = "loosening"
    else:
        overall = "mixed"

    return make_reading(
        COMPONENT, "derived_approximated",
        value=overall,
        detail={
            "fed_balance_sheet_trend_pct": fed_bs_trend,
            "m2_growth_pct": m2_growth,
            "credit_spread_baa10y": credit_spread,
            "note": "Derived dari kombinasi Fed balance sheet + M2 + credit spread (FRED), bukan indeks likuiditas tunggal resmi.",
        },
    )


def _sid(name: str) -> str:
    from .. import config
    return config.FRED_SERIES[name]
