"""
Konfigurasi terpusat AlphaForge v2.

Semua API key diambil dari environment variable, TIDAK di-hardcode.
Kalau sebuah key tidak tersedia, provider terkait harus degrade
dengan jelas (raise DataUnavailableError / tandai field `missing`) —
bukan diam-diam pakai data palsu. Ini konsisten dengan Prinsip #5
(Confidence Itu Eksplisit) di 00_Foundation/02_PRINCIPLES.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Auto-load file .env (kalau ada) supaya API key tidak perlu di-set manual
# lewat $env:/export tiap buka terminal baru. Dicari di root project (2 folder
# di atas file ini: alphaforge_core/config.py -> alphaforge-core-v2/.env).
# Kalau package python-dotenv tidak terinstall, lewati saja secara diam-diam --
# fallback tetap ke os.environ biasa (mis. kalau user memang set manual).
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv  # type: ignore

    _PROJECT_ROOT = Path(__file__).resolve().parent.parent
    _ENV_FILE = _PROJECT_ROOT / ".env"
    if _ENV_FILE.exists():
        # override=True: isi file .env SELALU menang dibanding env var yang
        # kebetulan sudah nyangkut di sesi shell (mis. dari percobaan $env:
        # sebelumnya di terminal yang sama). .env adalah sumber kebenaran.
        load_dotenv(_ENV_FILE, override=True)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# API keys (gratis semua, sesuai Prinsip #7 — lihat 04_DATA_SOURCES/*)
# ---------------------------------------------------------------------------
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# ---------------------------------------------------------------------------
# Direktori cache (SQLite, lihat cache.py)
# ---------------------------------------------------------------------------
CACHE_DIR = Path(os.environ.get("ALPHAFORGE_CACHE_DIR", str(Path.home() / ".alphaforge_v2_cache")))
CACHE_DB_PATH = CACHE_DIR / "cache.sqlite3"

# ---------------------------------------------------------------------------
# Historical Tracking / Decision Journal (03_LAYER2_SPECS/12_...md)
# ---------------------------------------------------------------------------
# Versi metodologi/formula. WAJIB ikut tersimpan di tiap entri jurnal supaya
# audit di masa depan tidak keliru membandingkan kesimpulan lama dengan formula
# yang sudah berubah (Prinsip #6, 00_Foundation/02_PRINCIPLES.md). Naikkan versi
# ini setiap kali logika reasoning/scoring yang mempengaruhi Output berubah.
METHODOLOGY_VERSION = os.environ.get("ALPHAFORGE_METHODOLOGY_VERSION", "0.1.0")

# DB jurnal dipisah dari cache: cache boleh dihapus/kadaluarsa kapan saja,
# jurnal justru harus persisten untuk audit jangka panjang.
JOURNAL_DIR = Path(os.environ.get("ALPHAFORGE_JOURNAL_DIR", str(Path.home() / ".alphaforge_v2_journal")))
JOURNAL_DB_PATH = JOURNAL_DIR / "journal.sqlite3"

# Ambang gerak harga (%) untuk mengklasifikasikan arah realisasi saat evaluasi.
# Di bawah ini dianggap "flat" (tidak konklusif), bukan naik/turun. Keputusan
# implementasi awal, boleh dikalibrasi.
JOURNAL_FLAT_BAND_PCT = 5.0

# TTL per jenis data (detik). Lihat 04_DATA_SOURCES/05_RATE_LIMIT_CACHING_STRATEGY.md
# — nilai ini adalah keputusan implementasi awal, boleh dikalibrasi ulang.
TTL_SECONDS = {
    "price_history": 60 * 60 * 4,        # 4 jam — harga tidak perlu realtime untuk reasoning ini
    "fundamentals": 60 * 60 * 24,        # 1 hari — laporan keuangan berubah per kuartal
    "ticker_listing": 60 * 60 * 24 * 7,  # 1 minggu — daftar ticker jarang berubah drastis
    "macro_series": 60 * 60 * 12,        # 12 jam — data FRED biasanya bulanan/mingguan
    "institutional": 60 * 60 * 24 * 7,   # 1 minggu — 13F dilaporkan kuartalan
    "news": 60 * 60 * 2,                 # 2 jam
    "sector_etf": 60 * 60 * 4,
}

# ---------------------------------------------------------------------------
# Rate limit / batching (lihat 04_DATA_SOURCES/05_RATE_LIMIT_CACHING_STRATEGY.md)
# ---------------------------------------------------------------------------
YF_BATCH_SIZE = 25
YF_BATCH_DELAY_SECONDS = 1.5
YF_MAX_RETRIES = 3
YF_RETRY_BACKOFF_BASE = 2.0  # detik, dikali 2^attempt

FINNHUB_CALLS_PER_MINUTE = 60
FINNHUB_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Ambang Screening (Layer 2) — persis dari 03_LAYER2_SPECS/01_SCREENING.md
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScreeningThresholds:
    hard_min_market_cap_usd: float = 30_000_000
    hard_min_avg_dollar_volume_20d_usd: float = 300_000
    hard_min_price_usd: float = 0.50
    hard_min_price_history_days: int = 20
    hard_max_quarters_since_last_filing: int = 2  # "2 kuartal terakhir"

    soft_micro_cap_max_usd: float = 300_000_000
    soft_small_cap_max_usd: float = 2_000_000_000
    soft_recent_ipo_max_days: int = 252
    soft_low_liquidity_max_usd: float = 1_000_000


SCREENING = ScreeningThresholds()

# ---------------------------------------------------------------------------
# Sector ETF map — dipakai Sector Rotation & Money Flow proxy
# (02_LAYER1_SPECS/02_SECTOR_ROTATION.md, 03_MONEY_FLOW.md)
# ---------------------------------------------------------------------------
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLC": "Communication Services",
}
BENCHMARK_INDEX_TICKER = "^GSPC"  # S&P 500, dipakai sbg acuan relative performance

# Index utama untuk Market Regime / Market Breadth (01_ARCHITECTURE, LAYER1 specs)
MAIN_INDICES = {
    "sp500": "^GSPC",
    "nasdaq_composite": "^IXIC",
}

# Tickers Layer 1 direct-API (Yahoo Finance)
VIX_TICKER = "^VIX"
DXY_TICKER = "DX-Y.NYB"
GOLD_TICKER = "GC=F"
OIL_TICKER = "CL=F"

# FRED series id yang dipakai (04_DATA_SOURCES/04_MACRO_DATA_SOURCES.md)
FRED_SERIES = {
    "gdp_growth": "A191RL1Q225SBEA",       # Real GDP QoQ, % annualized
    "ism_pmi_proxy": "MANEMP",              # proxy sederhana kalau tidak ada ISM gratis langsung
    "unemployment_rate": "UNRATE",
    "fed_balance_sheet": "WALCL",
    "m2_money_supply": "M2SL",
    "credit_spread_baa10y": "BAA10Y",       # Moody's Baa - 10Y Treasury spread
    "treasury_3m": "DGS3MO",
    "treasury_2y": "DGS2",
    "treasury_10y": "DGS10",
}

NASDAQ_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

REQUEST_TIMEOUT_SECONDS = 20


class DataUnavailableError(RuntimeError):
    """Dilempar ketika sumber data tidak bisa diakses (key hilang, network gagal,
    dsb) — dipakai supaya caller wajib menangani secara eksplisit, bukan diam-diam
    memakai fallback angka palsu."""
