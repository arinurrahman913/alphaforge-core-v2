"""
Tes logika murni Historical Tracking / Decision Journal — TIDAK memanggil
network sama sekali. Jurnal dipakai dengan DB in-memory dan price-lookup
disuntikkan, supaya jalan tanpa API key / koneksi internet.

Memvalidasi kontrak inti spec 03_LAYER2_SPECS/12_HISTORICAL_TRACKING_JOURNAL.md
dan Prinsip #6 (versi metodologi tersimpan & terdeteksi saat audit):
- record menyimpan snapshot lengkap termasuk versi metodologi
- list mengembalikan entri tersimpan
- evaluate menghitung return terealisasi dari price-lookup yang disuntikkan
- keselarasan modul deskriptif (aligned/misaligned/inconclusive), bukan vonis
- harga hilang -> 'missing', bukan ditebak 0
- versi metodologi berbeda -> ditandai mismatch eksplisit
- Output yang berhenti di tahap awal ditolak untuk direkam
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alphaforge_core import config
from alphaforge_core.layer2.journal import DecisionJournal


def _synthetic_output(ticker="TEST", mb="strong_growth_candidate",
                      qc="not_supported_by_current_evidence", sp="watch",
                      generated_at="2026-01-01T00:00:00+00:00",
                      methodology_version=None) -> dict:
    return {
        "ticker": ticker,
        "generated_at": generated_at,
        "methodology_version": methodology_version or config.METHODOLOGY_VERSION,
        "confidence": {"score": 72.5, "label": "medium"},
        "risk_redflag": {"overall_risk_level": "moderate"},
        "views": {
            "multibagger": {"module": "multibagger", "signal": mb, "internal_score_pct": 80},
            "quality_compound": {"module": "quality_compound", "signal": qc, "internal_score_pct": 20},
            "speculative": {"module": "speculative", "signal": sp, "internal_score_pct": 50},
        },
    }


def _fresh_journal() -> DecisionJournal:
    return DecisionJournal(db_path=":memory:")


def test_record_and_list():
    j = _fresh_journal()
    eid = j.record(_synthetic_output("AAPL"), price_at_analysis=100.0)
    assert isinstance(eid, int) and eid > 0
    entries = j.list_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e["ticker"] == "AAPL"
    assert e["price_at_analysis"] == 100.0
    assert e["signal_multibagger"] == "strong_growth_candidate"
    # full_output disimpan utuh untuk audit
    assert e["full_output"]["views"]["speculative"]["signal"] == "watch"
    print("OK: record menyimpan snapshot lengkap, list mengembalikannya")


def test_methodology_version_is_stored():
    j = _fresh_journal()
    j.record(_synthetic_output("MSFT", methodology_version="9.9.9"), price_at_analysis=50.0)
    e = j.list_entries(ticker="MSFT")[0]
    assert e["methodology_version"] == "9.9.9", "versi metodologi harus tersimpan apa adanya (Prinsip #6)"
    print("OK: versi metodologi tersimpan di entri (Prinsip #6)")


def test_list_filter_by_ticker():
    j = _fresh_journal()
    j.record(_synthetic_output("AAPL"), price_at_analysis=100.0)
    j.record(_synthetic_output("NVDA"), price_at_analysis=200.0)
    assert len(j.list_entries()) == 2
    only_nvda = j.list_entries(ticker="nvda")  # case-insensitive
    assert len(only_nvda) == 1 and only_nvda[0]["ticker"] == "NVDA"
    print("OK: list bisa difilter per ticker (case-insensitive)")


def test_evaluate_realized_return_and_alignment():
    j = _fresh_journal()
    # MB constructive, QC not_constructive. Harga naik 30% -> MB aligned, QC misaligned.
    eid = j.record(_synthetic_output("AAPL", mb="strong_growth_candidate",
                                     qc="not_supported_by_current_evidence", sp="watch"),
                   price_at_analysis=100.0)
    ev = j.evaluate_entry(eid, current_price=130.0, as_of="2026-06-01T00:00:00+00:00")
    assert ev["realized_return_pct"] == 30.0
    assert ev["realized_direction"] == "up"
    assert ev["module_alignment"]["multibagger"] == "aligned"          # constructive + up
    assert ev["module_alignment"]["quality_compound"] == "misaligned"  # not_constructive + up
    assert ev["module_alignment"]["speculative"] == "inconclusive"     # neutral stance
    assert ev["holding_days"] is not None and ev["holding_days"] > 100
    print("OK: evaluate menghitung return terealisasi + keselarasan modul deskriptif")


def test_flat_move_is_inconclusive():
    j = _fresh_journal()
    eid = j.record(_synthetic_output("AAPL", mb="strong_growth_candidate"), price_at_analysis=100.0)
    # Gerak +2% ada di dalam flat band (default 5%) -> flat -> inconclusive
    ev = j.evaluate_entry(eid, current_price=102.0)
    assert ev["realized_direction"] == "flat"
    assert ev["module_alignment"]["multibagger"] == "inconclusive"
    print("OK: gerak harga di dalam flat-band -> inconclusive, bukan dipaksa aligned/misaligned")


def test_missing_price_is_explicit_not_guessed():
    j = _fresh_journal()
    # Tanpa price_at_analysis
    eid = j.record(_synthetic_output("AAPL"), price_at_analysis=None)
    ev = j.evaluate_entry(eid, current_price=130.0)
    assert ev["realized_return_pct"] is None
    assert ev["realized_direction"] == "missing"
    assert any("missing" in n.lower() for n in ev["notes"])
    # dan sebaliknya: ada harga awal tapi lookup terkini gagal (None)
    eid2 = j.record(_synthetic_output("MSFT"), price_at_analysis=50.0)
    ev2 = j.evaluate_entry(eid2, current_price=None)
    assert ev2["realized_return_pct"] is None and ev2["realized_direction"] == "missing"
    print("OK: harga hilang ditandai 'missing' eksplisit, tidak ditebak 0")


def test_methodology_version_mismatch_flagged():
    j = _fresh_journal()
    eid = j.record(_synthetic_output("AAPL", methodology_version="0.0.1-old"), price_at_analysis=100.0)
    ev = j.evaluate_entry(eid, current_price=110.0)
    assert ev["methodology_version_mismatch"] is True
    assert ev["methodology_version_at_analysis"] == "0.0.1-old"
    assert ev["methodology_version_now"] == config.METHODOLOGY_VERSION
    assert any("versi metodologi" in n.lower() for n in ev["notes"])
    print("OK: versi metodologi berbeda ditandai mismatch eksplisit (audit bias, Prinsip #6)")


def test_evaluate_all_with_injected_lookup_and_min_days():
    j = _fresh_journal()
    from datetime import datetime, timezone, timedelta
    # entri lama (200 hari lalu) dan entri baru (hari ini)
    old_at = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    new_at = datetime.now(timezone.utc).isoformat()
    j.record(_synthetic_output("OLD", generated_at=old_at), price_at_analysis=100.0)
    j.record(_synthetic_output("NEW", generated_at=new_at), price_at_analysis=100.0)

    prices = {"OLD": 150.0, "NEW": 150.0}
    results = j.evaluate_all(price_lookup=lambda t: prices.get(t), min_holding_days=90)
    tickers = {r["ticker"] for r in results}
    assert "OLD" in tickers, "entri lama harus lolos min_holding_days"
    assert "NEW" not in tickers, "entri baru (< 90 hari) harus dilewati"
    print("OK: evaluate_all pakai price-lookup suntikan & menghormati --min-days")


def test_record_rejects_stage_stopped_output():
    j = _fresh_journal()
    stopped = {"ticker": "SHELL", "stage_stopped_at": "screening",
               "hard_exclude_reasons": ["market_cap_below_min"]}
    try:
        j.record(stopped, price_at_analysis=1.0)
        assert False, "seharusnya menolak Output yang berhenti di tahap awal"
    except ValueError:
        pass
    print("OK: Output yang berhenti di Screening/red-flag ekstrem ditolak untuk direkam")


def run_all():
    test_record_and_list()
    test_methodology_version_is_stored()
    test_list_filter_by_ticker()
    test_evaluate_realized_return_and_alignment()
    test_flat_move_is_inconclusive()
    test_missing_price_is_explicit_not_guessed()
    test_methodology_version_mismatch_flagged()
    test_evaluate_all_with_injected_lookup_and_min_days()
    test_record_rejects_stage_stopped_output()
    print("\nALL JOURNAL LOGIC TESTS PASSED")


if __name__ == "__main__":
    run_all()
