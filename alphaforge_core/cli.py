"""
CLI — jalankan analisa end-to-end untuk satu ticker + kelola Decision Journal.

Contoh:
    python -m alphaforge_core.cli analyze AAPL
    python -m alphaforge_core.cli analyze AAPL --peers MSFT,GOOGL
    python -m alphaforge_core.cli analyze AAPL --json --pretty
    python -m alphaforge_core.cli analyze AAPL --journal        # rekam ke jurnal
    python -m alphaforge_core.cli journal list                  # lihat entri
    python -m alphaforge_core.cli journal list AAPL
    python -m alphaforge_core.cli journal evaluate --min-days 90 # audit vs harga aktual
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .layer1.market_context_engine import build_market_context_package
from .layer2.pipeline import analyze_single_ticker
from .layer2.report_formatter import format_readable


def _current_price(ticker: str) -> Optional[float]:
    """Harga terkini via Yahoo Finance fast_info. Import lokal supaya subcommand
    yang tidak butuh network tidak ikut menyeret provider. Kembalikan None kalau
    tidak tersedia (dijadikan `missing` oleh jurnal, bukan ditebak)."""
    from .providers import yahoo_finance
    try:
        fi = yahoo_finance.get_fast_info(ticker)
    except Exception:  # noqa: BLE001 - kegagalan lookup jadi harga None yang eksplisit
        return None
    for key in ("last_price", "lastPrice", "regularMarketPrice", "last_close", "previous_close"):
        val = fi.get(key) if isinstance(fi, dict) else None
        if isinstance(val, (int, float)):
            return float(val)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(prog="alphaforge_core", description="AlphaForge v2 — analisa 1 saham end-to-end")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_parser = sub.add_parser("analyze", help="Analisa 1 ticker: Layer 1 + Layer 2 penuh")
    analyze_parser.add_argument("ticker", type=str, help="Ticker saham, mis. AAPL")
    analyze_parser.add_argument("--peers", type=str, default="",
                                 help="Daftar ticker peer dipisah koma, mis. MSFT,GOOGL (opsional)")
    analyze_parser.add_argument("--json", action="store_true",
                                 help="Cetak JSON mentah, bukan ringkasan enak dibaca (default)")
    analyze_parser.add_argument("--pretty", action="store_true", help="Kalau dipakai bareng --json, cetak JSON rapi (indented)")
    analyze_parser.add_argument("--journal", action="store_true",
                                 help="Rekam Output ke Decision Journal (Historical Tracking) untuk diaudit nanti")

    context_parser = sub.add_parser("context", help="Hitung Market Context Package (Layer 1) saja")
    context_parser.add_argument("--pretty", action="store_true")

    journal_parser = sub.add_parser("journal", help="Kelola Decision Journal (Historical Tracking)")
    journal_sub = journal_parser.add_subparsers(dest="journal_command", required=True)

    jlist = journal_sub.add_parser("list", help="Tampilkan entri jurnal tersimpan")
    jlist.add_argument("ticker", nargs="?", default=None, help="Filter per ticker (opsional)")
    jlist.add_argument("--limit", type=int, default=50)
    jlist.add_argument("--json", action="store_true")
    jlist.add_argument("--pretty", action="store_true")

    jeval = journal_sub.add_parser("evaluate", help="Bandingkan entri lama dengan harga aktual (audit)")
    jeval.add_argument("--ticker", type=str, default=None, help="Filter per ticker (opsional)")
    jeval.add_argument("--min-days", type=float, default=0.0,
                       help="Hanya evaluasi entri yang usianya >= sekian hari (default 0)")
    jeval.add_argument("--json", action="store_true")
    jeval.add_argument("--pretty", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "context":
        package = build_market_context_package()
        _print(package, args.pretty)
        return 0

    if args.command == "analyze":
        peers = [p.strip().upper() for p in args.peers.split(",") if p.strip()]
        ticker = args.ticker.upper()
        print("[1/2] Menghitung Market Context Package (Layer 1)...", file=sys.stderr)
        market_context = build_market_context_package()
        print(f"[2/2] Menjalankan pipeline Layer 2 untuk {ticker}...", file=sys.stderr)
        result = analyze_single_ticker(ticker, market_context, peer_tickers=peers)

        if args.journal:
            _record_to_journal(result, ticker)

        if args.json:
            _print(result, args.pretty)
        else:
            print(format_readable(result))
        return 0

    if args.command == "journal":
        return _run_journal(args)

    return 1


def _record_to_journal(result: dict, ticker: str) -> None:
    from .layer2.journal import default_journal
    if result.get("stage_stopped_at"):
        print(f"[jurnal] Tidak direkam: analisa {ticker} berhenti di tahap "
              f"'{result.get('stage_stopped_at')}' (tidak ada hasil tiga modul).",
              file=sys.stderr)
        return
    price = _current_price(ticker)
    entry_id = default_journal().record(result, price_at_analysis=price)
    price_note = f"harga saat analisa = {price}" if price is not None else "harga saat analisa TIDAK tersedia (missing)"
    print(f"[jurnal] Direkam sebagai entri #{entry_id} ({price_note}).", file=sys.stderr)


def _run_journal(args) -> int:
    from .layer2.journal import default_journal
    journal = default_journal()

    if args.journal_command == "list":
        entries = journal.list_entries(ticker=args.ticker.upper() if args.ticker else None,
                                       limit=args.limit)
        if args.json:
            _print(entries, args.pretty)
        else:
            print(_format_journal_list(entries))
        return 0

    if args.journal_command == "evaluate":
        results = journal.evaluate_all(
            price_lookup=_current_price,
            ticker=args.ticker.upper() if args.ticker else None,
            min_holding_days=args.min_days,
        )
        if args.json:
            _print(results, args.pretty)
        else:
            print(_format_journal_eval(results))
        return 0

    return 1


def _format_journal_list(entries: list) -> str:
    if not entries:
        return "Jurnal masih kosong. Rekam dengan: analyze <TICKER> --journal"
    lines = [f"{len(entries)} entri terbaru:", "-" * 62]
    for e in entries:
        lines.append(
            f"#{e['id']:<4} {e['ticker']:<6} {(e.get('analyzed_at') or '')[:10]}  "
            f"v{e.get('methodology_version')}  "
            f"MB={e.get('signal_multibagger')} QC={e.get('signal_quality_compound')} "
            f"SP={e.get('signal_speculative')}  "
            f"price@={e.get('price_at_analysis')}"
        )
    return "\n".join(lines)


def _format_journal_eval(results: list) -> str:
    if not results:
        return "Tidak ada entri yang dievaluasi (jurnal kosong atau semua di bawah --min-days)."
    lines = [f"Evaluasi {len(results)} entri (pengamatan historis, bukan vonis benar/salah):", "=" * 62]
    for r in results:
        lines.append(
            f"#{r['entry_id']} {r['ticker']}  dianalisa {(r.get('analyzed_at') or '')[:10]}  "
            f"holding={r.get('holding_days')}h"
        )
        lines.append(
            f"    harga {r.get('price_at_analysis')} -> {r.get('price_now')}  "
            f"= {r.get('realized_return_pct')}% ({r.get('realized_direction')})"
        )
        align = r.get("module_alignment", {})
        lines.append(f"    keselarasan: MB={align.get('multibagger')} "
                     f"QC={align.get('quality_compound')} SP={align.get('speculative')}")
        if r.get("methodology_version_mismatch"):
            lines.append(f"    [!] versi metodologi beda: {r.get('methodology_version_at_analysis')} "
                         f"-> {r.get('methodology_version_now')}")
        for note in r.get("notes", []):
            lines.append(f"    - {note}")
        lines.append("-" * 62)
    return "\n".join(lines)


def _print(obj, pretty: bool):
    if pretty:
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(obj, ensure_ascii=False, default=str))


if __name__ == "__main__":
    sys.exit(main())
