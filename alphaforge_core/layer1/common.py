"""
Utilitas bersama untuk komponen Layer 1.

Setiap komponen mengembalikan dict dengan bentuk seragam supaya Market Context
Package (market_context_engine.py) bisa menggabungkannya secara konsisten:

{
    "component": "<nama_komponen>",
    "kind": "direct" | "derived_approximated",   # lihat Prinsip #5 & Glosarium
    "value": <hasil utama, bisa str/float/dict>,
    "detail": {...},                              # data pendukung untuk transparansi
    "as_of": "<ISO timestamp>",
    "error": None | "<pesan error>",
}

`kind = "derived_approximated"` WAJIB dipakai untuk komponen yang menurut
Glosarium (`00_Foundation/03_GLOSSARY.md`) termasuk "Derived/Approximated Data" —
supaya konsumen (Layer 2 / tampilan akhir) tahu ini bukan angka resmi tunggal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def make_reading(component: str, kind: str, value: Any, detail: Optional[dict] = None,
                  error: Optional[str] = None) -> dict:
    assert kind in ("direct", "derived_approximated")
    return {
        "component": component,
        "kind": kind,
        "value": value,
        "detail": detail or {},
        "as_of": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }


def error_reading(component: str, kind: str, error: str) -> dict:
    return make_reading(component, kind, value=None, detail={}, error=error)
