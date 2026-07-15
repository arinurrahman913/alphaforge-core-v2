"""
Module — Speculative — 03_LAYER2_SPECS/09_MODULE_SPECULATIVE.md
Fokus: katalis konkret + waktunya, upside vs downside, risk appetite market
(VIX & Market Sentiment). Dilengkapi Catalyst Tracking.
"""
from __future__ import annotations

MODULE_NAME = "speculative"


def _val(d: dict, section: str, field: str):
    v = d.get(section, {}).get(field)
    if isinstance(v, dict) and v.get("status") == "ok":
        return v.get("value")
    return None


def analyze(knowledge: dict, market_context: dict, risk_flags: dict,
            confidence: dict, catalysts: list[dict] | None = None) -> dict:
    reasons = []
    score = 0
    max_score = 0
    catalysts = catalysts or []

    max_score += 3
    if catalysts:
        score += min(len(catalysts), 3)
        reasons.append(f"{len(catalysts)} katalis teridentifikasi (earnings/berita relevan) -- lihat Catalyst Tracking untuk detail tanggal.")
        for c in catalysts[:3]:
            label = c.get("type")
            date_ = c.get("estimated_date") or "tanggal belum pasti"
            reasons.append(f"  - {label}: {date_}")
    else:
        reasons.append("Tidak ada katalis konkret yang teridentifikasi saat ini -- tesis spekulatif tanpa katalis jelas kurang actionable.")

    volatility_daily = _val(knowledge, "historical_trends", "price_volatility_daily_pct")
    max_score += 2
    if volatility_daily is not None:
        if volatility_daily >= 3:
            score += 2
            reasons.append(f"Volatilitas harian historis tinggi ({volatility_daily}%) -- konsisten dengan profil risk/reward asimetris.")
        elif volatility_daily >= 1.5:
            score += 1
            reasons.append(f"Volatilitas harian historis moderat ({volatility_daily}%).")
    else:
        reasons.append("Data volatilitas harian tidak tersedia.")

    size_tier = _val(knowledge, "identity", "size_tier")
    max_score += 1
    if size_tier in ("micro_cap", "small_cap"):
        score += 1
        reasons.append(f"Ukuran perusahaan ({size_tier}) konsisten dengan profil spekulatif (volatilitas & sensitivitas katalis lebih tinggi).")

    # Konteks Layer 1: VIX & Market Sentiment (paling relevan untuk risk appetite)
    vix = market_context.get("components", {}).get("volatility_index", {}).get("value")
    sentiment = market_context.get("components", {}).get("market_sentiment", {}).get("value")

    max_score += 2
    risk_appetite_favorable = False
    if vix == "low_risk_on":
        score += 1
        risk_appetite_favorable = True
        reasons.append("VIX rendah (risk-on) -- kondisi market saat ini relatif mendukung selera risiko untuk taruhan spekulatif.")
    elif vix == "high_risk_off":
        reasons.append("VIX tinggi (risk-off) -- kondisi market saat ini cenderung menekan selera risiko untuk taruhan spekulatif.")
    if sentiment == "fear":
        reasons.append("Market Sentiment saat ini 'fear' -- bisa jadi sinyal kontrarian, tapi juga menandakan risk appetite rendah secara umum.")
    elif sentiment == "greed":
        score += 1
        risk_appetite_favorable = True
        reasons.append("Market Sentiment saat ini 'greed' -- risk appetite umum sedang tinggi.")

    risk_note = None
    if risk_flags.get("overall_risk_level") in ("moderate", "elevated"):
        risk_note = (f"Risk/Red-Flag Check menandai level '{risk_flags.get('overall_risk_level')}' -- "
                     "untuk tesis spekulatif ini relevan sebagai bagian dari downside risk, bukan otomatis diskualifikasi.")

    pct = round(score / max_score * 100, 1) if max_score else None
    if pct is not None and pct >= 60 and catalysts:
        signal = "actionable_speculative_setup"
    elif pct is not None and pct >= 30:
        signal = "watch"
    else:
        signal = "not_supported_by_current_evidence"

    return {
        "module": MODULE_NAME,
        "signal": signal,
        "internal_score_pct": pct,
        "reasoning": reasons,
        "risk_note": risk_note,
        "confidence": confidence,
        "catalysts": catalysts,
    }
