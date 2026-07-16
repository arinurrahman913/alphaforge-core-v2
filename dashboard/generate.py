"""
Generator dashboard AlphaForge v2 (statis, self-contained).

Menjalankan pipeline Layer 2 yang ASLI dengan tiga profil perusahaan sintetis
(karena generator ini dirancang bisa jalan tanpa akses API pasar live), lalu
mendemokan Decision Journal, dan me-render semuanya jadi satu file
`dashboard.html` yang bisa dibuka di HP/desktop tanpa server.

Jalankan dari root repo:
    python dashboard/generate.py
Hasil: dashboard/dashboard.html

Catatan: ini DATA CONTOH. Struktur & logika output identik dengan analisa
sungguhan (`python -m alphaforge_core.cli analyze AAPL`), hanya evidence-nya
sintetis supaya reproducible tanpa network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from alphaforge_core.layer2.evidence import Evidence, _field
from alphaforge_core.layer2.knowledge import build_knowledge
from alphaforge_core.layer2.confidence import compute_confidence
from alphaforge_core.layer2.risk_redflag import run_risk_check
from alphaforge_core.layer2.peer_comparison import compare_to_peers
from alphaforge_core.layer2 import catalyst_tracking, aggregator
from alphaforge_core.layer2.modules import multibagger, quality_compound, speculative
from alphaforge_core.layer2.journal import DecisionJournal


# --------------------------------------------------------------------------
# 1. Data sintetis + jalankan pipeline asli
# --------------------------------------------------------------------------
def _row(name, values):
    r = {"index": name}
    for i, v in enumerate(values):
        r[f"col_{i}"] = v
    return r


def make_evidence(ticker, revenue, market_cap, sector, industry,
                  debt, equity, inst_pct, news, beta=1.2, price_slope=0.05):
    ev = Evidence(ticker=ticker)
    ev.fields["quarterly_financials"] = _field({
        "income_stmt": [
            _row("Total Revenue", revenue),
            _row("Gross Profit", [v * 0.62 for v in revenue]),
            _row("Operating Income", [v * 0.21 for v in revenue]),
            _row("Net Income", [v * 0.16 for v in revenue]),
        ],
        "balance_sheet": [
            _row("Total Debt", [debt] * len(revenue)),
            _row("Common Stock Equity", [equity] * len(revenue)),
            _row("Current Assets", [300] * len(revenue)),
            _row("Current Liabilities", [150] * len(revenue)),
            _row("Cash And Cash Equivalents", [120] * len(revenue)),
        ],
        "cashflow": [_row("Free Cash Flow", [v * 0.18 for v in revenue])],
    }, source="synthetic_demo")
    ev.fields["market_stats"] = _field({"market_cap": market_cap, "beta": beta}, source="synthetic_demo")
    ev.fields["fundamentals_summary"] = _field({
        "sector": sector, "industry": industry,
        "heldPercentInstitutions": inst_pct, "heldPercentInsiders": 0.06,
    }, source="synthetic_demo")
    ev.fields["price_history"] = _field(
        [{"Close": 10 + i * price_slope} for i in range(400)], source="synthetic_demo")
    ev.fields["institutional_ownership"] = _field({"data": []}, source="synthetic_demo")
    ev.fields["news"] = _field(news, source="synthetic_demo")
    ev.fields["sec_filings"] = _field([], source="synthetic_demo")
    return ev


def _comp(kind, value, detail=None):
    return {"kind": kind, "value": value, "detail": detail or {}, "as_of": "2026-07-16T00:00:00+00:00"}


def build_market_context():
    mc = {
        "computed_at": "2026-07-16T00:00:00+00:00",
        "components_total": 12, "components_with_errors": 1,
        "components": {
            "business_cycle_stage": _comp("derived_approximated", "mid-cycle"),
            "sector_rotation": _comp("direct", {"inflow_sectors": ["Technology (XLK)", "Industrials (XLI)"],
                                                "outflow_sectors": ["Utilities (XLU)"]}),
            "money_flow": _comp("derived_approximated", "net_inflow_risk_assets"),
            "liquidity_conditions": _comp("direct", "loosening"),
            "yield_curve": _comp("direct", "normal"),
            "market_breadth": _comp("derived_approximated", None, {"note": "butuh daftar konstituen index"}),
            "volatility_index": _comp("direct", "low_risk_on"),
            "market_regime": _comp("direct", "bull_above_ma200"),
            "macro_calendar": _comp("direct", "FOMC dalam 8 hari"),
            "currency_dxy": _comp("direct", "sideways"),
            "commodity_signals": _comp("direct", "gold_up_oil_flat"),
            "market_sentiment": _comp("derived_approximated", "greed"),
        },
    }
    mc["components"]["market_breadth"]["error"] = "breadth_constituents belum disuplai"
    return mc


PROFILES = [
    dict(ticker="NOVA", sector="Technology", industry="Software—Application",
         revenue=[220, 205, 190, 175, 160, 150, 140, 128, 115, 105, 95, 88, 70, 64, 58, 52, 44, 40, 36, 33],
         market_cap=260_000_000, debt=120, equity=520, inst_pct=0.28, beta=1.7, price_slope=0.14,
         soft_flags=["micro_cap"],
         news=[{"headline": "NOVA unveils next-gen AI platform, guides revenue up"},
               {"headline": "NOVA signs multi-year enterprise contract"}]),
    dict(ticker="STED", sector="Consumer Staples", industry="Household Products",
         revenue=[512, 508, 505, 500, 498, 495, 492, 488, 485, 482, 479, 475, 470, 466, 462, 458, 452, 448, 445, 440],
         market_cap=48_000_000_000, debt=300, equity=1500, inst_pct=0.71, beta=0.7, price_slope=0.03,
         soft_flags=[],
         news=[{"headline": "STED raises dividend for 15th consecutive year"},
               {"headline": "STED reports steady margins amid input cost pressure"}]),
    dict(ticker="VOLT", sector="Health Care", industry="Biotechnology",
         revenue=[40, 36, 55, 20, 48, 15, 60, 12, 30, 10, 25, 8, 20, 6, 18, 5, 15, 4, 12, 3],
         market_cap=180_000_000, debt=900, equity=200, inst_pct=0.19, beta=2.4, price_slope=0.02,
         soft_flags=["micro_cap", "low_liquidity"],
         news=[{"headline": "VOLT faces class action lawsuit over trial disclosures"},
               {"headline": "VOLT awaits FDA decision on lead drug candidate next quarter"}]),
]
PRICE_AT = {"NOVA": 66.0, "STED": 22.0, "VOLT": 18.0}
PRICE_NOW = {"NOVA": 95.0, "STED": 23.5, "VOLT": 9.0}


def run_pipeline():
    market_context = build_market_context()
    knowledge_by_ticker = {}
    prepared = []
    for p in PROFILES:
        ev = make_evidence(p["ticker"], p["revenue"], p["market_cap"], p["sector"], p["industry"],
                           p["debt"], p["equity"], p["inst_pct"], p["news"], p["beta"], p["price_slope"])
        kp = build_knowledge(ev, screening_soft_flags=p["soft_flags"])
        knowledge_by_ticker[p["ticker"]] = kp
        prepared.append((p, ev, kp))

    outputs = []
    for p, ev, kp in prepared:
        kp_dict = kp.to_dict()
        conf = compute_confidence(kp.metadata, screening_soft_flags=p["soft_flags"])
        peers = [knowledge_by_ticker[q] for q in knowledge_by_ticker if q != p["ticker"]]
        peer_result = compare_to_peers(kp, peers)
        risk = run_risk_check(ev, kp)
        catalysts = catalyst_tracking.identify_catalysts(p["ticker"], ev)
        mb = multibagger.analyze(kp_dict, market_context, risk, conf)
        qc = quality_compound.analyze(kp_dict, market_context, risk, conf, peer_result)
        sp = speculative.analyze(kp_dict, market_context, risk, conf, catalysts)
        mc_summary = {n: c.get("value") for n, c in market_context["components"].items()}
        out = aggregator.aggregate(p["ticker"], kp_dict, conf, risk, mb, qc, sp, mc_summary)
        out["screening_soft_flags"] = p["soft_flags"]
        out["peer_comparison"] = peer_result
        out["catalysts"] = catalysts
        out["knowledge_full"] = kp_dict
        outputs.append(out)

    journal = DecisionJournal(db_path=":memory:")
    journal_view = []
    for out in outputs:
        eid = journal.record(out, price_at_analysis=PRICE_AT[out["ticker"]])
        journal_view.append(journal.evaluate_entry(
            eid, current_price=PRICE_NOW[out["ticker"]], as_of="2026-11-20T00:00:00+00:00"))

    return market_context, outputs, journal_view


# --------------------------------------------------------------------------
# 2. Trim data untuk dashboard
# --------------------------------------------------------------------------
def build_dashboard_data(market_context, outputs, journal_view):
    def trim_view(v):
        return {"signal": v["signal"], "score": v["internal_score_pct"],
                "reasoning": v.get("reasoning", [])[:4], "risk_note": v.get("risk_note")}

    analyses = []
    for a in outputs:
        def iv(sec, f):
            x = a["knowledge_full"].get(sec, {}).get(f) if a.get("knowledge_full") else None
            return x.get("value") if isinstance(x, dict) else None
        analyses.append({
            "ticker": a["ticker"],
            "sector": iv("identity", "sector"),
            "industry": iv("identity", "industry"),
            "size_tier": iv("identity", "size_tier"),
            "soft_flags": a.get("screening_soft_flags", []),
            "confidence": a["confidence"],
            "risk": a["risk_redflag"],
            "views": {k: trim_view(v) for k, v in a["views"].items()},
            "peer_size": a.get("peer_comparison", {}).get("peer_group_size"),
            "catalysts": a.get("catalysts", []),
            "methodology_version": a.get("methodology_version"),
        })

    mc = [{"name": name, "value": c.get("value"), "kind": c.get("kind"), "error": c.get("error")}
          for name, c in market_context["components"].items()]
    return {"market_context": mc, "analyses": analyses, "journal": journal_view}


# --------------------------------------------------------------------------
# 3. Render HTML
# --------------------------------------------------------------------------
HTML_TEMPLATE = r"""<title>AlphaForge v2 — Dashboard Analisa</title>
<style>
:root{
  --bg:#f4f6f8; --panel:#ffffff; --panel2:#eef1f5; --ink:#151b23; --muted:#5c6773;
  --line:#e3e7ee; --accent:#0e7490; --accent-ink:#0e7490; --accent-soft:#d7f0f4;
  --good:#15803d; --good-bg:#dcf5e3; --warn:#b45309; --warn-bg:#fdefcf;
  --na:#5d6b7a; --na-bg:#e9edf2; --bad:#b91c1c; --bad-bg:#fbe3e3;
  --up:#15803d; --down:#b91c1c;
  --shadow:0 1px 2px rgba(20,30,45,.06),0 4px 16px rgba(20,30,45,.05);
  --font-sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --font-mono:ui-monospace,"SF Mono","Cascadia Code","Roboto Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0c1016; --panel:#151b24; --panel2:#1b232e; --ink:#e7ecf3; --muted:#8b98a8;
  --line:#26303d; --accent:#22d3ee; --accent-ink:#5fe3f5; --accent-soft:#0a3742;
  --good:#34d399; --good-bg:#0e2a1d; --warn:#fbbf24; --warn-bg:#2c2410;
  --na:#93a2b3; --na-bg:#1b232e; --bad:#f87171; --bad-bg:#2c1616;
  --up:#34d399; --down:#f87171;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 20px rgba(0,0,0,.35);
}}
:root[data-theme="light"]{
  --bg:#f4f6f8; --panel:#ffffff; --panel2:#eef1f5; --ink:#151b23; --muted:#5c6773;
  --line:#e3e7ee; --accent:#0e7490; --accent-ink:#0e7490; --accent-soft:#d7f0f4;
  --good:#15803d; --good-bg:#dcf5e3; --warn:#b45309; --warn-bg:#fdefcf;
  --na:#5d6b7a; --na-bg:#e9edf2; --bad:#b91c1c; --bad-bg:#fbe3e3;
  --up:#15803d; --down:#b91c1c;
  --shadow:0 1px 2px rgba(20,30,45,.06),0 4px 16px rgba(20,30,45,.05);
}
:root[data-theme="dark"]{
  --bg:#0c1016; --panel:#151b24; --panel2:#1b232e; --ink:#e7ecf3; --muted:#8b98a8;
  --line:#26303d; --accent:#22d3ee; --accent-ink:#5fe3f5; --accent-soft:#0a3742;
  --good:#34d399; --good-bg:#0e2a1d; --warn:#fbbf24; --warn-bg:#2c2410;
  --na:#93a2b3; --na-bg:#1b232e; --bad:#f87171; --bad-bg:#2c1616;
  --up:#34d399; --down:#f87171;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 20px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0}
.wrap{background:var(--bg);color:var(--ink);font-family:var(--font-sans);
  line-height:1.5;-webkit-font-smoothing:antialiased;min-height:100vh;padding:0 0 56px}
.container{max-width:1080px;margin:0 auto;padding:0 16px}
.mono{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
header.top{background:linear-gradient(180deg,var(--panel),var(--bg));
  border-bottom:1px solid var(--line);padding:22px 0 18px;margin-bottom:18px}
.brand{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.brand h1{margin:0;font-size:clamp(1.35rem,4.5vw,1.9rem);letter-spacing:-.02em;
  font-weight:750;text-wrap:balance}
.brand .v{font-family:var(--font-mono);font-size:.72rem;color:var(--accent-ink);
  border:1px solid var(--accent);border-radius:6px;padding:2px 6px;font-weight:600}
.tagline{color:var(--muted);font-size:.92rem;margin:6px 0 0}
.banner{margin-top:14px;display:flex;gap:10px;align-items:flex-start;
  background:var(--warn-bg);border:1px solid color-mix(in srgb,var(--warn) 40%,transparent);
  border-radius:10px;padding:10px 12px;font-size:.82rem;color:var(--ink)}
.banner b{color:var(--warn)}
.banner .ic{font-family:var(--font-mono);font-weight:700;color:var(--warn)}
.sec{margin:26px 0 12px;display:flex;align-items:center;gap:10px}
.sec h2{margin:0;font-size:.82rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);font-weight:700}
.sec .rule{flex:1;height:1px;background:var(--line)}
.mc-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
@media(min-width:560px){.mc-grid{grid-template-columns:repeat(3,1fr)}}
@media(min-width:860px){.mc-grid{grid-template-columns:repeat(4,1fr)}}
.mc{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:9px 11px;box-shadow:var(--shadow)}
.mc .k{font-size:.68rem;color:var(--muted);letter-spacing:.02em;
  display:flex;justify-content:space-between;align-items:center;gap:6px}
.mc .val{font-family:var(--font-mono);font-size:.82rem;margin-top:3px;font-weight:600;word-break:break-word}
.mc .val.empty{color:var(--muted);font-style:italic;font-weight:400}
.kind{font-size:.56rem;font-family:var(--font-mono);padding:1px 5px;border-radius:4px;
  letter-spacing:.03em;white-space:nowrap;text-transform:uppercase}
.kind.direct{background:var(--accent-soft);color:var(--accent-ink)}
.kind.derived{background:var(--warn-bg);color:var(--warn)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;
  box-shadow:var(--shadow);padding:16px;margin-bottom:16px}
.p-head{display:flex;flex-wrap:wrap;gap:12px 16px;align-items:flex-start;
  justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:14px}
.p-id{display:flex;flex-direction:column;gap:4px;min-width:0}
.p-tk{font-family:var(--font-mono);font-size:1.5rem;font-weight:750;letter-spacing:-.01em;line-height:1}
.p-sub{color:var(--muted);font-size:.82rem}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:2px}
.chip{font-size:.66rem;font-family:var(--font-mono);padding:2px 7px;border-radius:20px;
  background:var(--panel2);color:var(--muted);border:1px solid var(--line)}
.p-meta{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.meter{min-width:120px}
.meter .lab{font-size:.66rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.meter .row{display:flex;align-items:baseline;gap:7px;margin:2px 0 4px}
.meter .num{font-family:var(--font-mono);font-size:1.25rem;font-weight:700}
.meter .tag{font-size:.66rem;font-family:var(--font-mono);text-transform:uppercase;
  padding:1px 6px;border-radius:5px;background:var(--panel2);color:var(--muted)}
.track{height:6px;border-radius:4px;background:var(--panel2);overflow:hidden;width:130px}
.track > i{display:block;height:100%;border-radius:4px;background:var(--accent)}
.risk{display:flex;flex-direction:column;gap:5px;align-items:flex-start}
.risk .lab{font-size:.66rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.rbadge{font-family:var(--font-mono);font-size:.78rem;font-weight:700;padding:3px 10px;
  border-radius:7px;display:inline-flex;align-items:center;gap:6px}
.rbadge::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.rbadge.good{background:var(--good-bg);color:var(--good)}
.rbadge.warn{background:var(--warn-bg);color:var(--warn)}
.rbadge.bad{background:var(--bad-bg);color:var(--bad)}
.flags{display:flex;flex-direction:column;gap:3px;margin-top:2px}
.flag{font-size:.68rem;color:var(--muted)}
.flag b{color:var(--ink);font-weight:600}
.lens-note{font-size:.72rem;color:var(--muted);margin:14px 0 10px;display:flex;gap:7px;align-items:center}
.lens-note b{color:var(--accent-ink)}
.lenses{display:grid;grid-template-columns:1fr;gap:10px}
@media(min-width:720px){.lenses{grid-template-columns:repeat(3,1fr)}}
.lens{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px;
  display:flex;flex-direction:column;gap:9px}
.lens h4{margin:0;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;
  font-weight:750;display:flex;align-items:center;gap:7px}
.lens h4 .dot{width:7px;height:7px;border-radius:2px;background:var(--accent)}
.lens .desc{font-size:.68rem;color:var(--muted);margin-top:-4px}
.sig{display:inline-flex;align-self:flex-start;font-family:var(--font-mono);font-weight:700;
  font-size:.74rem;padding:3px 9px;border-radius:7px}
.sig.good{background:var(--good-bg);color:var(--good)}
.sig.warn{background:var(--warn-bg);color:var(--warn)}
.sig.na{background:var(--na-bg);color:var(--na)}
.score{display:flex;align-items:center;gap:8px}
.score .track{width:100%}
.score .pct{font-family:var(--font-mono);font-size:.78rem;font-weight:700;min-width:44px;text-align:right}
.reasons{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:5px}
.reasons li{font-size:.74rem;color:var(--ink);padding-left:14px;position:relative;line-height:1.4}
.reasons li::before{content:"";position:absolute;left:2px;top:8px;width:5px;height:5px;
  border-radius:50%;background:var(--accent);opacity:.6}
.rnote{font-size:.7rem;color:var(--warn);background:var(--warn-bg);border-radius:7px;
  padding:6px 8px;line-height:1.35}
.jgrid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:720px){.jgrid{grid-template-columns:repeat(3,1fr)}}
.jcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);padding:14px;display:flex;flex-direction:column;gap:10px}
.jhead{display:flex;justify-content:space-between;align-items:baseline}
.jhead .tk{font-family:var(--font-mono);font-size:1.1rem;font-weight:750}
.jhead .days{font-size:.68rem;color:var(--muted);font-family:var(--font-mono)}
.jprice{display:flex;align-items:baseline;gap:8px;font-family:var(--font-mono)}
.jprice .from{color:var(--muted);font-size:.9rem}
.jprice .arrow{color:var(--muted)}
.jprice .to{font-size:.95rem;font-weight:700}
.jret{font-family:var(--font-mono);font-size:1.7rem;font-weight:750;line-height:1}
.jret.up{color:var(--up)} .jret.down{color:var(--down)} .jret.flat{color:var(--muted)}
.jret .dir{font-size:.66rem;letter-spacing:.08em;text-transform:uppercase;margin-left:6px;
  vertical-align:middle;color:var(--muted)}
.align{display:flex;flex-direction:column;gap:5px;border-top:1px solid var(--line);padding-top:9px}
.align .arow{display:flex;justify-content:space-between;align-items:center;font-size:.72rem}
.align .m{color:var(--muted);font-family:var(--font-mono);text-transform:uppercase;font-size:.64rem;letter-spacing:.05em}
.abadge{font-family:var(--font-mono);font-size:.66rem;font-weight:700;padding:1px 7px;border-radius:5px}
.abadge.aligned{background:var(--good-bg);color:var(--good)}
.abadge.misaligned{background:var(--bad-bg);color:var(--bad)}
.abadge.inconclusive{background:var(--na-bg);color:var(--na)}
.jver{font-size:.64rem;color:var(--muted);font-family:var(--font-mono)}
.foot{margin-top:30px;border-top:1px solid var(--line);padding-top:16px;
  font-size:.76rem;color:var(--muted);display:flex;flex-direction:column;gap:10px}
.foot .disc{background:var(--panel2);border-radius:10px;padding:11px 13px;line-height:1.5}
.foot code{font-family:var(--font-mono);background:var(--panel);border:1px solid var(--line);
  padding:1px 5px;border-radius:5px;font-size:.72rem;color:var(--accent-ink)}
.legend{display:flex;flex-wrap:wrap;gap:10px 16px}
.legend span{display:inline-flex;align-items:center;gap:5px;font-size:.7rem}
.legend i{width:9px;height:9px;border-radius:3px;display:inline-block}
</style>

<div class="wrap">
  <header class="top"><div class="container">
    <div class="brand"><h1>AlphaForge</h1><span class="v">v2</span></div>
    <p class="tagline">Tiga lensa independen berdampingan — bukan satu verdict. Market Context → Screening → Evidence → Knowledge → Risk → 3 Modul → Aggregator → Journal.</p>
    <div class="banner">
      <span class="ic">i</span>
      <span><b>Data contoh (sintetis).</b> Angka di bawah adalah output <i>asli</i> dari program yang dijalankan dengan data perusahaan buatan — struktur &amp; logikanya 100% sama dengan analisa sungguhan. Sandbox pembuatan ini tidak punya akses API pasar live; untuk data nyata, jalankan di laptop Anda (<code style="font-family:var(--font-mono)">analyze AAPL</code>).</span>
    </div>
  </div></header>

  <div class="container">
    <div class="sec"><h2>Market Context — Layer 1</h2><span class="rule"></span></div>
    <div class="mc-grid" id="mc"></div>

    <div class="sec"><h2>Analisa Saham — Layer 2</h2><span class="rule"></span></div>
    <div id="stocks"></div>

    <div class="sec"><h2>Decision Journal — Audit Historis</h2><span class="rule"></span></div>
    <p class="lens-note" style="margin-top:-2px"><b>Pengamatan</b>, bukan vonis benar/salah. Membandingkan sinyal saat analisa dengan gerak harga aktual sesudahnya (Prinsip #6 &amp; #10).</p>
    <div class="jgrid" id="journal"></div>

    <div class="foot">
      <div class="legend">
        <span><i style="background:var(--good)"></i>Kuat / selaras</span>
        <span><i style="background:var(--warn)"></i>Dipantau / flag sedang</span>
        <span><i style="background:var(--na)"></i>Belum didukung / inconclusive</span>
        <span><i style="background:var(--bad)"></i>Risiko tinggi / tidak selaras</span>
      </div>
      <div class="disc">Output ini bahan pertimbangan terstruktur, <b>bukan sinyal beli/jual otomatis</b>. AlphaForge tidak meramal masa depan (Prinsip #10). Keputusan akhir ada di tangan investor.</div>
      <div>Jalankan sendiri: <code>python -m alphaforge_core.cli analyze AAPL --peers MSFT,GOOGL --journal</code></div>
    </div>
  </div>
</div>

<script>
const DATA = __DATA__;
const SIG = {
  strong_growth_candidate:["Kandidat pertumbuhan kuat","good"],
  strong_quality_candidate:["Kandidat kualitas kuat","good"],
  actionable_speculative_setup:["Setup spekulatif actionable","good"],
  watch:["Layak dipantau","warn"],
  not_supported_by_current_evidence:["Belum didukung evidence","na"],
};
const LENS = {
  multibagger:["Multibagger","Pertumbuhan eksplosif jangka panjang"],
  quality_compound:["Quality / Compound","Compounder berkualitas & konsisten"],
  speculative:["Speculative","Momentum / katalis, risk-reward asimetris"],
};
const RISK = {
  none_detected:["Tidak ada flag","good"],
  moderate:["Flag sedang","warn"],
  elevated:["Flag tinggi","bad"],
};
const MCNAME = {
  business_cycle_stage:"Business Cycle", sector_rotation:"Sector Rotation",
  money_flow:"Money Flow", liquidity_conditions:"Liquidity", yield_curve:"Yield Curve",
  market_breadth:"Market Breadth", volatility_index:"Volatility (VIX)",
  market_regime:"Market Regime", macro_calendar:"Macro Calendar",
  currency_dxy:"Currency (DXY)", commodity_signals:"Commodity", market_sentiment:"Sentiment",
};
const esc = s => String(s==null?"":s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const fmtVal = v => {
  if(v==null) return null;
  if(typeof v==="object"){
    if(Array.isArray(v.inflow_sectors)) return "in: "+v.inflow_sectors.map(s=>s.split(" (")[0]).join(", ");
    return JSON.stringify(v);
  }
  return String(v).replace(/_/g," ");
};
document.getElementById("mc").innerHTML = DATA.market_context.map(c=>{
  const val = fmtVal(c.value);
  const kind = c.kind==="derived_approximated" ? '<span class="kind derived">perkiraan</span>'
             : c.kind==="direct" ? '<span class="kind direct">langsung</span>' : '';
  const body = val==null
    ? `<div class="val empty">${esc(c.error||"tidak tersedia")}</div>`
    : `<div class="val">${esc(val)}</div>`;
  return `<div class="mc"><div class="k"><span>${esc(MCNAME[c.name]||c.name)}</span>${kind}</div>${body}</div>`;
}).join("");
document.getElementById("stocks").innerHTML = DATA.analyses.map(a=>{
  const conf = a.confidence;
  const cpct = Math.round((conf.score||0)*100);
  const [rlab,rcls] = RISK[a.risk.overall_risk_level]||[a.risk.overall_risk_level,"na"];
  const flags = (a.risk.flags||[]).map(f=>
    `<div class="flag"><b>${esc(f.type.replace(/_/g," "))}</b> · ${esc(f.severity)} — ${esc((f.evidence||[]).join("; "))}</div>`).join("");
  const chips = [a.size_tier, ...(a.soft_flags||[])].filter(Boolean)
    .map(c=>`<span class="chip">${esc(String(c).replace(/_/g," "))}</span>`).join("");
  const lenses = ["multibagger","quality_compound","speculative"].map(k=>{
    const v=a.views[k]; const [slab,scls]=SIG[v.signal]||[v.signal,"na"];
    const [lname,ldesc]=LENS[k];
    const reasons=(v.reasoning||[]).slice(0,3).map(r=>`<li>${esc(r)}</li>`).join("");
    const rnote=v.risk_note?`<div class="rnote">${esc(v.risk_note)}</div>`:"";
    const pct=v.score==null?"—":v.score+"%";
    const w=v.score==null?0:v.score;
    return `<div class="lens">
      <h4><span class="dot"></span>${esc(lname)}</h4>
      <div class="desc">${esc(ldesc)}</div>
      <span class="sig ${scls}">${esc(slab)}</span>
      <div class="score"><div class="track"><i style="width:${w}%"></i></div><span class="pct">${pct}</span></div>
      <ul class="reasons">${reasons}</ul>${rnote}
    </div>`;
  }).join("");
  const peer = a.peer_size!=null?`<span class="chip">peer group: ${a.peer_size}</span>`:"";
  return `<div class="panel">
    <div class="p-head">
      <div class="p-id">
        <span class="p-tk">${esc(a.ticker)}</span>
        <span class="p-sub">${esc(a.sector||"—")}${a.industry?" · "+esc(a.industry):""}</span>
        <div class="chips">${chips}${peer}</div>
      </div>
      <div class="p-meta">
        <div class="meter">
          <div class="lab">Confidence</div>
          <div class="row"><span class="num">${cpct}%</span><span class="tag">${esc(conf.label||"")}</span></div>
          <div class="track"><i style="width:${cpct}%"></i></div>
        </div>
        <div class="risk">
          <span class="lab">Risk / Red-Flag</span>
          <span class="rbadge ${rcls}">${esc(rlab)}</span>
        </div>
      </div>
    </div>
    ${flags?`<div class="flags">${flags}</div>`:""}
    <div class="lens-note"><b>Tiga lensa independen</b>&nbsp;— Knowledge yang sama, reasoning terpisah. Tidak digabung jadi satu skor.</div>
    <div class="lenses">${lenses}</div>
  </div>`;
}).join("");
document.getElementById("journal").innerHTML = DATA.journal.map(j=>{
  const dir=j.realized_direction;
  const ret=j.realized_return_pct==null?"—":(j.realized_return_pct>0?"+":"")+j.realized_return_pct+"%";
  const align=["multibagger","quality_compound","speculative"].map(k=>{
    const a=j.module_alignment[k]||"inconclusive";
    return `<div class="arow"><span class="m">${k.replace("_compound","/comp").replace("multibagger","multibag")}</span><span class="abadge ${a}">${a}</span></div>`;
  }).join("");
  const mism = j.methodology_version_mismatch
    ? `<div class="jver" style="color:var(--warn)">⚠ versi metodologi beda: ${esc(j.methodology_version_at_analysis)} → ${esc(j.methodology_version_now)}</div>`
    : `<div class="jver">metodologi v${esc(j.methodology_version_now)}</div>`;
  return `<div class="jcard">
    <div class="jhead"><span class="tk">${esc(j.ticker)}</span><span class="days">${j.holding_days} hari</span></div>
    <div class="jprice"><span class="from">$${esc(j.price_at_analysis)}</span><span class="arrow">→</span><span class="to">$${esc(j.price_now)}</span></div>
    <div class="jret ${dir}">${ret}<span class="dir">${esc(dir)}</span></div>
    <div class="align">${align}</div>
    ${mism}
  </div>`;
}).join("");
</script>
"""


def render_html(dashboard_data) -> str:
    return HTML_TEMPLATE.replace("__DATA__", json.dumps(dashboard_data, ensure_ascii=False))


def main():
    market_context, outputs, journal_view = run_pipeline()
    data = build_dashboard_data(market_context, outputs, journal_view)
    html = render_html(data)
    out_html = Path(__file__).resolve().parent / "dashboard.html"
    out_json = Path(__file__).resolve().parent / "sample_data.json"
    out_html.write_text(html, encoding="utf-8")
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"WROTE {out_html} ({len(html)} bytes)")
    print(f"WROTE {out_json}")
    for out in outputs:
        v = out["views"]
        print(f"  {out['ticker']}: MB={v['multibagger']['signal']} "
              f"QC={v['quality_compound']['signal']} SP={v['speculative']['signal']} "
              f"risk={out['risk_redflag']['overall_risk_level']}")


if __name__ == "__main__":
    main()
