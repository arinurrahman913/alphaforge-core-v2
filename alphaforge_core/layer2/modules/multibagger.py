"""
Module — Multibagger — 03_LAYER2_SPECS/07_MODULE_MULTIBAGGER.md
Fokus: potensi pertumbuhan eksplosif jangka panjang. Konteks paling relevan:
Sector Rotation & Business Cycle Stage (01_ARCHITECTURE/02_LAYER1_MARKET_CONTEXT.md).

Catatan: kriteria/bobot berikut adalah interpretasi implementasi awal (spec
menyatakan "detail kriteria & bobot didiskusikan terpisah sebelum implementasi")
-- disusun eksplisit & bisa dikalibrasi ulang, bukan angka final yang dianggap benar.
"""
from __future__ import annotations

MODULE_NAME = "multibagger"


def _val(d: dict, section: str, field: str):
    v = d.get(section, {}).get(field)
    if isinstance(v, dict) and v.get("status") == "ok":
        return v.get("value")
    return None


def analyze(knowledge: dict, market_context: dict, risk_flags: dict,
            confidence: dict) -> dict:
    reasons = []
    score = 0
    max_score = 0

    revenue_cagr_3y = _val(knowledge, "financial_health", "revenue_cagr_3y_pct")
    revenue_yoy = _val(knowledge, "financial_health", "revenue_yoy_pct")
    size_tier = _val(knowledge, "identity", "size_tier")
    sector = _val(knowledge, "identity", "sector")

    max_score += 3
    if revenue_cagr_3y is not None:
        if revenue_cagr_3y >= 25:
            score += 3
            reasons.append(f"Revenue CAGR 3 tahun tinggi ({revenue_cagr_3y}%) -- konsisten dengan profil pertumbuhan eksplosif.")
        elif revenue_cagr_3y >= 10:
            score += 1.5
            reasons.append(f"Revenue CAGR 3 tahun moderat ({revenue_cagr_3y}%).")
        else:
            reasons.append(f"Revenue CAGR 3 tahun rendah ({revenue_cagr_3y}%) -- kurang mendukung tesis multibagger klasik.")
    else:
        reasons.append("Revenue CAGR 3 tahun tidak tersedia (data historis mungkin terlalu pendek).")

    max_score += 2
    if revenue_yoy is not None:
        if revenue_yoy >= 30:
            score += 2
            reasons.append(f"Revenue YoY terbaru sangat tinggi ({revenue_yoy}%).")
        elif revenue_yoy >= 15:
            score += 1
            reasons.append(f"Revenue YoY terbaru solid ({revenue_yoy}%).")
    else:
        reasons.append("Revenue YoY terbaru tidak tersedia.")

    max_score += 2
    if size_tier in ("micro_cap", "small_cap"):
        score += 2
        reasons.append(f"Ukuran perusahaan ({size_tier}) memberi ruang ekspansi lebih besar secara relatif dibanding large/mega-cap.")
    elif size_tier:
        reasons.append(f"Ukuran perusahaan ({size_tier}) -- ruang ekspansi multibagger klasik secara relatif lebih terbatas.")

    # Konteks Layer 1: Sector Rotation & Business Cycle
    sector_rotation = market_context.get("components", {}).get("sector_rotation", {})
    inflow_sectors = (sector_rotation.get("value") or {}).get("inflow_sectors", [])
    business_cycle = market_context.get("components", {}).get("business_cycle_stage", {}).get("value")

    max_score += 2
    if sector and any(sector.lower() in s.lower() for s in inflow_sectors):
        score += 2
        reasons.append(f"Sektor '{sector}' saat ini termasuk yang mengalami inflow relatif (Sector Rotation Layer 1).")
    elif sector:
        reasons.append(f"Sektor '{sector}' saat ini tidak teridentifikasi sebagai salah satu sektor inflow utama.")

    if business_cycle:
        reasons.append(f"Konteks Business Cycle Stage saat ini: {business_cycle} (early/mid-cycle secara historis lebih mendukung growth stocks).")

    risk_note = None
    if risk_flags.get("overall_risk_level") in ("moderate", "elevated"):
        risk_note = f"Risk/Red-Flag Check menandai level '{risk_flags.get('overall_risk_level')}' -- lihat detail flag sebelum bertindak atas sinyal pertumbuhan di atas."

    pct = round(score / max_score * 100, 1) if max_score else None

    if pct is not None and pct >= 65:
        signal = "strong_growth_candidate"
    elif pct is not None and pct >= 35:
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
    }
