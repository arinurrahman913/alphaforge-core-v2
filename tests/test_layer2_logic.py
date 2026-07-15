"""
Tes logika murni Layer 2 — TIDAK memanggil network sama sekali. Data
disuntikkan secara sintetis supaya bisa jalan tanpa API key / koneksi
internet (sandbox CI/dev tanpa akses ke Yahoo Finance/FRED/Finnhub).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alphaforge_core.layer2.evidence import Evidence, _field
from alphaforge_core.layer2.knowledge import build_knowledge
from alphaforge_core.layer2.confidence import compute_confidence
from alphaforge_core.layer2.risk_redflag import run_risk_check
from alphaforge_core.layer2.peer_comparison import compare_to_peers
from alphaforge_core.layer2.modules import multibagger, quality_compound, speculative


def _synthetic_evidence(ticker="TEST") -> Evidence:
    ev = Evidence(ticker=ticker)
    # Revenue kuartalan naik terus (buat CAGR positif jelas): quarter terbaru dulu
    revenue = [130, 125, 120, 110, 100, 95, 90, 85, 80, 78, 75, 70, 60, 55, 50, 45, 40, 38, 35, 32]
    gross_profit = [v * 0.6 for v in revenue]
    op_income = [v * 0.2 for v in revenue]
    net_income = [v * 0.15 for v in revenue]
    fcf = [v * 0.18 for v in revenue]

    def _row(name, values):
        row = {"index": name}
        for i, v in enumerate(values):
            row[f"col_{i}"] = v
        return row

    ev.fields["quarterly_financials"] = _field({
        "income_stmt": [
            _row("Total Revenue", revenue),
            _row("Gross Profit", gross_profit),
            _row("Operating Income", op_income),
            _row("Net Income", net_income),
        ],
        "balance_sheet": [
            _row("Total Debt", [200] * 20),
            _row("Common Stock Equity", [400] * 20),
            _row("Current Assets", [300] * 20),
            _row("Current Liabilities", [150] * 20),
            _row("Cash And Cash Equivalents", [100] * 20),
        ],
        "cashflow": [
            _row("Free Cash Flow", fcf),
        ],
    }, source="synthetic_test")

    ev.fields["market_stats"] = _field({"market_cap": 500_000_000, "beta": 1.2}, source="synthetic_test")
    ev.fields["fundamentals_summary"] = _field({
        "sector": "Technology", "industry": "Software",
        "heldPercentInstitutions": 0.42, "heldPercentInsiders": 0.05,
    }, source="synthetic_test")
    ev.fields["price_history"] = _field(
        [{"Close": 10 + i * 0.05} for i in range(300)], source="synthetic_test"
    )
    ev.fields["institutional_ownership"] = _field({"data": []}, source="synthetic_test")
    ev.fields["news"] = _field([
        {"headline": "Company announces new product launch"},
        {"headline": "Company wins major contract award"},
    ], source="synthetic_test")
    ev.fields["sec_filings"] = _field([], source="synthetic_test")
    return ev


def test_knowledge_no_qualitative_judgment_fields():
    ev = _synthetic_evidence()
    kp = build_knowledge(ev, screening_soft_flags=["small_cap"])
    assert kp.financial_health["revenue_cagr_3y_pct"]["status"] == "ok"
    assert kp.financial_health["revenue_cagr_3y_pct"]["value"] > 0
    assert kp.financial_health["debt_to_equity"]["value"] == 0.5
    assert kp.financial_health["current_ratio"]["value"] == 2.0
    assert kp.identity["size_tier"]["value"] == "small_cap"
    print("OK: knowledge derivation produces numeric facts, no evaluative labels")


def test_knowledge_missing_field_marked_missing_not_guessed():
    ev = Evidence(ticker="EMPTY")
    kp = build_knowledge(ev)
    assert kp.financial_health["revenue_yoy_pct"]["status"] == "missing"
    assert kp.financial_health["revenue_yoy_pct"]["value"] is None
    print("OK: missing evidence -> explicit 'missing' status, not interpolated")


def test_confidence_penalizes_soft_flags():
    ev = _synthetic_evidence()
    kp = build_knowledge(ev, screening_soft_flags=["micro_cap", "recent_ipo"])
    conf_flagged = compute_confidence(kp.metadata, screening_soft_flags=["micro_cap", "recent_ipo"])
    conf_clean = compute_confidence(kp.metadata, screening_soft_flags=[])
    assert conf_flagged["score"] < conf_clean["score"]
    print("OK: confidence score is lower when risk-reducing soft flags are present")


def test_risk_redflag_detects_litigation_keyword():
    ev = _synthetic_evidence()
    ev.fields["news"] = _field([{"headline": "Company faces class action lawsuit over disclosures"}], source="synthetic_test")
    kp = build_knowledge(ev)
    result = run_risk_check(ev, kp)
    types = [f["type"] for f in result["flags"]]
    assert "possible_litigation_or_investigation" in types
    assert result["overall_risk_level"] in ("moderate", "elevated")
    print("OK: risk/red-flag check surfaces litigation-pattern flag from news text")


def test_risk_redflag_high_leverage_flag():
    ev = _synthetic_evidence()

    def _row(name, values):
        row = {"index": name}
        for i, v in enumerate(values):
            row[f"col_{i}"] = v
        return row

    qfin = ev.fields["quarterly_financials"]["value"]
    qfin["balance_sheet"] = [
        _row("Total Debt", [900] * 20),
        _row("Common Stock Equity", [200] * 20),
        _row("Current Assets", [300] * 20),
        _row("Current Liabilities", [150] * 20),
    ]
    kp = build_knowledge(ev)
    result = run_risk_check(ev, kp)
    types = [f["type"] for f in result["flags"]]
    assert "high_leverage" in types
    print("OK: high debt-to-equity triggers high_leverage flag")


def test_three_modules_independent_outputs_differ():
    ev = _synthetic_evidence()
    kp = build_knowledge(ev, screening_soft_flags=["small_cap"])
    kp_dict = kp.to_dict()
    conf = compute_confidence(kp.metadata, screening_soft_flags=["small_cap"])
    risk = run_risk_check(ev, kp)

    fake_market_context = {
        "components": {
            "sector_rotation": {"value": {"inflow_sectors": ["Technology (XLK)"], "outflow_sectors": []}},
            "business_cycle_stage": {"value": "mid-cycle"},
            "yield_curve": {"value": "normal"},
            "liquidity_conditions": {"value": "loosening"},
            "volatility_index": {"value": "low_risk_on"},
            "market_sentiment": {"value": "greed"},
        }
    }
    catalysts = [{"type": "news_derived_catalyst", "estimated_date": None, "headline": "product launch"}]

    mb = multibagger.analyze(kp_dict, fake_market_context, risk, conf)
    qc = quality_compound.analyze(kp_dict, fake_market_context, risk, conf, peer_comparison=None)
    sp = speculative.analyze(kp_dict, fake_market_context, risk, conf, catalysts=catalysts)

    assert mb["module"] == "multibagger"
    assert qc["module"] == "quality_compound"
    assert sp["module"] == "speculative"
    # Modul harus punya reasoning masing-masing (independen), bukan turunan 1 skor gabungan
    assert mb["reasoning"] != qc["reasoning"]
    assert qc["reasoning"] != sp["reasoning"]
    print("OK: three reasoning modules produce independent, non-identical outputs from same Knowledge+Context")


def test_peer_comparison_empty_when_no_peers_explicit():
    ev = _synthetic_evidence()
    kp = build_knowledge(ev)
    result = compare_to_peers(kp, [])
    assert result["peer_group_size"] == 0
    assert "note" in result
    print("OK: peer comparison is explicit about absence of peer data, not silently averaged")


def test_revenue_cagr_fallback_to_annual_when_quarterly_insufficient():
    ev = Evidence(ticker="ANNUALTEST")

    def _row(name, values):
        row = {"index": name}
        for i, v in enumerate(values):
            row[f"col_{i}"] = v
        return row

    # Quarterly cuma 4 titik -- tidak cukup untuk CAGR 3 tahun (butuh index 12)
    ev.fields["quarterly_financials"] = _field({
        "income_stmt": [_row("Total Revenue", [110, 105, 100, 95])],
        "balance_sheet": [],
        "cashflow": [],
    }, source="synthetic_test")
    # Annual: 4 titik (tahun ini, -1, -2, -3) -- cukup untuk CAGR 3 tahun (index 3)
    ev.fields["annual_financials"] = _field({
        "income_stmt": [_row("Total Revenue", [400, 350, 300, 250])],
    }, source="synthetic_test")

    kp = build_knowledge(ev)
    assert kp.financial_health["revenue_cagr_3y_pct"]["status"] == "ok"
    expected = round(((400 / 250) ** (1 / 3) - 1) * 100, 3)
    assert kp.financial_health["revenue_cagr_3y_pct"]["value"] == expected
    print("OK: revenue CAGR 3y falls back to annual financials when quarterly data too short")


def test_business_model_category_heuristic():
    ev = Evidence(ticker="BMTEST")
    ev.fields["fundamentals_summary"] = _field({"sector": "Technology", "industry": "Software—Infrastructure"}, source="synthetic_test")
    kp = build_knowledge(ev)
    assert kp.competitive_position["business_model_category"]["status"] == "ok"
    assert kp.competitive_position["business_model_category"]["value"] == "subscription_or_software"
    assert kp.competitive_position["business_model_category"]["method"] == "heuristic_keyword_based"
    print("OK: business_model_category classified via explicit heuristic, method disclosed")


def test_price_return_1y_no_longer_always_missing():
    ev = Evidence(ticker="PRICETEST")
    # 400 hari data harga naik linear -> cukup buffer utk lookback 252 hari
    ev.fields["price_history"] = _field(
        [{"Close": 100 + i * 0.1} for i in range(400)], source="synthetic_test"
    )
    kp = build_knowledge(ev)
    assert kp.historical_trends["price_return_1y_pct"]["status"] == "ok"
    assert kp.historical_trends["price_return_1y_pct"]["value"] > 0
    print("OK: price_return_1y_pct computed correctly when enough price history buffer is stored")


def test_insider_transactions_normalized_as_facts_not_interpretation():
    ev = Evidence(ticker="INSIDERTEST")
    ev.fields["insider_transactions"] = _field([
        {"Start Date": "2026-06-01", "Insider": "Jane Doe", "Position": "CFO",
         "Transaction": "Sale", "Shares": 1000, "Value": 50000},
    ], source="synthetic_test")
    kp = build_knowledge(ev)
    txns = kp.ownership["recent_insider_transactions"]["value"]
    assert txns[0]["insider_name"] == "Jane Doe"
    assert txns[0]["transaction_type"] == "Sale"
    # Pastikan tidak ada interpretasi tambahan seperti "kurang percaya diri" dst.
    assert "confidence" not in txns[0] and "sentiment" not in txns[0]
    print("OK: insider transactions stored as plain facts (date/insider/type/shares/value), no interpretation added")


def test_insider_transactions_handles_nan_and_empty_transaction_column():
    ev = Evidence(ticker="INSIDERNAN")
    nan = float("nan")
    ev.fields["insider_transactions"] = _field([
        {"Start Date": "2026-06-01", "Insider": "John Roe", "Position": "Officer",
         "Transaction": "", "Text": "Sale at price 150", "Shares": 500, "Value": nan},
    ], source="synthetic_test")
    kp = build_knowledge(ev)
    txns = kp.ownership["recent_insider_transactions"]["value"]
    # NaN harus jadi None (JSON-safe), bukan NaN literal yang bukan JSON valid
    assert txns[0]["value_usd"] is None
    # 'Transaction' kosong -> fallback ke 'Text'
    assert txns[0]["transaction_type"] == "Sale at price 150"
    print("OK: NaN converted to JSON-safe None, empty 'Transaction' column falls back to 'Text'")


if __name__ == "__main__":
    test_knowledge_no_qualitative_judgment_fields()
    test_knowledge_missing_field_marked_missing_not_guessed()
    test_confidence_penalizes_soft_flags()
    test_risk_redflag_detects_litigation_keyword()
    test_risk_redflag_high_leverage_flag()
    test_three_modules_independent_outputs_differ()
    test_peer_comparison_empty_when_no_peers_explicit()
    test_revenue_cagr_fallback_to_annual_when_quarterly_insufficient()
    test_business_model_category_heuristic()
    test_price_return_1y_no_longer_always_missing()
    test_insider_transactions_normalized_as_facts_not_interpretation()
    test_insider_transactions_handles_nan_and_empty_transaction_column()
    print("\nALL LAYER 2 LOGIC TESTS PASSED")
