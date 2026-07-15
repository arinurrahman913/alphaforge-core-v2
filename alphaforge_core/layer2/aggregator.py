"""
Aggregator & Output — 03_LAYER2_SPECS/11_AGGREGATOR_OUTPUT.md

Menyusun ketiga hasil modul reasoning berdampingan. TIDAK menggabungkan jadi
satu skor/verdict (Prinsip #3). Confidence & Risk flag disertakan eksplisit.
"""
from __future__ import annotations

from datetime import datetime, timezone


def aggregate(ticker: str, knowledge: dict, confidence: dict, risk_flags: dict,
              multibagger_result: dict, quality_compound_result: dict,
              speculative_result: dict, market_context_summary: dict) -> dict:
    return {
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "confidence": confidence,
        "risk_redflag": risk_flags,
        "market_context_summary": market_context_summary,
        "views": {
            # Sengaja disebut "views", bukan "scores" -- tiga sudut pandang
            # berdampingan, investor yang memilih lensa mana yang relevan.
            "multibagger": multibagger_result,
            "quality_compound": quality_compound_result,
            "speculative": speculative_result,
        },
        "identity": knowledge.get("identity", {}),
        "disclaimer": (
            "Output ini adalah bahan pertimbangan terstruktur, bukan sinyal beli/jual "
            "otomatis. AlphaForge tidak meramal masa depan (Prinsip #10, "
            "00_Foundation/02_PRINCIPLES.md). Keputusan akhir ada di tangan investor."
        ),
    }
