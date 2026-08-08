# Setup

Prasyarat: macOS, Python 3.11+ (venv sudah ada di `.venv/`), Postgres.app (port 5432) untuk database lokal, dan akses jaringan ke `mis-prod` (port 1234).

## 1. Dependensi Python

```bash
.venv/bin/pip install -r requirements.txt
```

Isi `requirements.txt`: `psycopg[binary]`, `python-dotenv`, `fastapi`, `uvicorn`.

## 2. Konfigurasi `.env`

Buat/isi `.env` di root proyek (tidak di-commit). Daftar variabel dan formatnya di [03-konfigurasi-env.md](03-konfigurasi-env.md).

## 3. Inisialisasi database hasil

Buat database `mis_analytics` (sekali saja) lalu jalankan migrasi schema:

```bash
/opt/homebrew/opt/postgresql@17/bin/createdb mis_analytics   # jika belum ada
/opt/homebrew/opt/postgresql@17/bin/psql mis_analytics -f sql/001_init.sql
/opt/homebrew/opt/postgresql@17/bin/psql mis_analytics -f sql/002_tree_points.sql
```

Skrip SQL idempotent (`CREATE ... IF NOT EXISTS`) — aman dijalankan ulang. Catatan: `psql` tidak ada di PATH; pakai path Homebrew di atas, atau `/opt/homebrew/opt/libpq/bin/psql` untuk koneksi ke `mis-prod`.

## 4. Verifikasi

```bash
# CLI end-to-end (baca prod, tulis lokal):
.venv/bin/python analyze.py tree-count --parcel-id TJP.0001.A.14.06.06.2018

# Dashboard:
.venv/bin/uvicorn app:app --reload --port 8008
# lalu buka http://localhost:8008
```

Jika uvicorn gagal dengan `[Errno 48] address already in use`, berarti instance lama masih jalan — cek dengan `lsof -nP -iTCP:8008 -sTCP:LISTEN`, dan pakai instance itu atau matikan dulu (`kill <PID>`).

## Belum dikonfigurasi

- **Google Earth Engine** — dibutuhkan modul NDVI dan seterusnya. Paket `earthengine-api` belum ada di `requirements.txt`; autentikasi memakai akun pribadi (`sofyan.agus18@gmail.com`) belum dilakukan. Variabel `GEE_PROJECT` sudah disiapkan di `.env`.
