"""
Tes logika klasifikasi Layer 1 — provider di-monkeypatch supaya tidak ada
panggilan network sama sekali (sandbox ini tidak punya akses ke Yahoo
Finance/FRED). Fokus: apakah aturan klasifikasi (inverted/normal, bull/bear,
dst) benar terhadap data yang diketahui.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alphaforge_core.layer1 import yield_curve, market_regime, volatility, market_sentiment
from alphaforge_core.providers import fred as fred_provider
from alphaforge_core.providers import yahoo_finance as yf_provider


def test_yield_curve_inverted(monkeypatch):
    def fake_get_series(series_id, limit=60, use_cache=True):
        mapping = {
            "DGS3MO": [{"date": "2026-07-01", "value": 5.3}],
            "DGS2": [{"date": "2026-07-01", "value": 4.8}],
            "DGS10": [{"date": "2026-07-01", "value": 4.0}],
        }
        return mapping[series_id]

    monkeypatch.setattr(fred_provider, "get_series", fake_get_series)
    result = yield_curve.compute()
    assert result["value"] == "inverted"
    assert result["detail"]["spread_10y_2y"] == -0.8
    print("OK: yield curve correctly classified as inverted when 10Y < 2Y")


def test_yield_curve_normal(monkeypatch):
    def fake_get_series(series_id, limit=60, use_cache=True):
        mapping = {
            "DGS3MO": [{"date": "2026-07-01", "value": 3.0}],
            "DGS2": [{"date": "2026-07-01", "value": 3.5}],
            "DGS10": [{"date": "2026-07-01", "value": 4.5}],
        }
        return mapping[series_id]

    monkeypatch.setattr(fred_provider, "get_series", fake_get_series)
    result = yield_curve.compute()
    assert result["value"] == "normal"
    print("OK: yield curve correctly classified as normal when 10Y > 2Y with healthy spread")


def _fake_price_df(prices):
    return pd.DataFrame({"Close": prices, "Volume": [1_000_000] * len(prices)})


def test_market_regime_bull(monkeypatch):
    # Harga naik terus -> last > ma50 > ma200
    prices = [100 + i * 0.5 for i in range(300)]

    def fake_get_price_history(ticker, period="2y", interval="1d", use_cache=True):
        return _fake_price_df(prices)

    monkeypatch.setattr(yf_provider, "get_price_history", fake_get_price_history)
    result = market_regime.compute()
    assert result["value"] == "bull_above_ma200"
    print("OK: market regime correctly classified as bull when price trending up above MA50/MA200")


def test_market_regime_bear(monkeypatch):
    prices = [200 - i * 0.5 for i in range(300)]

    def fake_get_price_history(ticker, period="2y", interval="1d", use_cache=True):
        return _fake_price_df(prices)

    monkeypatch.setattr(yf_provider, "get_price_history", fake_get_price_history)
    result = market_regime.compute()
    assert result["value"] == "bear_below_ma200"
    print("OK: market regime correctly classified as bear when price trending down below MA50/MA200")


def test_volatility_low_risk_on(monkeypatch):
    prices = [12.0] * 500

    def fake_get_price_history(ticker, period="2y", interval="1d", use_cache=True):
        return _fake_price_df(prices)

    monkeypatch.setattr(yf_provider, "get_price_history", fake_get_price_history)
    result = volatility.compute()
    assert result["value"] == "low_risk_on"
    print("OK: VIX below 15 correctly classified as low_risk_on")


def test_market_sentiment_explicit_about_missing_inputs(monkeypatch):
    def fake_compute_vix():
        return {"component": "volatility_index", "kind": "direct", "value": "high_risk_off",
                "detail": {}, "as_of": "", "error": None}

    monkeypatch.setattr(market_sentiment, "compute_vix", fake_compute_vix)
    result = market_sentiment.compute(aaii_bull_bear_spread=None, put_call_ratio=None, breadth_health=None)
    assert result["value"] == "fear"
    assert "aaii_bull_bear_spread" in result["detail"]["inputs_missing"]
    assert "put_call_ratio" in result["detail"]["inputs_missing"]
    print("OK: market sentiment still computes from available VIX signal and explicitly lists missing inputs")


if __name__ == "__main__":
    import types

    class _MonkeyPatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _MonkeyPatch()
    test_yield_curve_inverted(mp)
    test_yield_curve_normal(mp)
    test_market_regime_bull(mp)
    test_market_regime_bear(mp)
    test_volatility_low_risk_on(mp)
    test_market_sentiment_explicit_about_missing_inputs(mp)
    print("\nALL LAYER 1 LOGIC TESTS PASSED")
