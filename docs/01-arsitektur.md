# Arsitektur

## Dua database, satu arah

```
┌─────────────────┐   baca (read-only)   ┌──────────────────────┐
│    mis-prod     │ ───────────────────▶ │  mis-land-analytics  │
│ (persil, petani,│                      │  (CLI / FastAPI)     │
│  produksi)      │                      └──────────┬───────────┘
└─────────────────┘                                 │ tulis hasil
   localhost:1234                                   ▼
   dikelola Prisma                        ┌──────────────────┐
   oleh mis-dashboard                     │  mis_analytics   │
                                          │ schema analytics │
                                          └──────────────────┘
                                            localhost:5432
                                            (Postgres.app, PostGIS)
```

- **`mis-prod`** — database produksi aplikasi MIS. Proyek ini **tidak pernah menulis** ke sana. Penegakan di level koneksi: `mla/db.py::prod_conn()` menjalankan `SET default_transaction_read_only = on` segera setelah connect, sehingga `INSERT`/`UPDATE`/`DELETE` apa pun lewat koneksi itu gagal dengan error. Detail isi database di [04-database-mis-prod.md](04-database-mis-prod.md).
- **`mis_analytics`** — database lokal untuk hasil analisa, schema `analytics`, dilayani Postgres.app di port 5432, PostGIS aktif. Detail schema di [05-database-mis-analytics.md](05-database-mis-analytics.md).

Pemisahan ini disengaja: schema `mis-prod` dikelola Prisma oleh aplikasi terpisah (`mis-dashboard`), jadi menambah tabel di sana akan bentrok dengan migrasi Prisma.

## Alur by-request

Semua analisa dipicu per persil, bukan batch:

```
pengguna ──▶ CLI (analyze.py)  ─┐
                                ├─▶ mla/<modul>.py ──▶ baca mis-prod
pengguna ──▶ dashboard (app.py)─┘         │
                                          └─▶ upsert hasil ke mis_analytics
```

1. Persil di-resolve dari `parcel_id` (ID lahan) atau primary key — lihat penanganan ID ganda di [09-modul-tree-count.md](09-modul-tree-count.md).
2. Modul menghitung dan meng-**upsert** hasil (unique per `(land_parcel_pk, method)`), jadi menjalankan ulang analisa yang sama menimpa hasil lama, bukan menumpuk.
3. Dashboard/CLI membaca kembali hasil dari `mis_analytics`.

## Komponen

| Komponen | File | Peran |
|---|---|---|
| Koneksi DB | `mla/db.py` | `prod_conn()` (read-only) & `local_conn()` |
| Modul analisa | `mla/tree_count.py` (dst.) | Satu file per modul; logika hitung + simpan |
| CLI | `analyze.py` | Entry point per modul via subcommand |
| API + server | `app.py` | FastAPI; juga menyajikan dashboard statis |
| Dashboard | `static/index.html` | Satu file HTML+JS, MapLibre, tanpa build step |
