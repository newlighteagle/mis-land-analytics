# Ikhtisar

`mis-land-analytics` adalah alat analisa lahan untuk petani sawit swadaya di Riau, sebagai pelengkap aplikasi MIS (`mis-dashboard`). MIS menyimpan data persil, petani, dan produksi; proyek ini menambahkan lapisan analisa geospasial di atasnya **tanpa menyentuh database produksi** (lihat [01-arsitektur.md](01-arsitektur.md)).

## Prinsip kerja

- **By-request per ID lahan** — analisa tidak berjalan batch untuk semua ±10.950 persil, melainkan dipicu per persil lewat CLI atau dashboard. Skala data (rata-rata 1,55 ha per persil) membuat pendekatan ini cukup dan murah.
- **Modular** — satu modul analisa = satu file di `mla/`. Modul dikerjakan bertahap sesuai roadmap.
- **Hasil selalu tercatat lengkap** — setiap hasil menyimpan metode, versi model, tanggal citra (jika pakai citra), dan parameter, supaya bisa dibandingkan antar-metode dan direproduksi.

## Roadmap modul

| # | Modul | Status |
|---|---|---|
| 1 | Tree counting | **Baseline selesai** ([09-modul-tree-count.md](09-modul-tree-count.md)); deteksi per pohon dari citra menyusul |
| 2 | NDVI monitoring (Sentinel-2) | Belum |
| 3 | Estimasi biomasa/karbon (allometrik + umur tanam) | Belum |
| 4 | Analisa kesehatan (anomali time-series vigor) | Belum |
| 5 | Deteksi HPT (Ganoderma, dll.) | Belum |
| 6 | Analisa/prediksi panen (kalibrasi `tbl_production_record`) | Belum |

Detail rencana per modul di [11-roadmap.md](11-roadmap.md).
