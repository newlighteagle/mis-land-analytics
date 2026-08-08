# Database sumber: `mis-prod`

PostgreSQL + PostGIS di `localhost:1234`, database `mis-prod`. Schema dikelola **Prisma** oleh aplikasi MIS terpisah (`mis-dashboard`) — proyek ini hanya **membaca** (penegakan di `mla/db.py::prod_conn()`, lihat [01-arsitektur.md](01-arsitektur.md)).

Akses manual: `/opt/homebrew/opt/libpq/bin/psql` (psql tidak ada di PATH).

## Tabel kunci

### `tbl_land_parcel` — persil lahan

±10.950 persil aktif milik ±6.840 petani, rata-rata 1,55 ha.

| Kolom | Catatan |
|---|---|
| `id` | Primary key (cuid, text). **Selalu pakai ini** untuk resolve persil secara pasti. |
| `parcel_id` | ID lahan (business key), mis. `TJP.0001.A.14.06.06.2018`. **Tidak 100% unik** — lihat caveat. |
| `geometry` | Poligon GeoJSON di kolom `jsonb`, WGS84 (bukan tipe PostGIS `geometry`). |
| `area` | Luas dalam hektare. **Akurat** — sudah tervalidasi terhadap luas geodesik dari geometri. |
| `planting_year` | **Kosong di semua baris.** Tahun tanam diperkirakan dari ujung `parcel_id` (lihat caveat). |
| `crop_type` | Kosong di ±6.800 baris. |
| `is_active` | Semua query proyek ini memfilter `is_active = true`. |
| `farmer_id` | FK ke `tbl_farmer`. |
| `species`, `land_status`, `blok`, `is_psr`, `notes` | Atribut tambahan, ditampilkan di dashboard. |

### `tbl_farmer`, `tbl_farmer_group`

Pemilik persil dan kelompok taninya. Dipakai untuk pencarian by nama petani dan tampilan atribut.

### `tbl_production_record`

Data produksi aktual per persil — ground truth untuk modul analisa/prediksi panen (modul #6, belum dikerjakan).

## Caveat data (penting)

1. **`parcel_id` ganda** — ±20 duplikat aktif. Kode melempar `AmbiguousParcel` jika ID lahan cocok >1 baris; resolve dengan memakai PK `id`. Detailnya di [09-modul-tree-count.md](09-modul-tree-count.md).
2. **`planting_year` kosong semua** — tahun 4 digit di ujung `parcel_id` (mis. `...2018`) dipakai sebagai *hint*, disimpan di `params.year_hint_from_parcel_id` pada hasil analisa. Ini heuristik, bukan data tervalidasi.
3. **`crop_type` mayoritas kosong** — jangan pakai sebagai filter wajib; tampilkan `-` jika null.
4. **Geometri berupa jsonb** — untuk operasi spasial di sisi analisa, parse GeoJSON-nya sendiri (atau cast ke PostGIS di DB lokal); jangan berharap fungsi PostGIS langsung bekerja di kolom ini.
