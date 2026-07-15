"""
Module — Quality/Compound — 03_LAYER2_SPECS/08_MODULE_QUALITY_COMPOUND.md
Fokus: moat, konsistensi ROE/margin, kualitas balance sheet, alokasi modal.
Konteks paling relevan: Yield Curve & Liquidity Conditions + Peer Comparison.
"""
from __future__ import annotations

MODULE_NAME = "quality_compound"


def _val(d: dict, section: str, field: str):
    v = d.get(section, {}).get(field)
    if isinstance(v, dict) and v.get("status") == "ok":
        return v.get("value")
    return None


def _series_consistency(series) -> str:
    if not series or len(series) < 4:
        return "insufficient_data"
    valid = [v for v in series if v is not None]
    if len(valid) < 4:
        return "insufficient_data"
    diffs = [valid[i] - valid[i + 1] for i in range(len(valid) - 1)]
    declining_count = sum(1 for d in diffs if d < -1)
    if declining_count >= len(diffs) * 0.5:
        return "declining"
    improving_count = sum(1 for d in diffs if d > 1)
    if improving_count >= len(diffs) * 0.5:
        return "improving"
    return "stable"


def analyze(knowledge: dict, market_context: dict, risk_flags: dict,
            confidence: dict, peer_comparison: dict | None = None) -> dict:
    reasons = []
    score = 0
    max_score = 0

    gross_margin_series = _val(knowledge, "financial_health", "gross_margin_series_pct") or []
    net_margin_series = _val(knowledge, "financial_health", "net_margin_series_pct") or []
    debt_to_equity = _val(knowledge, "financial_health", "debt_to_equity")
    current_ratio = _val(knowledge, "financial_health", "current_ratio")
    fcf_margin_series = _val(knowledge, "financial_health", "fcf_margin_series_pct") or []

    max_score += 3
    margin_trend = _series_consistency(net_margin_series)
    if margin_trend == "stable":
        score += 2
        reasons.append("Net margin kuartalan relatif stabil sepanjang histori yang tersedia.")
    elif margin_trend == "improving":
        score += 3
        reasons.append("Net margin kuartalan menunjukkan tren membaik.")
    elif margin_trend == "declining":
        reasons.append("Net margin kuartalan menunjukkan tren menurun -- kurang mendukung tesis compounder konsisten.")
    else:
        reasons.append("Data net margin historis tidak cukup untuk menilai konsistensi.")

    max_score += 2
    if debt_to_equity is not None:
        if debt_to_equity <= 1.0:
            score += 2
            reasons.append(f"Debt-to-equity rendah ({debt_to_equity}) -- struktur balance sheet konservatif.")
        elif debt_to_equity <= 2.0:
            score += 1
            reasons.append(f"Debt-to-equity moderat ({debt_to_equity}).")
        else:
            reasons.append(f"Debt-to-equity tinggi ({debt_to_equity}) -- perlu diperiksa lebih lanjut untuk tesis kualitas.")
    else:
        reasons.append("Debt-to-equity tidak tersedia.")

    max_score += 2
    if current_ratio is not None:
        if current_ratio >= 1.5:
            score += 2
            reasons.append(f"Current ratio sehat ({current_ratio}).")
        elif current_ratio >= 1.0:
            score += 1
            reasons.append(f"Current ratio memadai ({current_ratio}).")
        else:
            reasons.append(f"Current ratio di bawah 1.0 ({current_ratio}) -- likuiditas jangka pendek perlu diperhatikan.")
    else:
        reasons.append("Current ratio tidak tersedia.")

    max_score += 2
    fcf_trend = _series_consistency(fcf_margin_series)
    if fcf_trend in ("stable", "improving"):
        score += 2
        reasons.append(f"FCF margin menunjukkan tren {fcf_trend}.")
    elif fcf_trend == "declining":
        reasons.append("FCF margin menunjukkan tren menurun.")
    else:
        reasons.append("Data FCF margin historis tidak cukup untuk dinilai.")

    # Peer comparison
    if peer_comparison and peer_comparison.get("peer_group_size", 0) > 0:
        de_metric = peer_comparison.get("metrics", {}).get("financial_health.debt_to_equity", {})
        percentile = de_metric.get("target_percentile_within_peers")
        if percentile is not None:
            reasons.append(f"Debt-to-equity berada di persentil {percentile} dibanding {peer_comparison['peer_group_size']} peer (semakin rendah semakin baik untuk metrik ini).")
    else:
        reasons.append("Peer/Relative Comparison belum tersedia untuk sesi ini -- penilaian relatif terhadap industri tidak dilakukan.")

    # Konteks Layer 1
    yield_curve = market_context.get("components", {}).get("yield_curve", {}).get("value")
    liquidity = market_context.get("components", {}).get("liquidity_conditions", {}).get("value")
    if yield_curve:
        reasons.append(f"Konteks Yield Curve saat ini: {yield_curve} -- memengaruhi biaya modal & valuasi relatif compounder.")
    if liquidity:
        reasons.append(f"Konteks Liquidity Conditions saat ini: {liquidity}.")

    risk_note = None
    if risk_flags.get("overall_risk_level") in ("moderate", "elevated"):
        risk_note = f"Risk/Red-Flag Check menandai level '{risk_flags.get('overall_risk_level')}' -- pertimbangkan sebelum menilai kualitas jangka panjang."

    pct = round(score / max_score * 100, 1) if max_score else None
    if pct is not None and pct >= 65:
        signal = "strong_quality_candidate"
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
