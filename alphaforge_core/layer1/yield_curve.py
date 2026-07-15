"""
Yield Curve — 02_LAYER1_SPECS/05_YIELD_CURVE.md

Sumber: FRED (data resmi, gratis) -> "direct" API (bukan derived), sesuai
klasifikasi di 04_DATA_SOURCES/01_PROVIDERS_OVERVIEW.md bagian 2.
"""
from __future__ import annotations

from ..config import DataUnavailableError
from ..providers import fred
from .common import error_reading, make_reading

COMPONENT = "yield_curve"


def _latest_value(series: list[dict]) -> float | None:
    for obs in series:
        if obs["value"] is not None:
            return obs["value"]
    return None


def compute() -> dict:
    try:
        y3m = _latest_value(fred.get_series(fred_series_id("treasury_3m")))
        y2y = _latest_value(fred.get_series(fred_series_id("treasury_2y")))
        y10y = _latest_value(fred.get_series(fred_series_id("treasury_10y")))
    except DataUnavailableError as exc:
        return error_reading(COMPONENT, "direct", str(exc))

    if y10y is None or y2y is None:
        return error_reading(COMPONENT, "direct", "Data treasury tidak lengkap dari FRED")

    spread_10y_2y = round(y10y - y2y, 4)
    spread_10y_3m = round(y10y - y3m, 4) if y3m is not None else None

    if spread_10y_2y < 0:
        shape = "inverted"
    elif spread_10y_2y < 0.25:
        shape = "flat"
    else:
        shape = "normal"

    return make_reading(
        COMPONENT, "direct",
        value=shape,
        detail={
            "treasury_3m": y3m,
            "treasury_2y": y2y,
            "treasury_10y": y10y,
            "spread_10y_2y": spread_10y_2y,
            "spread_10y_3m": spread_10y_3m,
        },
    )


def fred_series_id(name: str) -> str:
    from .. import config
    return config.FRED_SERIES[name]
