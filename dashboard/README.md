# Dashboard AlphaForge v2

Dashboard web statis (satu file HTML, tanpa server, tanpa dependency eksternal)
untuk melihat output AlphaForge v2 secara visual — bisa dibuka di HP maupun
desktop.

## 🔗 Buka versi online

**Publik (GitHub Pages, bisa dibuka di HP tanpa login):**
**https://arinurrahman913.github.io/alphaforge-core-v2/**

Dilayani otomatis dari `dashboard.html` lewat GitHub Actions
(`.github/workflows/deploy-pages.yml`) setiap ada push ke `main`. Aktif setelah
Pages dinyalakan sekali di **Settings › Pages › Source: GitHub Actions**.

_Alternatif:_ buka file `dashboard.html` langsung di browser (offline), atau
lihat artifact privat di claude.ai (butuh login akun pemilik).

## Apa yang ditampilkan

- **Market Context (Layer 1)** — 12 komponen, dengan badge `langsung` vs
  `perkiraan` (derived/approximated, sesuai Prinsip #5). Market Breadth tampil
  "belum tersedia" karena butuh daftar konstituen index.
- **Analisa Saham (Layer 2)** — per ticker: Confidence meter, Risk/Red-Flag
  badge + daftar flag, dan **tiga lensa independen berdampingan** (Multibagger,
  Quality/Compound, Speculative) — masing-masing dengan sinyal, skor, dan alasan.
  Tidak digabung jadi satu verdict (Prinsip #3).
- **Decision Journal** — audit historis: harga saat analisa → harga sekarang,
  return terealisasi, dan keselarasan tiap lensa (`aligned`/`misaligned`/
  `inconclusive`) — deskriptif, bukan vonis benar/salah (Prinsip #6 & #10).

## Regenerate

Dashboard di-render dari output pipeline yang ASLI (fungsi Layer 2 yang sama
persis dengan CLI), memakai **data perusahaan sintetis** supaya reproducible
tanpa akses API pasar live. Untuk membuat ulang:

```bash
python dashboard/generate.py
# menghasilkan dashboard/dashboard.html + dashboard/sample_data.json
```

## Data live (bukan contoh)

Dashboard ini pakai data contoh karena sandbox pembuatannya tidak punya akses
ke Yahoo/FRED/Finnhub. Untuk analisa nyata, jalankan CLI di lingkungan dengan
internet:

```bash
python -m alphaforge_core.cli analyze AAPL --peers MSFT,GOOGL --json > out.json
```

Struktur `out.json` sama dengan yang dirender di sini — tinggal diadaptasi jadi
input `generate.py` kalau ingin dashboard dari data live.
