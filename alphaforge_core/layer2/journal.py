"""
Historical Tracking / Decision Journal — 03_LAYER2_SPECS/12_HISTORICAL_TRACKING_JOURNAL.md

Tahap terakhir Layer 2. Menyimpan snapshot Output (hasil tiga modul + confidence
+ flag risk + versi metodologi) setiap kali sebuah analisa dijalankan, lalu
memungkinkan pembandingan entri lama terhadap pergerakan harga aktual di
kemudian hari — supaya bisa diaudit apakah reasoning-nya terbukti akurat atau
sekadar terdengar meyakinkan (Prinsip #6, 00_Foundation/02_PRINCIPLES.md).

Prinsip desain yang dipegang di sini:
- **Versi metodologi wajib tersimpan** di tiap entri (Prinsip #6). Saat evaluasi,
  kalau versi metodologi entri berbeda dari versi saat ini, itu ditandai
  eksplisit — audit membandingkan formula yang mungkin sudah berubah.
- **Tidak meramal, hanya mencatat & membandingkan** (Prinsip #10). Evaluasi
  menghasilkan pengamatan deskriptif (return terealisasi, arah gerak, apakah
  stance modul selaras dengan gerak harga), BUKAN vonis "modul benar/salah".
- **Data hilang ditandai eksplisit, tidak ditebak** — kalau harga saat analisa
  atau harga saat evaluasi tidak tersedia, hasilnya `missing`, bukan diisi 0.
- **Jurnal terpisah dari cache**: cache boleh kadaluarsa, jurnal harus persisten.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .. import config

# Stance tiap signal modul reasoning terhadap saham: apakah modul "tertarik"
# (constructive), netral (menunggu), atau tidak mendukung. Dipakai HANYA untuk
# pengamatan keselarasan arah saat evaluasi — bukan bobot/skor.
_SIGNAL_STANCE = {
    # Multibagger
    "strong_growth_candidate": "constructive",
    # Quality/Compound
    "strong_quality_candidate": "constructive",
    # Speculative
    "actionable_speculative_setup": "constructive",
    # Umum ketiga modul
    "watch": "neutral",
    "not_supported_by_current_evidence": "not_constructive",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class DecisionJournal:
    """Penyimpanan entri analisa berbasis SQLite (pola sama seperti cache.py).

    db_path bisa di-override untuk testing (mis. `:memory:` atau file temp),
    supaya tes jalan tanpa menyentuh jurnal asli pengguna.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path is not None else config.JOURNAL_DB_PATH
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                analyzed_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                methodology_version TEXT NOT NULL,
                price_at_analysis REAL,
                confidence_score REAL,
                confidence_label TEXT,
                risk_level TEXT,
                signal_multibagger TEXT,
                signal_quality_compound TEXT,
                signal_speculative TEXT,
                full_output TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_journal_ticker ON journal_entries(ticker)"
        )
        self._conn.commit()

    # -- Perekaman ---------------------------------------------------------

    def record(self, output: dict, price_at_analysis: Optional[float] = None) -> int:
        """Simpan satu snapshot Output Aggregator. Kembalikan id entri.

        `output` adalah dict hasil `pipeline.analyze_single_ticker(...)`.
        `price_at_analysis` opsional — harga saham saat analisa, jadi dasar
        perhitungan return terealisasi saat evaluasi nanti. Kalau tidak
        disuplai, evaluasi return akan ditandai `missing` (tidak ditebak).
        """
        if output.get("stage_stopped_at"):
            raise ValueError(
                "Output berhenti di tahap awal (mis. gagal Screening / red flag ekstrem) "
                "dan tidak punya hasil tiga modul untuk dijurnalkan: "
                f"stage_stopped_at={output.get('stage_stopped_at')!r}"
            )

        views = output.get("views", {})
        conf = output.get("confidence") or {}
        risk = output.get("risk_redflag") or {}

        def _sig(module: str):
            return (views.get(module) or {}).get("signal")

        cur = self._conn.execute(
            """
            INSERT INTO journal_entries (
                ticker, analyzed_at, recorded_at, methodology_version,
                price_at_analysis, confidence_score, confidence_label, risk_level,
                signal_multibagger, signal_quality_compound, signal_speculative,
                full_output
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                output.get("ticker"),
                output.get("generated_at") or _now_iso(),
                _now_iso(),
                output.get("methodology_version") or config.METHODOLOGY_VERSION,
                price_at_analysis,
                conf.get("score"),
                conf.get("label"),
                risk.get("overall_risk_level"),
                _sig("multibagger"),
                _sig("quality_compound"),
                _sig("speculative"),
                json.dumps(output, ensure_ascii=False, default=str),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # -- Pembacaan ---------------------------------------------------------

    def get_entry(self, entry_id: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM journal_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_entries(self, ticker: Optional[str] = None, limit: int = 50) -> list[dict]:
        if ticker:
            rows = self._conn.execute(
                "SELECT * FROM journal_entries WHERE ticker = ? ORDER BY id DESC LIMIT ?",
                (ticker.upper(), limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM journal_entries ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        # full_output disimpan sebagai JSON string; kembalikan sebagai objek.
        raw = d.pop("full_output", None)
        if raw:
            try:
                d["full_output"] = json.loads(raw)
            except json.JSONDecodeError:
                d["full_output"] = None
        return d

    # -- Evaluasi ----------------------------------------------------------

    def evaluate_entry(
        self,
        entry_id: int,
        current_price: Optional[float],
        as_of: Optional[str] = None,
    ) -> dict:
        """Bandingkan satu entri lama dengan harga terkini.

        `current_price` disuplai dari luar (callable price-lookup) supaya modul
        ini bisa diuji offline tanpa network. Kalau `None`, return terealisasi
        ditandai `missing`.
        """
        entry = self.get_entry(entry_id)
        if entry is None:
            raise KeyError(f"Entri jurnal id={entry_id} tidak ditemukan.")
        return self._evaluate(entry, current_price, as_of)

    def evaluate_all(
        self,
        price_lookup: Callable[[str], Optional[float]],
        ticker: Optional[str] = None,
        min_holding_days: float = 0.0,
        limit: int = 500,
    ) -> list[dict]:
        """Evaluasi banyak entri sekaligus. `price_lookup(ticker) -> harga|None`.

        `min_holding_days`: lewati entri yang belum cukup "matang" (baru dianalisa
        beberapa hari lalu) — membandingkan reasoning jangka panjang dengan gerak
        harga beberapa hari jelas tidak bermakna.
        """
        results = []
        now = datetime.now(timezone.utc)
        for entry in self.list_entries(ticker=ticker, limit=limit):
            analyzed = _parse_iso(entry.get("analyzed_at"))
            if analyzed is not None and min_holding_days > 0:
                age_days = (now - analyzed).total_seconds() / 86400
                if age_days < min_holding_days:
                    continue
            try:
                price = price_lookup(entry["ticker"])
            except Exception as exc:  # noqa: BLE001 - satu lookup gagal tidak menggagalkan sisanya
                price = None
                results.append(self._evaluate(entry, None, now.isoformat(),
                                               lookup_error=str(exc)))
                continue
            results.append(self._evaluate(entry, price, now.isoformat()))
        return results

    def _evaluate(
        self,
        entry: dict,
        current_price: Optional[float],
        as_of: Optional[str],
        lookup_error: Optional[str] = None,
    ) -> dict:
        as_of = as_of or _now_iso()
        analyzed = _parse_iso(entry.get("analyzed_at"))
        as_of_dt = _parse_iso(as_of)
        holding_days = None
        if analyzed is not None and as_of_dt is not None:
            holding_days = round((as_of_dt - analyzed).total_seconds() / 86400, 2)

        price_then = entry.get("price_at_analysis")
        realized_return_pct = None
        direction = "missing"
        if price_then is not None and current_price is not None and price_then != 0:
            realized_return_pct = round((current_price - price_then) / price_then * 100, 2)
            band = config.JOURNAL_FLAT_BAND_PCT
            if realized_return_pct > band:
                direction = "up"
            elif realized_return_pct < -band:
                direction = "down"
            else:
                direction = "flat"

        # Keselarasan per modul: deskriptif, bukan vonis benar/salah.
        module_signals = {
            "multibagger": entry.get("signal_multibagger"),
            "quality_compound": entry.get("signal_quality_compound"),
            "speculative": entry.get("signal_speculative"),
        }
        module_outcomes = {
            name: self._alignment(signal, direction)
            for name, signal in module_signals.items()
        }

        version_now = config.METHODOLOGY_VERSION
        version_then = entry.get("methodology_version")
        version_mismatch = bool(version_then) and version_then != version_now

        notes = []
        if version_mismatch:
            notes.append(
                f"Versi metodologi berbeda: entri dibuat dengan '{version_then}', "
                f"versi saat ini '{version_now}'. Perbandingan lintas-versi bisa bias "
                "(Prinsip #6) — tafsirkan hati-hati."
            )
        if lookup_error:
            notes.append(f"Gagal mengambil harga terkini: {lookup_error}")
        if direction == "missing":
            notes.append(
                "Return terealisasi tidak bisa dihitung (harga saat analisa dan/atau "
                "harga terkini tidak tersedia) — ditandai missing, bukan diasumsikan."
            )

        return {
            "entry_id": entry.get("id"),
            "ticker": entry.get("ticker"),
            "analyzed_at": entry.get("analyzed_at"),
            "evaluated_as_of": as_of,
            "holding_days": holding_days,
            "methodology_version_at_analysis": version_then,
            "methodology_version_now": version_now,
            "methodology_version_mismatch": version_mismatch,
            "price_at_analysis": price_then,
            "price_now": current_price,
            "realized_return_pct": realized_return_pct,
            "realized_direction": direction,
            "module_signals": module_signals,
            "module_alignment": module_outcomes,
            "notes": notes,
            "disclaimer": (
                "Evaluasi ini adalah pengamatan historis (return terealisasi vs stance "
                "modul), BUKAN vonis bahwa sebuah modul benar/salah. AlphaForge tidak "
                "meramal (Prinsip #10)."
            ),
        }

    @staticmethod
    def _alignment(signal: Optional[str], direction: str) -> str:
        """Apakah stance modul selaras dengan arah gerak harga terealisasi.

        Deskriptif saja:
        - 'aligned'      : stance constructive & harga naik, atau not_constructive & turun
        - 'misaligned'   : stance constructive & harga turun, atau not_constructive & naik
        - 'inconclusive' : stance netral, harga flat, atau data harga hilang
        """
        stance = _SIGNAL_STANCE.get(signal or "", "unknown")
        if direction in ("missing", "flat") or stance in ("neutral", "unknown"):
            return "inconclusive"
        if stance == "constructive":
            return "aligned" if direction == "up" else "misaligned"
        if stance == "not_constructive":
            return "aligned" if direction == "down" else "misaligned"
        return "inconclusive"

    def close(self) -> None:
        self._conn.close()


_default_journal: Optional[DecisionJournal] = None


def default_journal() -> DecisionJournal:
    global _default_journal
    if _default_journal is None:
        _default_journal = DecisionJournal()
    return _default_journal
