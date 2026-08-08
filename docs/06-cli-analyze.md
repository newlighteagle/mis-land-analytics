# CLI: `analyze.py`

Entry point analisa per persil dari terminal. Satu subcommand per modul.

## Pemakaian

```bash
# Estimasi baseline dengan SPH default (136 pohon/ha):
.venv/bin/python analyze.py tree-count --parcel-id TJP.0001.A.14.06.06.2018

# Override kerapatan (mis. kebun rapat 128 pohon/ha):
.venv/bin/python analyze.py tree-count --parcel-id TJP.0001.A.14.06.06.2018 --sph 128

# Pakai primary key (wajib jika parcel_id ganda):
.venv/bin/python analyze.py tree-count --parcel-id cmrsro65k00ma4c678cews26p
```

## Argumen `tree-count`

| Argumen | Wajib | Arti |
|---|---|---|
| `--parcel-id` | Ya | ID lahan (`parcel_id`) **atau** primary key (`id`) dari `tbl_land_parcel`. Keduanya dicoba sekaligus. |
| `--sph` | Tidak | Kerapatan pohon/ha. Default 136 (lihat [09-modul-tree-count.md](09-modul-tree-count.md)). |

## Output

JSON baris hasil (setelah di-upsert ke `analytics.tree_count`), contoh:

```json
{
  "id": 1,
  "land_parcel_pk": "cmrsro65k00ma4c678cews26p",
  "parcel_id": "TJP.0001.A.14.06.06.2018",
  "method": "baseline_density",
  "model_version": "baseline_density/v1",
  "image_date": null,
  "tree_count": 288,
  "sph_used": 136.0,
  "area_ha": 2.12,
  "confidence": "low",
  "params": {
    "sph_source": "default",
    "year_hint_from_parcel_id": 2018,
    "crop_type": null,
    "is_psr": false
  },
  "computed_at": "2026-08-08T14:13:00+07:00"
}
```

## Subcommand `tree-grid`

```bash
.venv/bin/python analyze.py tree-grid --parcel-id ITM.0106.A.14.06.06.2017
```

Ukur kisi tanam dari citra, simpan posisi pohon ke `analytics.tree`, dan upsert agregat dengan `method='grid_fit'`. Ini metode yang dipakai dashboard untuk layer titik pohon — lihat [13-modul-tree-grid.md](13-modul-tree-grid.md). Keluar dengan pesan `Pola tanam tidak terbaca: ...` bila periodisitas tanam tidak terdeteksi.

## Subcommand `tree-detect` (eksperimental)

```bash
.venv/bin/python analyze.py tree-detect --parcel-id TJP.0001.A.14.06.06.2018
```

Deteksi per pohon dari citra. **Belum menghasilkan angka yang valid** dengan citra yang tersedia sekarang — lihat [12-modul-tree-detect.md](12-modul-tree-detect.md). Sengaja hanya tersedia di CLI (tidak di dashboard) supaya hasil eksperimen tidak tampil sebagai hasil resmi. Argumen sama dengan `tree-count`; `--sph` di sini dipakai untuk menurunkan jarak minimum antar puncak, bukan untuk mengalikan luas.

Keluar dengan pesan `Citra tidak tersedia: ...` jika semua zoom hanya berisi tile placeholder.

## Error & exit

| Kondisi | Perilaku |
|---|---|
| Persil tidak ditemukan / tidak aktif | Exit non-zero, pesan `Persil tidak ditemukan: <ident>` |
| `parcel_id` cocok >1 persil aktif | Exit non-zero, pesan berisi daftar PK yang bisa dipakai |
| `.env` tidak lengkap | `KeyError` pada `PROD_DATABASE_URL` / `LOCAL_DATABASE_URL` |

Koneksi prod dan lokal selalu ditutup di blok `finally`, apa pun hasilnya.
