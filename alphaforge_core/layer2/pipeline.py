"""
Orkestrator Layer 2 end-to-end untuk SATU ticker:

Screening -> Evidence -> Knowledge -> Confidence + Peer Comparison ->
Risk/Red-Flag Check -> [Multibagger, Quality/Compound, Speculative] -> Aggregator

Sesuai diagram di 01_ARCHITECTURE/03_LAYER2_STOCK_ANALYSIS.md bagian 3.
Historical Tracking / Decision Journal (tahap terakhir) sengaja belum
diimplementasikan di sini -- itu diakui eksplisit sebagai kandidat v2.1 di
03_LAYER2_SPECS/12_HISTORICAL_TRACKING_JOURNAL.md.
"""
from __future__ import annotations

from typing import Iterable, Optional

from . import aggregator, catalyst_tracking, confidence as confidence_mod
from . import evidence as evidence_mod
from . import knowledge as knowledge_mod
from . import peer_comparison, risk_redflag, screening
from .knowledge import KnowledgeProfile
from .modules import multibagger, quality_compound, speculative


def analyze_single_ticker(
    ticker: str,
    market_context: dict,
    security_type: str = "common_stock",
    is_test_issue: bool = False,
    is_adr: bool = False,
    peer_tickers: Optional[Iterable[str]] = None,
) -> dict:
    """Jalankan pipeline penuh untuk satu ticker dan kembalikan output Aggregator.

    market_context: hasil `layer1.market_context_engine.build_market_context_package()`,
        dihitung SEKALI di luar fungsi ini lalu dipakai ulang untuk semua ticker
        dalam sesi yang sama (lihat 01_ARCHITECTURE/02_LAYER1_MARKET_CONTEXT.md #4).
    peer_tickers: opsional, ticker peer/kompetitor untuk Peer/Relative Comparison.
        Kalau tidak disuplai, perbandingan peer di-skip secara eksplisit.
    """
    # 1. Screening
    screen_result = screening.screen_ticker(
        ticker, security_type=security_type, is_test_issue=is_test_issue, is_adr=is_adr
    )
    if not screen_result.passed:
        return {
            "ticker": ticker,
            "stage_stopped_at": "screening",
            "hard_exclude_reasons": screen_result.hard_exclude_reasons,
            "note": "Ticker tidak lolos Hard Exclude di Screening -- tidak diteruskan ke Evidence.",
        }

    # 2. Evidence
    ev = evidence_mod.collect_evidence(ticker)

    # 3. Knowledge
    kp = knowledge_mod.build_knowledge(ev, screening_soft_flags=screen_result.soft_flags)
    kp_dict = kp.to_dict()

    # 4. Confidence + Peer Comparison
    conf = confidence_mod.compute_confidence(kp.metadata, screening_soft_flags=screen_result.soft_flags)

    peer_profiles: list[KnowledgeProfile] = []
    peer_failures: list[dict] = []
    if peer_tickers:
        for peer_ticker in peer_tickers:
            try:
                peer_screen = screening.screen_ticker(peer_ticker)
                if not peer_screen.passed:
                    peer_failures.append({
                        "ticker": peer_ticker,
                        "reason": "failed_screening",
                        "detail": peer_screen.hard_exclude_reasons,
                    })
                    continue
                peer_ev = evidence_mod.collect_evidence(peer_ticker)
                peer_kp = knowledge_mod.build_knowledge(peer_ev, screening_soft_flags=peer_screen.soft_flags)
                peer_profiles.append(peer_kp)
            except Exception as exc:  # noqa: BLE001 - satu peer gagal tidak boleh menggagalkan seluruh analisa
                peer_failures.append({"ticker": peer_ticker, "reason": "exception", "detail": str(exc)})
                continue
    peer_result = peer_comparison.compare_to_peers(kp, peer_profiles)
    if peer_failures:
        peer_result["peer_failures"] = peer_failures

    # 5. Risk / Red-Flag Check
    risk_result = risk_redflag.run_risk_check(ev, kp)

    # 6. Catalyst Tracking (dipakai Speculative Module)
    catalysts = catalyst_tracking.identify_catalysts(ticker, ev)

    # 7. Tiga modul reasoning independen
    mb_result = multibagger.analyze(kp_dict, market_context, risk_result, conf)
    qc_result = quality_compound.analyze(kp_dict, market_context, risk_result, conf, peer_result)
    sp_result = speculative.analyze(kp_dict, market_context, risk_result, conf, catalysts)

    # 8. Aggregator
    mc_summary = {
        name: comp.get("value")
        for name, comp in market_context.get("components", {}).items()
    }
    output = aggregator.aggregate(
        ticker=ticker,
        knowledge=kp_dict,
        confidence=conf,
        risk_flags=risk_result,
        multibagger_result=mb_result,
        quality_compound_result=qc_result,
        speculative_result=sp_result,
        market_context_summary=mc_summary,
    )
    output["screening_soft_flags"] = screen_result.soft_flags
    output["peer_comparison"] = peer_result
    output["knowledge_full"] = kp_dict
    output["evidence_field_status"] = {
        name: {"source": f.get("source"), "error": f.get("error")} for name, f in ev.fields.items()
    }
    return output
