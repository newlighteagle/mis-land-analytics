# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`mis-land-analytics` — analisa lahan petani sawit swadaya (Riau) untuk MIS. Roadmap modular, dikerjakan bertahap:

1. **Tree counting** (modul pertama, sedang dikerjakan)
2. NDVI monitoring (Sentinel-2)
3. Estimasi biomasa/karbon (allometrik + umur tanam)
4. Analisa kesehatan (anomali time-series vigor)
5. Deteksi HPT (Ganoderma, dll.)
6. Analisa/prediksi panen (kalibrasi dengan `tbl_production_record`)

## Commands

```bash
.venv/bin/pip install -r requirements.txt          # setup (venv sudah ada)
.venv/bin/python analyze.py tree-count --parcel-id <ID> [--sph 128]
.venv/bin/uvicorn app:app --reload --port 8008     # dashboard: http://localhost:8008
/opt/homebrew/opt/postgresql@17/bin/psql mis_analytics -f sql/001_init.sql  # init/migrasi schema hasil
```

## Arsitektur

- **Dua database**: `mis-prod` (sumber data persil/petani, **READ-ONLY** — `mla/db.py` memaksa `default_transaction_read_only`) dan `mis_analytics` lokal (hasil analisa, schema `analytics`, dilayani Postgres.app di port 5432, PostGIS aktif).
- **By-request per ID lahan**: semua analisa dipicu per persil via CLI (`analyze.py`) atau dashboard (`app.py` FastAPI + `static/index.html` MapLibre, basemap Esri World Imagery). Alur dashboard: cari ID lahan/nama petani → pilih → peta + panel analisa.
- **Modul analisa** di `mla/` — satu file per modul. `tree_count.py` berisi baseline (SPH × luas, SPH bisa custom per request); hasil di-upsert ke `analytics.tree_count` dengan unique `(land_parcel_pk, method)`.
- Kredensial di `.env` (tidak di-commit): `PROD_DATABASE_URL`, `LOCAL_DATABASE_URL`, `GEE_PROJECT`.
- GEE pakai akun pribadi user (`sofyan.agus18@gmail.com`), belum diautentikasi.

## Database

PostgreSQL + PostGIS di `localhost:1234`, database `mis-prod` (koneksi via `DATABASE_URL`, jangan hardcode credentials). Skema dikelola Prisma oleh aplikasi MIS terpisah (`mis-dashboard`).

Tabel kunci:
- `tbl_land_parcel` — ±10.950 persil aktif, ±6.840 petani, rata-rata 1,55 ha. Geometri poligon GeoJSON di kolom `geometry` (jsonb, WGS84). Kolom `area` (ha) akurat (tervalidasi vs luas geodesik). `planting_year` **kosong di semua baris** (tahun tersirat di ujung `parcel_id` dipakai sebagai hint). `crop_type` kosong di ±6.800 baris. `parcel_id` tidak 100% unik (±20 duplikat aktif) — resolve via PK `id`.
- `tbl_farmer`, `tbl_farmer_group` — pemilik persil.
- `tbl_production_record` — data produksi aktual per persil (ground truth untuk modul panen).

`psql` tidak ada di PATH — pakai `/opt/homebrew/opt/libpq/bin/psql`.

## Keputusan desain

- Hasil tree counting disimpan per pohon (tabel titik per pohon), bukan hanya agregat per persil — modul kesehatan/HPT butuh level pohon.
- Semua hasil analisa dicatat dengan tanggal citra + metode + versi model.
- Pendekatan tree counting: baseline estimasi kerapatan (SPH standar × luas, koreksi umur) untuk semua persil, lalu deteksi per pohon dari citra resolusi tinggi pada sampel.
