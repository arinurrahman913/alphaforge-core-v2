"""
Provider Yahoo Finance — lihat 04_DATA_SOURCES/02_YAHOO_FINANCE.md.

Catatan penting dari spec:
- Bukan API resmi (yfinance = scraping), rawan rate-limit -> wajib
  caching + batching + retry/backoff (05_RATE_LIMIT_CACHING_STRATEGY.md).
- Tidak punya endpoint "semua ticker" -> lihat market_listings.py.
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

import pandas as pd

from .. import config
from ..cache import default_cache
from ..config import DataUnavailableError

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None


def _require_yfinance():
    if yf is None:
        raise DataUnavailableError(
            "Package 'yfinance' tidak terinstall. Jalankan: pip install yfinance"
        )


def _with_retry(fn, max_retries: int = config.YF_MAX_RETRIES):
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - yfinance melempar berbagai exception generik
            last_exc = exc
            sleep_for = config.YF_RETRY_BACKOFF_BASE * (2 ** attempt)
            time.sleep(sleep_for)
    raise DataUnavailableError(f"Yahoo Finance gagal setelah {max_retries} percobaan: {last_exc}")


def get_price_history(ticker: str, period: str = "5y", interval: str = "1d",
                       use_cache: bool = True) -> pd.DataFrame:
    """OHLCV historis. Dipakai Evidence, Market Regime, Market Breadth, dll."""
    _require_yfinance()
    cache_key = f"price_history:{ticker}:{period}:{interval}"
    cache = default_cache()

    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            df = pd.DataFrame(cached)
            if not df.empty:
                # utc=True wajib di sini: tanggal yang disimpan bisa punya offset
                # timezone berbeda (mis. EST vs EDT akibat daylight saving), dan
                # pandas >= 2.x menolak parse mixed-offset tanpa utc=True.
                df["Date"] = pd.to_datetime(df["Date"], utc=True)
                df = df.set_index("Date")
            return df

    def _fetch():
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval)
        return hist

    hist = _with_retry(_fetch)
    if use_cache:
        serializable = hist.reset_index().to_dict(orient="records")
        # convert Timestamp -> iso string for json
        for row in serializable:
            if "Date" in row and hasattr(row["Date"], "isoformat"):
                row["Date"] = row["Date"].isoformat()
        cache.set(cache_key, serializable, config.TTL_SECONDS["price_history"])
    return hist


def get_fast_info(ticker: str, use_cache: bool = True) -> dict:
    """Info ringkas: market cap, shares outstanding, dll. Lebih murah daripada .info penuh."""
    _require_yfinance()
    cache_key = f"fast_info:{ticker}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _fetch():
        t = yf.Ticker(ticker)
        fi = dict(t.fast_info) if t.fast_info else {}
        return fi

    data = _with_retry(_fetch)
    if use_cache:
        cache.set(cache_key, data, config.TTL_SECONDS["fundamentals"])
    return data


def get_full_info(ticker: str, use_cache: bool = True) -> dict:
    """Info fundamental lebih lengkap (revenue, margin, dll ringkasan Yahoo)."""
    _require_yfinance()
    cache_key = f"full_info:{ticker}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _fetch():
        t = yf.Ticker(ticker)
        return dict(t.info) if t.info else {}

    data = _with_retry(_fetch)
    if use_cache:
        cache.set(cache_key, data, config.TTL_SECONDS["fundamentals"])
    return data


def get_quarterly_financials(ticker: str, use_cache: bool = True) -> dict:
    """Ringkasan income statement / balance sheet / cashflow kuartalan."""
    _require_yfinance()
    cache_key = f"qfinancials:{ticker}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _fetch():
        t = yf.Ticker(ticker)
        out = {}
        for name, df in (
            ("income_stmt", t.quarterly_income_stmt),
            ("balance_sheet", t.quarterly_balance_sheet),
            ("cashflow", t.quarterly_cashflow),
        ):
            if df is not None and not df.empty:
                d = df.copy()
                d.columns = [c.isoformat() if hasattr(c, "isoformat") else str(c) for c in d.columns]
                out[name] = d.reset_index().to_dict(orient="records")
            else:
                out[name] = []
        return out

    data = _with_retry(_fetch)
    if use_cache:
        cache.set(cache_key, data, config.TTL_SECONDS["fundamentals"])
    return data


def get_annual_financials(ticker: str, use_cache: bool = True) -> dict:
    """Ringkasan income statement / balance sheet / cashflow TAHUNAN.

    Dipakai sebagai fallback untuk revenue_cagr_3y_pct/5y_pct di Knowledge --
    quarterly_financials biasanya cuma nyediain 4-5 kuartal terakhir dari
    Yahoo Finance, tidak cukup untuk CAGR 3-5 tahun. Data tahunan biasanya
    tersedia untuk ~4 tahun terakhir.
    """
    _require_yfinance()
    cache_key = f"afinancials:{ticker}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _fetch():
        t = yf.Ticker(ticker)
        out = {}
        for name, df in (
            ("income_stmt", t.income_stmt),
            ("balance_sheet", t.balance_sheet),
            ("cashflow", t.cashflow),
        ):
            if df is not None and not df.empty:
                d = df.copy()
                d.columns = [c.isoformat() if hasattr(c, "isoformat") else str(c) for c in d.columns]
                out[name] = d.reset_index().to_dict(orient="records")
            else:
                out[name] = []
        return out

    data = _with_retry(_fetch)
    if use_cache:
        cache.set(cache_key, data, config.TTL_SECONDS["fundamentals"])
    return data


def get_insider_transactions(ticker: str, use_cache: bool = True) -> list[dict]:
    """Transaksi insider terbaru (beli/jual oleh eksekutif/direktur), gratis
    lewat Yahoo Finance. Dipakai untuk Knowledge.ownership.recent_insider_transactions.

    Catatan: struktur/nama kolom `Ticker.insider_transactions` bisa berubah
    antar versi yfinance -- kode pemanggil (evidence.py/knowledge.py) harus
    tetap defensif terhadap kolom yang hilang.
    """
    _require_yfinance()
    cache_key = f"insider_txn:{ticker}"
    cache = default_cache()
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    def _fetch():
        t = yf.Ticker(ticker)
        df = t.insider_transactions
        if df is None or df.empty:
            return []
        d = df.copy()
        for col in d.columns:
            if hasattr(d[col].iloc[0] if len(d) else None, "isoformat"):
                d[col] = d[col].apply(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
        return d.to_dict(orient="records")

    data = _with_retry(_fetch)
    if use_cache:
        cache.set(cache_key, data, config.TTL_SECONDS["institutional"])
    return data


def batch_download(tickers: Iterable[str], period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    """Unduh banyak ticker sekaligus dengan batching + delay antar batch,
    sesuai 04_DATA_SOURCES/05_RATE_LIMIT_CACHING_STRATEGY.md poin #3."""
    _require_yfinance()
    tickers = list(tickers)
    frames = []
    for i in range(0, len(tickers), config.YF_BATCH_SIZE):
        batch = tickers[i:i + config.YF_BATCH_SIZE]

        def _fetch(batch=batch):
            return yf.download(
                batch, period=period, interval=interval,
                group_by="ticker", progress=False, threads=True,
            )

        frames.append(_with_retry(_fetch))
        if i + config.YF_BATCH_SIZE < len(tickers):
            time.sleep(config.YF_BATCH_DELAY_SECONDS)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def get_calendar(ticker: str) -> Optional[dict]:
    """Kalender earnings mendatang — dipakai Catalyst Tracking."""
    _require_yfinance()

    def _fetch():
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return None
        if hasattr(cal, "to_dict"):
            return cal.to_dict()
        return dict(cal) if isinstance(cal, dict) else None

    return _with_retry(_fetch)
