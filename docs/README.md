# Dokumentasi mis-land-analytics

Dokumentasi dipecah atomic — satu file, satu topik. Mulai dari ikhtisar, lalu ikuti sesuai kebutuhan.

## Daftar isi

| File | Topik |
|---|---|
| [00-ikhtisar.md](00-ikhtisar.md) | Apa itu proyek ini, tujuan, dan roadmap modul |
| [01-arsitektur.md](01-arsitektur.md) | Arsitektur dua database & alur by-request |
| [02-setup.md](02-setup.md) | Instalasi dari nol sampai jalan |
| [03-konfigurasi-env.md](03-konfigurasi-env.md) | Variabel lingkungan di `.env` |
| [04-database-mis-prod.md](04-database-mis-prod.md) | Database sumber `mis-prod` (read-only) & caveat datanya |
| [05-database-mis-analytics.md](05-database-mis-analytics.md) | Database hasil `mis_analytics` & schema `analytics` |
| [06-cli-analyze.md](06-cli-analyze.md) | CLI `analyze.py` |
| [07-api.md](07-api.md) | Endpoint HTTP FastAPI (`app.py`) |
| [08-dashboard.md](08-dashboard.md) | Dashboard peta (`static/index.html`) |
| [09-modul-tree-count.md](09-modul-tree-count.md) | Modul tree counting: metode baseline |
| [10-keputusan-desain.md](10-keputusan-desain.md) | Keputusan desain & alasannya |
| [11-roadmap.md](11-roadmap.md) | Rencana modul berikutnya |

## Peta file kode

```
analyze.py            CLI entry point
app.py                FastAPI (API + serve dashboard)
mla/db.py             Koneksi database (prod read-only, lokal)
mla/tree_count.py     Modul analisa #1: tree counting
sql/001_init.sql      Schema hasil analisa (mis_analytics)
static/index.html     Dashboard MapLibre (satu file, tanpa build step)
```
