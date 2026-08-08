# API HTTP: `app.py`

FastAPI, dijalankan dengan:

```bash
.venv/bin/uvicorn app:app --reload --port 8008
```

Juga menyajikan dashboard (`GET /` → `static/index.html`, aset di `/static`). Dokumentasi interaktif otomatis tersedia di `http://localhost:8008/docs` (Swagger UI bawaan FastAPI).

## Endpoint

### `GET /api/search?q=<teks>`

Cari persil aktif berdasarkan potongan `parcel_id` **atau** nama petani (ILIKE, case-insensitive). Kembalikan maksimal 20 hasil, terurut `parcel_id`. Query < 3 karakter langsung mengembalikan `[]` (tanpa menyentuh database).

```json
[
  { "id": "cmrsro65k...", "parcel_id": "TJP.0001.A.14.06.06.2018",
    "area": 2.12, "crop_type": null, "farmer_name": "Agus Nugroho Budiarto" }
]
```

### `GET /api/parcel/{pk}`

Detail satu persil sebagai **GeoJSON Feature** — `geometry` dari kolom jsonb prod, atribut lain di `properties` (termasuk `farmer_name`, `farmer_group_name`). `{pk}` harus primary key (`id`), bukan `parcel_id`. `404` jika tidak ada / tidak aktif.

### `GET /api/parcel/{pk}/results`

Semua hasil analisa persil dari `analytics.tree_count`, terurut `computed_at` menurun. Array kosong jika belum pernah dianalisa.

### `POST /api/parcel/{pk}/analyze/tree-count`

Jalankan estimasi baseline dan simpan hasilnya (upsert). Body:

```json
{ "sph": 128 }
```

`sph` opsional (`null`/tidak dikirim → default 136). Respons = baris hasil (format sama dengan output CLI, lihat [06-cli-analyze.md](06-cli-analyze.md)). `404` jika persil tidak ditemukan.

## Catatan desain

- Endpoint membuka koneksi per request via context manager (`with prod_conn() ...`) — tidak ada connection pool; cukup untuk pemakaian lokal satu pengguna.
- `{pk}` konsisten memakai primary key karena `parcel_id` bisa ganda (lihat [04-database-mis-prod.md](04-database-mis-prod.md)); pencarian ke PK terjadi di `/api/search`.
- Tidak ada autentikasi — server hanya untuk `localhost`, jangan diekspos ke jaringan.
