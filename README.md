# alphaforge-core-v2

Implementasi kode untuk spec `alphaforge-v2` (dokumen ada di `00_Foundation/`,
`01_ARCHITECTURE/`, `02_LAYER1_SPECS/`, `03_LAYER2_SPECS/`, `04_DATA_SOURCES/`
dari repo dokumentasi aslinya).

## Cakupan yang sudah diimplementasikan

**Layer 1 — Market Context Engine (12/12 komponen):**
Business Cycle Stage, Sector Rotation, Money Flow, Liquidity Conditions, Yield
Curve, Market Breadth, Volatility (VIX), Market Regime, Macro Calendar,
Currency/DXY, Commodity Signals, Market Sentiment — semua di `alphaforge_core/layer1/`,
digabung oleh `market_context_engine.py` jadi satu Market Context Package.

**Layer 2 — Stock Analysis Engine (end-to-end untuk 1 ticker):**
Screening → Evidence → Knowledge → Confidence + Peer Comparison →
Risk/Red-Flag Check → [Multibagger, Quality/Compound, Speculative] →
Aggregator. Orkestrasinya ada di `alphaforge_core/layer2/pipeline.py`.

## Belum diimplementasikan (diakui eksplisit di spec sebagai boleh menyusul)
- Historical Tracking / Decision Journal (`03_LAYER2_SPECS/12_...md` menyebut ini
  eksplisit sebagai kandidat v2.1).
- `screen_universe()` untuk full market-wide screening ada, tapi belum dites
  terhadap ribuan ticker riil (butuh koneksi network yang tidak tersedia di
  sandbox pembuatan kode ini).
- **`institutional_ownership_detail`** (siapa institusi pegang berapa saham):
  Finnhub `institutional/ownership` ternyata sekarang endpoint premium-only
  (bukan gratis seperti asumsi awal di spec dokumentasi) -- dapat 403 Forbidden
  di free tier. Alternatif gratis (parsing bulk dataset 13F resmi dari SEC
  EDGAR, cross-match CUSIP) butuh effort jauh lebih besar (unduh dataset
  kuartalan ratusan MB) -- sengaja ditunda, field ini tetap `missing` secara
  eksplisit. `institutional_ownership_pct` (persentase saja, TANPA rincian per
  institusi) tetap tersedia dari Yahoo Finance.
- Market Breadth (Layer 1) belum jalan out-of-the-box karena butuh daftar
  konstituen index (S&P 500/NASDAQ) yang belum disuplai -- lihat parameter
  `breadth_constituents` di `market_context_engine.build_market_context_package()`.

## Update sejak rilis awal
- **Fixed**: bug `price_return_1y_pct` selalu `missing` -- penyebabnya Evidence
  cuma nyimpen 252 hari data harga, padahal butuh buffer 253+ hari untuk
  lookback 1 tahun. Sekarang Evidence nyimpen histori penuh (~5 tahun), dan
  `price_return_3y_pct`/`price_return_5y_pct` juga sudah ditambahkan.
- **Added**: `revenue_cagr_3y_pct`/`5y_pct` sekarang fallback ke data finansial
  TAHUNAN (`annual_financials`) kalau data kuartalan tidak cukup panjang
  (biasanya Yahoo Finance cuma kasih 4-5 kuartal terakhir).
- **Added**: `recent_insider_transactions` sekarang terisi dari Yahoo Finance
  (`Ticker.insider_transactions`, gratis) -- disimpan sebagai fakta murni
  (tanggal/nama/jenis transaksi/jumlah), tanpa interpretasi.
- **Added**: `business_model_category` sekarang terisi dari heuristik
  keyword sektor/industri (ditandai eksplisit `"method": "heuristic_keyword_based"`
  supaya tidak dikira klasifikasi otoritatif).
- **Fixed**: bug mixed-timezone saat membaca cache harga (`pd.to_datetime` perlu
  `utc=True`).
- **Fixed**: `.env` sekarang di-load dengan `override=True` supaya API key di
  file selalu menang dibanding env var lama yang kebetulan nyangkut di sesi
  shell.
- **Fixed**: Finnhub 403 (endpoint premium) sekarang langsung gagal dengan
  pesan jelas, bukan retry sia-sia 3x dengan backoff.

## PENTING: sandbox pembuatan kode ini tidak punya akses network ke API finance

Semua logika sudah ditulis dan **diuji dengan data sintetis** (lihat `tests/`),
tapi **belum pernah dijalankan dengan panggilan live** ke Yahoo Finance / FRED /
Finnhub / NASDAQ Trader, karena sandbox ini hanya mengizinkan domain paket
(pypi, npm, github, dst), bukan domain data finansial. Jalankan di lingkungan
kamu sendiri (laptop/server dengan akses internet biasa) untuk tes end-to-end
sungguhan.

## Setup

```bash
cd alphaforge-core-v2
python3 -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# isi FRED_API_KEY (gratis, https://fred.stlouisfed.org/docs/api/api_key.html)
# isi FINNHUB_API_KEY (gratis, https://finnhub.io/register)
export $(grep -v '^#' .env | xargs)   # atau load .env dengan python-dotenv
```

## Cara pakai

```bash
# Hitung Market Context Package (Layer 1) saja
python -m alphaforge_core.cli context --pretty

# Analisa 1 saham end-to-end (Layer 1 + Layer 2 penuh)
python -m alphaforge_core.cli analyze AAPL --pretty

# Dengan peer group untuk Peer/Relative Comparison
python -m alphaforge_core.cli analyze AAPL --peers MSFT,GOOGL,META --pretty
```

Atau dari Python langsung:

```python
from alphaforge_core.layer1.market_context_engine import build_market_context_package
from alphaforge_core.layer2.pipeline import analyze_single_ticker

market_context = build_market_context_package()   # hitung sekali per sesi
result = analyze_single_ticker("AAPL", market_context, peer_tickers=["MSFT", "GOOGL"])
print(result["views"]["multibagger"])
print(result["views"]["quality_compound"])
print(result["views"]["speculative"])
```

## Menjalankan tes (tidak butuh network / API key)

```bash
python3 tests/test_layer1_logic.py
python3 tests/test_layer2_logic.py
```

Kedua file ini memvalidasi logika murni (klasifikasi yield curve, market
regime, derivasi Knowledge, confidence scoring, risk/red-flag detection, dan
independensi tiga modul reasoning) memakai data sintetis lewat monkeypatching
— jadi bisa jalan di sandbox mana pun tanpa API key.

## Struktur

```
alphaforge_core/
  config.py                  — API keys, ambang Screening, TTL cache, dll
  cache.py                   — TTL cache berbasis SQLite
  providers/
    yahoo_finance.py         — harga, fundamental, VIX, DXY, commodity, sector ETF
    fred.py                  — yield curve, GDP, unemployment, M2, Fed balance sheet
    finnhub.py                — institutional ownership, company news, filings
    market_listings.py       — universe ticker NASDAQ + NYSE
  layer1/                    — 12 komponen Market Context Engine
    market_context_engine.py — orkestrator, hasil: Market Context Package
  layer2/
    screening.py             — Hard Exclude / Soft Flag
    evidence.py               — pengumpulan fakta mentah per ticker
    knowledge.py               — fakta turunan (BUKAN penilaian kualitatif)
    confidence.py              — Confidence/Data Quality Score
    peer_comparison.py         — perbandingan ke peer group
    risk_redflag.py            — gerbang deteksi red flag
    catalyst_tracking.py       — identifikasi katalis mendatang
    modules/
      multibagger.py
      quality_compound.py
      speculative.py
    aggregator.py               — gabungkan 3 pandangan berdampingan
    pipeline.py                — orkestrator end-to-end 1 ticker
  cli.py                      — command-line interface
tests/
  test_layer1_logic.py
  test_layer2_logic.py
```

## Catatan desain penting (mengikuti Prinsip di `00_Foundation/02_PRINCIPLES.md`)

- **Evidence sebelum Knowledge**: `knowledge.py` hanya menghitung dari
  `Evidence`, tidak pernah menarik data baru sendiri.
- **Knowledge = fakta turunan, bukan penilaian**: setiap field numerik/kategori
  berbasis ambang eksplisit; kata sifat evaluatif ("bagus"/"berisiko") hanya
  muncul di tiga modul reasoning.
- **Data hilang ditandai `missing`, tidak pernah diestimasi** — lihat
  `_missing()` di `knowledge.py`.
- **Tiga modul reasoning independen**: masing-masing punya fungsi `analyze()`
  sendiri, menerima Knowledge + Market Context yang sama tapi tidak saling
  memanggil atau saling mempengaruhi. `aggregator.py` sengaja tidak
  menggabungkan jadi satu skor.
- **Risk/Red-Flag sebagai gerbang, bukan rata-rata**: `risk_redflag.py`
  menghasilkan flag yang ditempelkan ke semua modul, bukan salah satu faktor
  yang di-average.
- **Confidence eksplisit**: setiap output Aggregator membawa `confidence`
  (score + label + faktor penyusun), bukan disembunyikan.
- Komponen Layer 1 yang termasuk "Derived/Approximated Data" (lihat Glosarium)
  ditandai `"kind": "derived_approximated"` di setiap reading — bukan
  disamarkan seolah sekuat data langsung seperti VIX/DXY.

## Yang masih perlu dikalibrasi (bukan bug, memang belum final)

Spec sendiri menyebut beberapa hal ini "didiskusikan lebih lanjut mendekati
implementasi" — jadi nilai berikut adalah keputusan implementasi awal, bukan
angka final:
- Ambang klasifikasi Business Cycle Stage, Liquidity Conditions, Market
  Sentiment (lihat komentar di masing-masing file `layer1/*.py`).
- Bobot & kriteria skor di tiga modul reasoning (`layer2/modules/*.py`) — spec
  eksplisit menyatakan ini "didiskusikan terpisah sebelum implementasi".
- Ambang funnel Screening ($30jt market cap, $300rb volume) perlu divalidasi
  terhadap hasil funnel riil saat `screen_universe()` dijalankan penuh.
