"""
Report Formatter — mengubah output Aggregator (JSON) jadi ringkasan teks yang
enak dibaca manusia di terminal. TIDAK menambah interpretasi baru -- murni
menyusun ulang & memformat data yang sudah ada di output pipeline, sesuai
urutan baca yang disarankan: Confidence -> Risk -> 3 Views -> detail per view.

Dipakai lewat CLI: `python -m alphaforge_core.cli analyze AAPL` (default).
Untuk JSON mentah, pakai flag --json.
"""
from __future__ import annotations

SIGNAL_LABELS = {
    "strong_growth_candidate": "Kandidat pertumbuhan kuat",
    "watch": "Layak dipantau",
    "not_supported_by_current_evidence": "Belum didukung evidence saat ini",
}

RISK_LEVEL_LABELS = {
    "none_detected": "Tidak ada flag terdeteksi",
    "moderate": "Ada flag tingkat sedang -- baca detailnya",
    "elevated": "Ada flag tingkat tinggi -- baca detailnya",
}

VIEW_ORDER = [
    ("multibagger", "MULTIBAGGER", "Cari saham yang berpotensi tumbuh eksplosif jangka panjang"),
    ("quality_compound", "QUALITY / COMPOUND", "Cari perusahaan berkualitas untuk dipegang jangka panjang"),
    ("speculative", "SPECULATIVE", "Cari momentum/katalis jangka pendek dengan risk-reward asimetris"),
]


def _bar(width: int = 62, char: str = "-") -> str:
    return char * width


def _section_title(title: str) -> str:
    return f"\n{_bar()}\n{title}\n{_bar()}"


def format_readable(output: dict) -> str:
    lines: list[str] = []
    ticker = output.get("ticker", "?")
    identity = output.get("identity", {})
    sector = (identity.get("sector") or {}).get("value") or "?"
    industry = (identity.get("industry") or {}).get("value") or "?"
    size_tier = (identity.get("size_tier") or {}).get("value") or "?"

    lines.append(_bar("=", 62))
    lines.append(f"  ALPHAFORGE v2 -- {ticker}")
    lines.append(f"  {sector} / {industry} / {size_tier}")
    lines.append(f"  Dihitung: {output.get('generated_at', '?')}")
    lines.append(_bar("=", 62))

    # --- Langkah 1: Confidence ---
    conf = output.get("confidence", {})
    lines.append(_section_title("1) SEBERAPA BISA DIPERCAYA DATANYA?"))
    lines.append(
        f"  Confidence: {conf.get('label', '?').upper()} ({conf.get('score', '?')})"
    )
    lines.append(
        f"  Kelengkapan data: {round((conf.get('completeness_ratio') or 0) * 100)}% "
        f"| Sumber: {conf.get('sources_count', '?')} | Umur data: {conf.get('evidence_age_days', '?')} hari"
    )
    if conf.get("flags_applied"):
        lines.append(f"  Catatan: confidence diturunkan karena -> {', '.join(conf['flags_applied'])}")
    lines.append(
        "  (Ini ukuran kualitas DATA-nya, bukan ukuran aman/tidaknya saham -- "
        "lihat bagian Risk di bawah untuk itu.)"
    )

    # --- Langkah 2: Risk / Red-Flag ---
    risk = output.get("risk_redflag", {})
    level = risk.get("overall_risk_level", "?")
    lines.append(_section_title("2) ADA HAL YANG PERLU DIWASPADAI?"))
    lines.append(f"  Status: {RISK_LEVEL_LABELS.get(level, level)}")
    for f in risk.get("flags", []):
        lines.append(f"  - [{f.get('severity', '?').upper()}] {f.get('type', '?')}")
        for ev in (f.get("evidence") or [])[:3]:
            lines.append(f"      \u2022 {ev}")
    if not risk.get("flags"):
        lines.append("  Tidak ada pola red flag yang terdeteksi dari data yang tersedia.")

    # --- Langkah 3: Tiga Pandangan ---
    lines.append(_section_title("3) TIGA SUDUT PANDANG (pilih yang relevan untuk tujuanmu)"))
    views = output.get("views", {})
    for key, label, desc in VIEW_ORDER:
        v = views.get(key)
        if not v:
            continue
        signal = v.get("signal", "?")
        pct = v.get("internal_score_pct")
        lines.append(f"\n  [{label}] {desc}")
        lines.append(f"  -> {SIGNAL_LABELS.get(signal, signal)} (skor internal: {pct}%)")
        for r in v.get("reasoning", []):
            lines.append(f"     - {r}")
        if v.get("risk_note"):
            lines.append(f"     ! {v['risk_note']}")
        if v.get("catalysts"):
            lines.append("     Katalis mendatang:")
            for c in v["catalysts"]:
                date_str = c.get("estimated_date") or "tanggal belum pasti"
                extra = c.get("headline", "")
                lines.append(f"       - {c.get('type', '?')} ({date_str}) {('- ' + extra) if extra else ''}")

    # --- Peer comparison ringkas ---
    peer = output.get("peer_comparison", {})
    if peer.get("peer_group_size"):
        lines.append(_section_title("4) DIBANDING PEER"))
        if peer.get("note"):
            lines.append(f"  {peer['note']}")
        for metric, m in peer.get("metrics", {}).items():
            lines.append(
                f"  - {metric}: {m.get('target')} (peer median: {m.get('peer_median')}, "
                f"persentil: {m.get('target_percentile_within_peers')})"
            )

    lines.append(_bar("=", 62))
    lines.append(f"  {output.get('disclaimer', '')}")
    lines.append(_bar("=", 62))

    return "\n".join(lines)
