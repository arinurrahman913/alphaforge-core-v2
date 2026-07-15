"""
Business Cycle Stage — 02_LAYER1_SPECS/01_BUSINESS_CYCLE_STAGE.md
Derived/approximated dari kombinasi PMI proxy, GDP QoQ, unemployment trend (FRED).
"""
from __future__ import annotations

from ..config import DataUnavailableError
from ..providers import fred
from .common import error_reading, make_reading
from .yield_curve import compute as compute_yield_curve  # dipakai sbg konteks tambahan

COMPONENT = "business_cycle_stage"


def _series_values(obs_list):
    return [o["value"] for o in obs_list if o["value"] is not None]


def compute() -> dict:
    try:
        gdp = fred.get_series(_sid("gdp_growth"), limit=8)
        unemployment = fred.get_series(_sid("unemployment_rate"), limit=13)
        pmi_proxy = fred.get_series(_sid("ism_pmi_proxy"), limit=13)
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "derived_approximated", str(exc))

    gdp_vals = _series_values(gdp)
    unemp_vals = _series_values(unemployment)
    pmi_vals = _series_values(pmi_proxy)

    gdp_latest = gdp_vals[0] if gdp_vals else None
    unemp_latest = unemp_vals[0] if unemp_vals else None
    unemp_trend_up = (
        unemp_vals[0] > unemp_vals[6] if len(unemp_vals) > 6 else None
    )
    pmi_trend_up = (
        pmi_vals[0] > pmi_vals[6] if len(pmi_vals) > 6 else None
    )

    # Klasifikasi kasar & eksplisit (aturan sendiri, bukan angka resmi tunggal):
    # - recession: GDP negatif dua sinyal berturut / unemployment naik tajam
    # - late-cycle: GDP positif tapi melambat & unemployment mulai naik
    # - mid-cycle: GDP stabil positif, unemployment stabil/turun
    # - early-cycle: GDP rebound kuat dari titik rendah, unemployment masih tinggi tapi turun
    if gdp_latest is not None and gdp_latest < 0:
        stage = "recession"
    elif unemp_trend_up and gdp_latest is not None and gdp_latest < 1.5:
        stage = "late-cycle"
    elif gdp_latest is not None and gdp_latest >= 3 and unemp_trend_up is False:
        stage = "early-cycle"
    elif gdp_latest is not None:
        stage = "mid-cycle"
    else:
        stage = "unknown"

    return make_reading(
        COMPONENT, "derived_approximated",
        value=stage,
        detail={
            "gdp_growth_latest_pct": gdp_latest,
            "unemployment_rate_latest": unemp_latest,
            "unemployment_trend_up": unemp_trend_up,
            "pmi_proxy_trend_up": pmi_trend_up,
            "note": "Klasifikasi hasil kombinasi indikator FRED (GDP QoQ, unemployment, proxy PMI) "
                    "-- bukan angka resmi tunggal dari satu sumber otoritatif (Prinsip #5).",
        },
    )


def _sid(name: str) -> str:
    from .. import config
    return config.FRED_SERIES[name]
