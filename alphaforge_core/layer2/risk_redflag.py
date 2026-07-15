"""
Risk / Red-Flag Check — 03_LAYER2_SPECS/04_RISK_REDFLAG_CHECK.md

Gerbang deteksi pola bermasalah (bukan skor yang dirata-rata). Hasilnya
menempel sebagai flag eksplisit yang WAJIB dilihat ketiga modul reasoning --
tidak menghentikan proses secara default, kecuali kasus yang sudah
terkonfirmasi sangat berat (fraud terbukti / delisting resmi -- deteksi
otomatis untuk itu di luar cakupan v2.0 awal ini, ditandai sebagai TODO).
"""
from __future__ import annotations

from .evidence import Evidence
from .knowledge import KnowledgeProfile

RESTATEMENT_KEYWORDS = ["restatement", "restate", "material weakness", "non-reliance"]
AUDITOR_CHANGE_KEYWORDS = ["dismissed", "auditor resign", "change in accountant", "changed its auditor"]
LITIGATION_KEYWORDS = ["lawsuit", "class action", "sec investigation", "subpoena", "fraud"]


def _news_headlines(ev: Evidence) -> list[str]:
    news = ev.fields.get("news", {}).get("value") or []
    return [str(n.get("headline", "")) for n in news if isinstance(n, dict)]


def _filing_titles(ev: Evidence) -> list[str]:
    filings = ev.fields.get("sec_filings", {}).get("value") or []
    return [str(f.get("form", "")) + " " + str(f.get("description", "")) for f in filings if isinstance(f, dict)]


def _keyword_hits(texts: list[str], keywords: list[str]) -> list[str]:
    hits = []
    for text in texts:
        low = text.lower()
        for kw in keywords:
            if kw in low:
                hits.append(text)
                break
    return hits


def run_risk_check(ev: Evidence, kp: KnowledgeProfile) -> dict:
    headlines = _news_headlines(ev)
    filing_titles = _filing_titles(ev)
    all_texts = headlines + filing_titles

    flags = []

    restatement_hits = _keyword_hits(all_texts, RESTATEMENT_KEYWORDS)
    if restatement_hits:
        flags.append({"type": "possible_restatement_or_material_weakness", "severity": "high", "evidence": restatement_hits[:5]})

    auditor_hits = _keyword_hits(all_texts, AUDITOR_CHANGE_KEYWORDS)
    if auditor_hits:
        flags.append({"type": "possible_auditor_change", "severity": "medium", "evidence": auditor_hits[:5]})

    litigation_hits = _keyword_hits(all_texts, LITIGATION_KEYWORDS)
    if litigation_hits:
        flags.append({"type": "possible_litigation_or_investigation", "severity": "medium", "evidence": litigation_hits[:5]})

    debt_to_equity = kp.financial_health.get("debt_to_equity", {}).get("value")
    if isinstance(debt_to_equity, (int, float)) and debt_to_equity > 3:
        flags.append({
            "type": "high_leverage",
            "severity": "medium",
            "evidence": [f"debt_to_equity={debt_to_equity}"],
        })

    current_ratio = kp.financial_health.get("current_ratio", {}).get("value")
    if isinstance(current_ratio, (int, float)) and current_ratio < 1.0:
        flags.append({
            "type": "weak_short_term_liquidity",
            "severity": "medium",
            "evidence": [f"current_ratio={current_ratio}"],
        })

    severities = [f["severity"] for f in flags]
    if "high" in severities:
        overall = "elevated"
    elif "medium" in severities:
        overall = "moderate"
    else:
        overall = "none_detected"

    return {
        "overall_risk_level": overall,
        "flags": flags,
        "confirmed_severe_stop": False,  # TODO v2.1: deteksi fraud terbukti/delisting resmi utk hentikan proses
        "note": "Flag menempel & wajib direspons ketiga modul reasoning (Prinsip #4) -- bukan otomatis menghentikan proses.",
    }
