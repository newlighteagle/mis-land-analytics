# API HTTP: `app.py`

FastAPI, dijalankan dengan:

```bash
.venv/bin/uvicorn app:app --reload --port 8008
```

Juga menyajikan dashboard (`GET /` → `static/index.html`, aset di `/static`). Dokumentasi interaktif otomatis tersedia di `http://localhost:8008/docs` (Swagger UI bawaan FastAPI).

## Endpoint

### `GET /api/search?q=<teks>&status=<all|new|done>`

Cari persil aktif berdasarkan potongan `parcel_id` **atau** nama petani (ILIKE, case-insensitive). Kembalikan maksimal 20 hasil, terurut `parcel_id`. Query < 3 karakter langsung mengembalikan `[]` (tanpa menyentuh database).

Parameter `status` (default `all`) menyaring berdasarkan ada/tidaknya hasil analisa:

| Nilai | Arti |
|---|---|
| `all` | Semua persil aktif |
| `new` | **Belum pernah** dianalisa |
| `done` | Sudah pernah dianalisa |

Filternya lintas-database: daftar PK yang sudah dianalisa diambil dari `mis_analytics`, lalu dikirim sebagai parameter array ke query `mis-prod` (`p.id = ANY(%s)`) — tidak ada join lintas-database.

```json
[
  { "id": "cmrsro65k...", "parcel_id": "TJP.0001.A.14.06.06.2018",
    "area": 2.12, "crop_type": null, "farmer_name": "Agus Nugroho Budiarto" }
]
```

### `GET /api/groups`

Daftar lembaga tani beserta progres cakupan analisa — sumber tingkat 1 di dashboard. Petani tanpa kelompok dikumpulkan di bawah id sentinel `_none`.

```json
[
  { "id": "cm...", "name": "KUD Intan Makmur", "total": 317,
    "analyzed": 2, "pct": 0.6, "total_area": 619.1 }
]
```

Terurut: yang paling banyak dianalisa dulu, lalu menurut jumlah lahan.

### `GET /api/group/{gid}/parcels?status=<done|new|all>`

Lahan dalam satu lembaga (maks. 500), default `status=done`. Untuk `done`, tiap baris diperkaya ringkasan hasil (`trees_grid`, `sph_grid`, `trees_baseline`, `last_computed`) dari DB lokal.

### `GET /api/analyzed`

Semua persil yang sudah punya hasil analisa, terurut waktu analisa terbaru. Dipakai dashboard untuk mengisi select box mode *"Sudah dianalisa"* — dikirim sekaligus (jumlahnya kecil) lalu difilter di klien, jadi tidak ada round-trip per ketikan.

```json
[
  { "id": "cmrsro65k...", "parcel_id": "TJP.0001.A.14.06.06.2018",
    "farmer_name": "Agus Nugroho Budiarto", "area": 2.12,
    "n_methods": 1, "last_computed": "2026-08-08T14:13:38+07:00" }
]
```

### `GET /api/analyzed/geojson?group=<gid>`

Poligon lahan teranalisa sebagai GeoJSON FeatureCollection, dipakai dashboard sebagai layer ikhtisar biru. `group` opsional membatasi ke satu lembaga (`_none` untuk tanpa kelompok); `properties` tiap feature berisi ringkasan yang sama dengan `/api/analyzed`.

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

### `POST /api/parcel/{pk}/analyze/tree-grid`

Ukur kisi tanam dari citra, simpan posisi pohon, dan upsert agregat (`method='grid_fit'`). Tanpa body. Respons = baris hasil; `params` berisi jarak tanam, arah baris, SPH terukur, polaritas mahkota, dan `warnings`. Detail metode di [13-modul-tree-grid.md](13-modul-tree-grid.md).

`422` bila citra tidak tersedia atau pola tanam tidak terbaca (pesan di `detail`), `404` bila persil tidak ada.

### `GET /api/parcel/{pk}/trees?method=grid_fit`

Titik pohon sebagai **GeoJSON FeatureCollection**, dipakai dashboard sebagai layer titik. Kosong bila persil belum dipetakan.

## Catatan desain

- Endpoint membuka koneksi per request via context manager (`with prod_conn() ...`) — tidak ada connection pool; cukup untuk pemakaian lokal satu pengguna.
- `{pk}` konsisten memakai primary key karena `parcel_id` bisa ganda (lihat [04-database-mis-prod.md](04-database-mis-prod.md)); pencarian ke PK terjadi di `/api/search`.
- Tidak ada autentikasi — server hanya untuk `localhost`, jangan diekspos ke jaringan.
