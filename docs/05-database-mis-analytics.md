# Database hasil: `mis_analytics`

PostgreSQL lokal (Postgres.app, `localhost:5432`), PostGIS aktif. Semua hasil analisa disimpan di schema **`analytics`**. Migrasi: file SQL bernomor di `sql/` (saat ini baru `001_init.sql`), dijalankan manual:

```bash
/opt/homebrew/opt/postgresql@17/bin/psql mis_analytics -f sql/001_init.sql
```

Semua statement `IF NOT EXISTS` — aman dijalankan ulang. Belum ada tabel pelacak migrasi; jika kelak schema berubah, tambahkan file `002_*.sql` baru, jangan edit `001` (yang sudah dijalankan di mesin lain tidak akan tereksekusi ulang).

## Tabel `analytics.tree_count`

Satu baris = satu hasil tree count per persil per metode (agregat; tabel titik per pohon menyusul saat modul deteksi dibuat — lihat [10-keputusan-desain.md](10-keputusan-desain.md)).

| Kolom | Tipe | Catatan |
|---|---|---|
| `id` | `bigserial` PK | |
| `land_parcel_pk` | `text` | = `tbl_land_parcel.id` di mis-prod (cuid). Kunci join utama. |
| `parcel_id` | `text` | ID lahan, denormalisasi untuk kemudahan query/tampilan. Ada index. |
| `method` | `text` | `'baseline_density'` sekarang; `'detection_esri'` dll. menyusul. |
| `model_version` | `text` | Mis. `baseline_density/v1`. Naikkan setiap logika berubah. |
| `image_date` | `date`, nullable | Tanggal citra yang dipakai. `NULL` untuk baseline (tanpa citra). |
| `tree_count` | `integer` | Hasil estimasi/deteksi. |
| `sph_used` | `numeric`, nullable | Kerapatan pohon/ha yang dipakai (hanya relevan untuk baseline). |
| `area_ha` | `numeric` | Luas persil saat dihitung (snapshot, bukan referensi ke prod). |
| `confidence` | `text` | `'low' | 'medium' | 'high'`. Baseline selalu `'low'`. |
| `params` | `jsonb` | Parameter & konteks perhitungan (lihat [09-modul-tree-count.md](09-modul-tree-count.md)). |
| `computed_at` | `timestamptz` | Diperbarui setiap upsert. |

**Constraint kunci**: `UNIQUE (land_parcel_pk, method)` — satu persil hanya punya **satu hasil terkini per metode**. Menjalankan ulang analisa yang sama = `ON CONFLICT ... DO UPDATE` (menimpa), bukan menambah baris. Konsekuensinya tidak ada riwayat antar-run untuk metode yang sama; riwayat yang ditampilkan dashboard adalah riwayat **antar-metode**.

## Tabel `analytics.tree` (`sql/002_tree_points.sql`)

Titik per pohon hasil deteksi citra — dibutuhkan modul kesehatan/HPT yang bekerja di level pohon.

| Kolom | Tipe | Catatan |
|---|---|---|
| `id` | `bigserial` PK | |
| `land_parcel_pk` | `text` | = `tbl_land_parcel.id` |
| `method` | `text` | Selaras dengan `method` di `tree_count` (mis. `detection_esri`) |
| `geom` | `geometry(Point, 4326)` | Posisi pohon, index GiST |
| `score` | `real` | Kekuatan puncak deteksi, dinormalisasi 0–1 dalam persil |
| `detected_at` | `timestamptz` | |

Pola tulisnya **delete + insert**: satu run deteksi mengganti seluruh titik persil untuk method yang sama, konsisten dengan upsert satu-baris di `tree_count`.

Saat ini tabel kosong — hasil uji deteksi dihapus karena citranya belum memadai (lihat [12-modul-tree-detect.md](12-modul-tree-detect.md)).

## Konvensi untuk tabel modul berikutnya

- Selalu simpan `land_parcel_pk` + `parcel_id` (denormalisasi) + `method` + `model_version` + `image_date` + `params jsonb` + `computed_at`.
- Hasil level pohon: tabel titik terpisah (mis. `analytics.tree`) dengan FK ke baris agregat, geometri PostGIS `Point`.
