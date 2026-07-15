"""
Evidence — 03_LAYER2_SPECS/02_EVIDENCE.md

Murni pengumpulan fakta per ticker, tiap field ditandai source + fetched_at
(bahan Confidence/Data Quality di tahap berikutnya). TIDAK ada interpretasi
di sini (Prinsip #1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..config import DataUnavailableError
from ..providers import finnhub, yahoo_finance as yf_provider


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _field(value, source: str, error: Optional[str] = None) -> dict:
    return {"value": value, "source": source, "fetched_at": _now(), "error": error}


@dataclass
class Evidence:
    ticker: str
    snapshot_date: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ticker": self.ticker, "snapshot_date": self.snapshot_date, "fields": self.fields}


def collect_evidence(ticker: str, news_days_back: int = 90) -> Evidence:
    """Kumpulkan Evidence untuk satu ticker mengikuti urutan di spec bagian 3:
    1) harga & fundamental ringkas (Yahoo Finance)
    2) kepemilikan institusional (Finnhub, fallback SEC EDGAR -- fallback belum
       diimplementasikan di v2.0 awal ini, ditandai eksplisit kalau Finnhub gagal)
    3) berita terkini (Finnhub)
    """
    ev = Evidence(ticker=ticker)

    # 1. Harga & pasar
    try:
        hist = yf_provider.get_price_history(ticker, period="5y")
        fast_info = yf_provider.get_fast_info(ticker)
        # Simpan ~5 tahun (bukan cuma 252 hari) supaya cukup buffer untuk
        # hitung return 1/3/5 tahun (butuh index -253/-757/-1261, kalau cuma
        # nyimpen tepat 252 baris, lookback 1 tahun selalu gagal karena
        # len(hist) <= days terpenuhi persis di batas -- ini bug yang sudah
        # diperbaiki, lihat catatan di knowledge.py).
        ev.fields["price_history"] = _field(
            hist.reset_index().to_dict(orient="records") if hist is not None and not hist.empty else [],
            source="yahoo_finance",
        )
        ev.fields["market_stats"] = _field(fast_info, source="yahoo_finance")
    except DataUnavailableError as exc:
        ev.fields["price_history"] = _field(None, source="yahoo_finance", error=str(exc))
        ev.fields["market_stats"] = _field(None, source="yahoo_finance", error=str(exc))

    # 1b. Fundamental ringkas (kuartalan) + tahunan (untuk CAGR 3-5 tahun,
    # karena quarterly biasanya cuma 4-5 kuartal terakhir dari Yahoo Finance)
    try:
        full_info = yf_provider.get_full_info(ticker)
        qfin = yf_provider.get_quarterly_financials(ticker)
        afin = yf_provider.get_annual_financials(ticker)
        ev.fields["fundamentals_summary"] = _field(full_info, source="yahoo_finance")
        ev.fields["quarterly_financials"] = _field(qfin, source="yahoo_finance")
        ev.fields["annual_financials"] = _field(afin, source="yahoo_finance")
    except DataUnavailableError as exc:
        ev.fields["fundamentals_summary"] = _field(None, source="yahoo_finance", error=str(exc))
        ev.fields["quarterly_financials"] = _field(None, source="yahoo_finance", error=str(exc))
        ev.fields["annual_financials"] = _field(None, source="yahoo_finance", error=str(exc))

    # 1c. Insider transactions (gratis lewat Yahoo Finance)
    try:
        insider_txns = yf_provider.get_insider_transactions(ticker)
        ev.fields["insider_transactions"] = _field(insider_txns, source="yahoo_finance")
    except DataUnavailableError as exc:
        ev.fields["insider_transactions"] = _field(None, source="yahoo_finance", error=str(exc))

    # 2. Kepemilikan institusional (Jalur A: Finnhub; fallback SEC EDGAR 13F belum
    #    diimplementasikan -- lihat catatan "Yang Masih Perlu Diputuskan" di README v2)
    try:
        inst = finnhub.get_institutional_ownership(ticker)
        ev.fields["institutional_ownership"] = _field(inst, source="finnhub")
    except DataUnavailableError as exc:
        ev.fields["institutional_ownership"] = _field(None, source="finnhub", error=str(exc))

    # 3. Berita
    try:
        news = finnhub.get_company_news(ticker, days_back=news_days_back)
        ev.fields["news"] = _field(news, source="finnhub")
    except DataUnavailableError as exc:
        ev.fields["news"] = _field(None, source="finnhub", error=str(exc))

    # 5. SEC filings umum (untuk Risk/Red-Flag Check)
    try:
        filings = finnhub.get_company_filings(ticker)
        ev.fields["sec_filings"] = _field(filings, source="finnhub")
    except DataUnavailableError as exc:
        ev.fields["sec_filings"] = _field(None, source="finnhub", error=str(exc))

    return ev
