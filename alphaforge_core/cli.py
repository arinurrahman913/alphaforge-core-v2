"""
CLI — jalankan analisa end-to-end untuk satu ticker.

Contoh:
    python -m alphaforge_core.cli analyze AAPL
    python -m alphaforge_core.cli analyze AAPL --peers MSFT,GOOGL
    python -m alphaforge_core.cli analyze AAPL --json --pretty
"""
from __future__ import annotations

import argparse
import json
import sys

from .layer1.market_context_engine import build_market_context_package
from .layer2.pipeline import analyze_single_ticker
from .layer2.report_formatter import format_readable


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

    context_parser = sub.add_parser("context", help="Hitung Market Context Package (Layer 1) saja")
    context_parser.add_argument("--pretty", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "context":
        package = build_market_context_package()
        _print(package, args.pretty)
        return 0

    if args.command == "analyze":
        peers = [p.strip().upper() for p in args.peers.split(",") if p.strip()]
        print(f"[1/2] Menghitung Market Context Package (Layer 1)...", file=sys.stderr)
        market_context = build_market_context_package()
        print(f"[2/2] Menjalankan pipeline Layer 2 untuk {args.ticker.upper()}...", file=sys.stderr)
        result = analyze_single_ticker(args.ticker.upper(), market_context, peer_tickers=peers)
        if args.json:
            _print(result, args.pretty)
        else:
            print(format_readable(result))
        return 0

    return 1


def _print(obj, pretty: bool):
    if pretty:
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    else:
        print(json.dumps(obj, ensure_ascii=False, default=str))


if __name__ == "__main__":
    sys.exit(main())
