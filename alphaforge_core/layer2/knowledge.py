"""
Knowledge — 03_LAYER2_SPECS/03_KNOWLEDGE.md

Aturan paling penting: HANYA fakta turunan (rasio, tren, kategori berbasis
ambang) -- TIDAK PERNAH kata sifat evaluatif ("bagus", "kuat", "berisiko").
Field yang datanya tidak tersedia diisi None + status "missing", tidak pernah
diinterpolasi/diestimasi (lihat bagian "Data Hilang" di spec).
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any, Optional

from .evidence import Evidence


def _missing() -> dict:
    return {"value": None, "status": "missing"}


def _present(value: Any) -> dict:
    return {"value": value, "status": "ok"}


@dataclass
class KnowledgeProfile:
    ticker: str
    identity: dict = dc_field(default_factory=dict)
    financial_health: dict = dc_field(default_factory=dict)
    competitive_position: dict = dc_field(default_factory=dict)
    historical_trends: dict = dc_field(default_factory=dict)
    ownership: dict = dc_field(default_factory=dict)
    metadata: dict = dc_field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "identity": self.identity,
            "financial_health": self.financial_health,
            "competitive_position": self.competitive_position,
            "historical_trends": self.historical_trends,
            "ownership": self.ownership,
            "metadata": self.metadata,
        }


def _find_line_item(records: list[dict], candidates: list[str]) -> Optional[dict]:
    """Cari baris (line item) di list of dict hasil quarterly financials
    berdasarkan beberapa kemungkinan nama field yfinance (index kolom pertama
    dari DataFrame reset_index() bernama 'index')."""
    if not records:
        return None
    for row in records:
        key = str(row.get("index", "")).strip().lower()
        for cand in candidates:
            if cand.lower() == key:
                return row
    return None


def _quarterly_series(row: Optional[dict]) -> list[Optional[float]]:
    """Ambil deret nilai kuartalan dari 1 baris (mengecualikan kolom 'index'),
    terurut sesuai urutan kolom aslinya (biasanya terbaru dulu dari yfinance)."""
    if row is None:
        return []
    values = []
    for k, v in row.items():
        if k == "index":
            continue
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            values.append(None)
    return values


def _yoy_growth(series: list[Optional[float]], periods_per_year: int = 4) -> Optional[float]:
    if len(series) <= periods_per_year:
        return None
    latest, year_ago = series[0], series[periods_per_year]
    if latest is None or year_ago is None or year_ago == 0:
        return None
    return round((latest - year_ago) / abs(year_ago) * 100, 3)


def _cagr(series: list[Optional[float]], periods: int, periods_per_year: int = 4) -> Optional[float]:
    idx = periods * periods_per_year
    if len(series) <= idx:
        return None
    latest, past = series[0], series[idx]
    if latest is None or past is None or past <= 0 or latest <= 0:
        return None
    return round(((latest / past) ** (1 / periods) - 1) * 100, 3)


# Heuristik kasar sektor/industri -> kategori model bisnis deskriptif.
# INI HEURISTIK BERBASIS KATA KUNCI, bukan klasifikasi otoritatif -- ditandai
# eksplisit sebagai "heuristic" di output supaya tidak dikira sumber resmi.
_BUSINESS_MODEL_KEYWORDS = [
    (("software", "internet", "information technology services"), "subscription_or_software"),
    (("semiconductor", "hardware", "electronic", "consumer electronics"), "hardware"),
    (("retail", "e-commerce", "internet retail"), "retail_or_marketplace"),
    (("bank", "insurance", "capital markets", "financial"), "financial_services"),
    (("biotechnology", "pharmaceutical", "drug"), "biotech_or_pharma"),
    (("oil", "gas", "energy"), "energy"),
    (("real estate", "reit"), "real_estate"),
    (("telecom",), "telecom"),
    (("utilities",), "utilities"),
]


def _classify_business_model(sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    text = f"{sector or ''} {industry or ''}".lower()
    if not text.strip():
        return None
    for keywords, category in _BUSINESS_MODEL_KEYWORDS:
        if any(kw in text for kw in keywords):
            return category
    return "other_uncategorized"


def build_knowledge(ev: Evidence, screening_soft_flags: Optional[list[str]] = None) -> KnowledgeProfile:
    kp = KnowledgeProfile(ticker=ev.ticker)
    screening_soft_flags = screening_soft_flags or []

    market_stats = ev.fields.get("market_stats", {}).get("value") or {}
    full_info = ev.fields.get("fundamentals_summary", {}).get("value") or {}
    qfin = ev.fields.get("quarterly_financials", {}).get("value") or {}
    afin = ev.fields.get("annual_financials", {}).get("value") or {}
    price_hist = ev.fields.get("price_history", {}).get("value") or []
    inst_own = ev.fields.get("institutional_ownership", {}).get("value")
    insider_txns_raw = ev.fields.get("insider_transactions", {}).get("value") or []

    # --- 1. Identitas & Klasifikasi ---
    size_tier = "unknown"
    for flag in ("micro_cap", "small_cap"):
        if flag in screening_soft_flags:
            size_tier = flag
    if size_tier == "unknown":
        mc = market_stats.get("market_cap") or full_info.get("marketCap")
        if mc:
            if mc >= 200_000_000_000:  # 200B — ambang mega-cap, sudah divalidasi (bukan angka final)
                size_tier = "mega_cap"
            elif mc >= 10_000_000_000:
                size_tier = "large_cap"
            elif mc >= 2_000_000_000:
                size_tier = "mid_cap"
            else:
                size_tier = "small_cap"

    kp.identity = {
        "ticker": ev.ticker,
        "exchange": _present(full_info.get("exchange")) if full_info.get("exchange") else _missing(),
        "sector": _present(full_info.get("sector")) if full_info.get("sector") else _missing(),
        "industry": _present(full_info.get("industry")) if full_info.get("industry") else _missing(),
        "size_tier": _present(size_tier),
        "instrument_flags": _present(screening_soft_flags),
    }

    # --- 2. Kesehatan Finansial ---
    income_records = qfin.get("income_stmt", [])
    balance_records = qfin.get("balance_sheet", [])
    cashflow_records = qfin.get("cashflow", [])

    revenue_row = _find_line_item(income_records, ["Total Revenue", "Revenue"])
    gross_profit_row = _find_line_item(income_records, ["Gross Profit"])
    op_income_row = _find_line_item(income_records, ["Operating Income", "Operating Revenue"])
    net_income_row = _find_line_item(income_records, ["Net Income", "Net Income Common Stockholders"])

    revenue_series = _quarterly_series(revenue_row)
    gross_profit_series = _quarterly_series(gross_profit_row)
    op_income_series = _quarterly_series(op_income_row)
    net_income_series = _quarterly_series(net_income_row)

    revenue_yoy = _yoy_growth(revenue_series)
    revenue_cagr_3y = _cagr(revenue_series, 3)
    revenue_cagr_5y = _cagr(revenue_series, 5)

    # Fallback ke data TAHUNAN kalau quarterly tidak cukup panjang (biasanya
    # Yahoo Finance cuma kasih 4-5 kuartal terakhir, tidak cukup untuk CAGR
    # 3-5 tahun yang butuh 12-20 kuartal). Data tahunan biasanya ada ~4 tahun.
    if revenue_cagr_3y is None or revenue_cagr_5y is None:
        annual_income_records = afin.get("income_stmt", [])
        annual_revenue_row = _find_line_item(annual_income_records, ["Total Revenue", "Revenue"])
        annual_revenue_series = _quarterly_series(annual_revenue_row)  # sebenarnya deret tahunan, fungsi sama
        if revenue_cagr_3y is None:
            revenue_cagr_3y = _cagr(annual_revenue_series, 3, periods_per_year=1)
        if revenue_cagr_5y is None:
            revenue_cagr_5y = _cagr(annual_revenue_series, 5, periods_per_year=1)

    gross_margin_series = [
        round(gp / rev * 100, 2) if (gp is not None and rev not in (None, 0)) else None
        for gp, rev in zip(gross_profit_series, revenue_series)
    ] if gross_profit_series and revenue_series else []
    op_margin_series = [
        round(op / rev * 100, 2) if (op is not None and rev not in (None, 0)) else None
        for op, rev in zip(op_income_series, revenue_series)
    ] if op_income_series and revenue_series else []
    net_margin_series = [
        round(ni / rev * 100, 2) if (ni is not None and rev not in (None, 0)) else None
        for ni, rev in zip(net_income_series, revenue_series)
    ] if net_income_series and revenue_series else []

    total_debt_row = _find_line_item(balance_records, ["Total Debt"])
    total_equity_row = _find_line_item(balance_records, ["Common Stock Equity", "Stockholders Equity"])
    current_assets_row = _find_line_item(balance_records, ["Current Assets"])
    current_liab_row = _find_line_item(balance_records, ["Current Liabilities"])
    cash_row = _find_line_item(balance_records, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])

    total_debt = _quarterly_series(total_debt_row)
    total_equity = _quarterly_series(total_equity_row)
    current_assets = _quarterly_series(current_assets_row)
    current_liab = _quarterly_series(current_liab_row)
    cash_series = _quarterly_series(cash_row)

    debt_to_equity = (
        round(total_debt[0] / total_equity[0], 3)
        if total_debt and total_equity and total_debt[0] is not None and total_equity[0] not in (None, 0)
        else None
    )
    current_ratio = (
        round(current_assets[0] / current_liab[0], 3)
        if current_assets and current_liab and current_assets[0] is not None and current_liab[0] not in (None, 0)
        else None
    )

    fcf_row = _find_line_item(cashflow_records, ["Free Cash Flow"])
    fcf_series = _quarterly_series(fcf_row)
    fcf_margin_series = [
        round(fcf / rev * 100, 2) if (fcf is not None and rev not in (None, 0)) else None
        for fcf, rev in zip(fcf_series, revenue_series)
    ] if fcf_series and revenue_series else []

    kp.financial_health = {
        "revenue_yoy_pct": _present(revenue_yoy) if revenue_yoy is not None else _missing(),
        "revenue_cagr_3y_pct": _present(revenue_cagr_3y) if revenue_cagr_3y is not None else _missing(),
        "revenue_cagr_5y_pct": _present(revenue_cagr_5y) if revenue_cagr_5y is not None else _missing(),
        "gross_margin_series_pct": _present(gross_margin_series) if gross_margin_series else _missing(),
        "operating_margin_series_pct": _present(op_margin_series) if op_margin_series else _missing(),
        "net_margin_series_pct": _present(net_margin_series) if net_margin_series else _missing(),
        "debt_to_equity": _present(debt_to_equity) if debt_to_equity is not None else _missing(),
        "current_ratio": _present(current_ratio) if current_ratio is not None else _missing(),
        "cash_position_latest": _present(cash_series[0]) if cash_series and cash_series[0] is not None else _missing(),
        "fcf_margin_series_pct": _present(fcf_margin_series) if fcf_margin_series else _missing(),
    }

    # --- 3. Posisi Kompetitif (deskriptif, bukan predikat) ---
    business_model = _classify_business_model(full_info.get("sector"), full_info.get("industry"))
    kp.competitive_position = {
        "business_model_category": (
            {"value": business_model, "status": "ok", "method": "heuristic_keyword_based"}
            if business_model else _missing()
        ),
        "revenue_share_of_peer_group_pct": _missing(),  # dihitung di Peer/Relative Comparison, bukan di sini
    }

    # --- 4. Tren Historis ---
    def _price_return(days: int) -> Optional[float]:
        if len(price_hist) <= days:
            return None
        closes = [r.get("Close") for r in price_hist if r.get("Close") is not None]
        if len(closes) <= days:
            return None
        return round((closes[-1] / closes[-days - 1] - 1) * 100, 3)

    import statistics as _stats
    closes = [r.get("Close") for r in price_hist if r.get("Close") is not None]
    daily_returns = [
        (closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1]
    ] if len(closes) > 1 else []
    volatility_daily = round(_stats.pstdev(daily_returns) * 100, 4) if len(daily_returns) > 1 else None

    kp.historical_trends = {
        "price_return_1y_pct": _present(_price_return(252)) if _price_return(252) is not None else _missing(),
        "price_return_3y_pct": _present(_price_return(756)) if _price_return(756) is not None else _missing(),
        "price_return_5y_pct": _present(_price_return(1260)) if _price_return(1260) is not None else _missing(),
        "price_volatility_daily_pct": _present(volatility_daily) if volatility_daily is not None else _missing(),
        "beta": _present(market_stats.get("beta") or full_info.get("beta")) if (market_stats.get("beta") or full_info.get("beta")) else _missing(),
    }

    # --- Insider transactions: normalisasi baris mentah yfinance jadi bentuk
    # faktual (tanggal, arah, jumlah) -- BUKAN interpretasi arah ("kurang
    # percaya diri" dst, itu wewenang modul reasoning, bukan Knowledge).
    def _clean_num(v):
        """NaN bukan JSON valid -- convert ke None secara eksplisit."""
        try:
            if v is None:
                return None
            fv = float(v)
            return None if fv != fv else fv  # fv != fv adalah cara cek NaN tanpa import math
        except (TypeError, ValueError):
            return v

    def _normalize_insider_txn(row: dict) -> dict:
        # Nama kolom 'Transaction' di data yfinance sering kosong/tidak
        # konsisten kualitasnya -- fallback ke 'Text' (deskripsi transaksi
        # mentah) kalau 'Transaction' kosong, baru None kalau dua-duanya kosong.
        txn_type = row.get("Transaction") or row.get("Text") or None
        if isinstance(txn_type, str) and not txn_type.strip():
            txn_type = None
        return {
            "date": row.get("Start Date") or row.get("Date"),
            "insider_name": row.get("Insider"),
            "position": row.get("Position"),
            "transaction_type": txn_type,
            "shares": _clean_num(row.get("Shares")),
            "value_usd": _clean_num(row.get("Value")),
        }

    recent_insider_transactions = [_normalize_insider_txn(r) for r in insider_txns_raw[:15]] if insider_txns_raw else []

    # --- 5. Kepemilikan ---
    inst_pct = full_info.get("heldPercentInstitutions")
    insider_pct = full_info.get("heldPercentInsiders")
    kp.ownership = {
        "institutional_ownership_pct": _present(round(inst_pct * 100, 2)) if inst_pct is not None else _missing(),
        "insider_ownership_pct": _present(round(insider_pct * 100, 2)) if insider_pct is not None else _missing(),
        "institutional_ownership_detail": _present(inst_own) if inst_own else _missing(),
        "recent_insider_transactions": (
            _present(recent_insider_transactions) if recent_insider_transactions else _missing()
        ),
    }

    # --- Metadata ---
    expected_fields = (
        list(kp.identity.keys()) + list(kp.financial_health.keys())
        + list(kp.competitive_position.keys()) + list(kp.historical_trends.keys())
        + list(kp.ownership.keys())
    )
    all_field_dicts = (
        list(kp.identity.values()) + list(kp.financial_health.values())
        + list(kp.competitive_position.values()) + list(kp.historical_trends.values())
        + list(kp.ownership.values())
    )
    filled = sum(1 for d in all_field_dicts if isinstance(d, dict) and d.get("status") == "ok")

    sources_used = sorted({v.get("source") for v in ev.fields.values() if v.get("value") is not None})

    kp.metadata = {
        "evidence_snapshot_date": ev.snapshot_date,
        "fields_expected": len(expected_fields),
        "fields_filled": filled,
        "completeness_ratio": round(filled / len(expected_fields), 3) if expected_fields else 0.0,
        "sources_used": sources_used,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }

    return kp
