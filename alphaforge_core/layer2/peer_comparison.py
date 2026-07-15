"""
Peer / Relative Comparison — 03_LAYER2_SPECS/06_PEER_RELATIVE_COMPARISON.md
Beroperasi di atas Knowledge (bukan Evidence mentah). Butuh Knowledge dari
saham lain di sektor/industri yang sama sebagai pembanding.
"""
from __future__ import annotations

import statistics as stats
from typing import Iterable

from .knowledge import KnowledgeProfile

COMPARABLE_METRICS = [
    ("financial_health", "revenue_yoy_pct"),
    ("financial_health", "revenue_cagr_3y_pct"),
    ("financial_health", "debt_to_equity"),
    ("financial_health", "current_ratio"),
    ("historical_trends", "price_volatility_daily_pct"),
]

# Di bawah ambang ini, percentile/median dianggap kurang bermakna secara
# statistik -- ditandai eksplisit lewat "low_sample_size", bukan disembunyikan.
MIN_PEER_GROUP_SIZE = 3


def _extract(kp: KnowledgeProfile, section: str, field: str):
    d = getattr(kp, section).get(field)
    if isinstance(d, dict) and d.get("status") == "ok":
        val = d.get("value")
        return val if isinstance(val, (int, float)) else None
    return None


def compare_to_peers(target: KnowledgeProfile, peers: Iterable[KnowledgeProfile]) -> dict:
    """Bandingkan target terhadap median grup peer untuk metrik-metrik kunci.
    Kalau tidak ada peer yang disuplai, mengembalikan hasil kosong yang
    ditandai eksplisit -- BUKAN dianggap 'rata-rata industri'."""
    peers = list(peers)
    result = {"peer_group_size": len(peers), "metrics": {}}

    if not peers:
        result["note"] = "Tidak ada peer group yang disuplai -- perbandingan tidak dilakukan."
        return result

    if len(peers) < MIN_PEER_GROUP_SIZE:
        result["note"] = (
            f"Peer group hanya {len(peers)} saham (di bawah minimum {MIN_PEER_GROUP_SIZE}) -- "
            "median/percentile di bawah tetap dihitung tapi kurang bermakna secara statistik, "
            "perlakukan sebagai indikasi kasar saja."
        )
        result["low_sample_size"] = True
    else:
        result["low_sample_size"] = False

    for section, field in COMPARABLE_METRICS:
        target_val = _extract(target, section, field)
        peer_vals = [v for p in peers if (v := _extract(p, section, field)) is not None]
        if not peer_vals:
            result["metrics"][f"{section}.{field}"] = {"target": target_val, "peer_median": None, "percentile_note": "no_peer_data"}
            continue
        peer_median = round(stats.median(peer_vals), 4)
        rank_below = sum(1 for v in peer_vals if v < target_val) if target_val is not None else None
        percentile = round(rank_below / len(peer_vals) * 100, 1) if (target_val is not None and peer_vals) else None
        result["metrics"][f"{section}.{field}"] = {
            "target": target_val,
            "peer_median": peer_median,
            "peer_group_n": len(peer_vals),
            "target_percentile_within_peers": percentile,
        }
    return result
