"""
Confidence / Data Quality Score — 03_LAYER2_SPECS/05_CONFIDENCE_DATA_QUALITY.md
Dihitung dari kelengkapan (completeness_ratio di Knowledge.metadata) + jumlah
sumber yang saling menguatkan + kebaruan data (evidence_snapshot_date) +
soft flags dari Screening yang menurunkan keyakinan default (mis. micro_cap,
recent_ipo, no_institutional_data).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

CONFIDENCE_REDUCING_FLAGS = {
    "micro_cap": 0.10,
    "recent_ipo": 0.10,
    "adr": 0.05,
    "low_liquidity": 0.05,
    "no_institutional_data": 0.05,
}

# Data fundamental yang lebih tua dari 1 kuartal penuh (~95 hari) dianggap
# mulai basi -- lihat 03_LAYER2_SPECS/05_CONFIDENCE_DATA_QUALITY.md komponen #2.
STALE_AFTER_DAYS = 95
VERY_STALE_AFTER_DAYS = 190  # 2 kuartal -- penalti lebih besar


def _recency_penalty(evidence_snapshot_date: Optional[str]) -> tuple[float, Optional[int]]:
    """Kembalikan (penalty, age_days). penalty 0.0 kalau data masih segar atau
    tanggalnya tidak bisa diparse (fail-open: tidak menghukum data yang
    tanggalnya tidak diketahui, tapi age_days None supaya terlihat eksplisit)."""
    if not evidence_snapshot_date:
        return 0.0, None
    try:
        snap = datetime.fromisoformat(str(evidence_snapshot_date).replace("Z", "+00:00"))
        if snap.tzinfo is None:
            snap = snap.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - snap).days
    except (ValueError, TypeError):
        return 0.0, None

    if age_days >= VERY_STALE_AFTER_DAYS:
        return 0.15, age_days
    if age_days >= STALE_AFTER_DAYS:
        return 0.07, age_days
    return 0.0, age_days


def compute_confidence(knowledge_metadata: dict, screening_soft_flags: list[str] | None = None) -> dict:
    screening_soft_flags = screening_soft_flags or []
    completeness = knowledge_metadata.get("completeness_ratio", 0.0)
    n_sources = len(knowledge_metadata.get("sources_used", []))

    source_bonus = min(n_sources * 0.05, 0.15)
    base_score = min(completeness + source_bonus, 1.0)

    flag_penalty = sum(CONFIDENCE_REDUCING_FLAGS.get(f, 0.0) for f in screening_soft_flags)
    recency_penalty, age_days = _recency_penalty(knowledge_metadata.get("evidence_snapshot_date"))

    total_penalty = flag_penalty + recency_penalty
    score = max(round(base_score - total_penalty, 3), 0.0)

    if score >= 0.75:
        label = "high"
    elif score >= 0.45:
        label = "medium"
    else:
        label = "low"

    return {
        "score": score,
        "label": label,
        "completeness_ratio": completeness,
        "sources_count": n_sources,
        "evidence_age_days": age_days,
        "penalty_from_flags": round(flag_penalty, 3),
        "penalty_from_recency": round(recency_penalty, 3),
        "flags_applied": [f for f in screening_soft_flags if f in CONFIDENCE_REDUCING_FLAGS],
    }
