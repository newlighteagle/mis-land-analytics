# Modul tree counting (`mla/tree_count.py`)

Modul analisa pertama. Versi sekarang: **baseline kerapatan** (`baseline_density/v1`) — estimasi cepat tanpa citra, untuk semua persil. Tahap berikutnya: deteksi per pohon dari citra resolusi tinggi pada sampel persil (lihat [11-roadmap.md](11-roadmap.md)).

## Metode baseline

```
tree_count = round(area_ha × SPH)
```

- **`area_ha`** — kolom `area` dari `tbl_land_parcel` (tervalidasi akurat, lihat [04-database-mis-prod.md](04-database-mis-prod.md)).
- **SPH** (*stems per hectare*) — default **136 pohon/ha**, asumsi jarak tanam 9,2 m pola segitiga (standar kebun sawit). Bisa di-override per request (`--sph` di CLI, `sph` di API) karena kebun swadaya jarak tanamnya tidak seragam.
- **Koreksi umur belum ada** — `planting_year` kosong di semua baris prod. Tahun 4 digit yang tersirat di ujung `parcel_id` disimpan sebagai *hint* di `params.year_hint_from_parcel_id` untuk dipakai kelak, tapi belum memengaruhi hitungan.
- **Confidence selalu `low`** — ini estimasi kasar; nilainya sebagai baseline pembanding untuk metode deteksi nanti.

## Resolusi persil (`resolve_parcel`)

Input pengguna bisa `parcel_id` (ID lahan) atau primary key; query mencoba keduanya sekaligus terhadap persil `is_active`:

| Hasil query | Perilaku |
|---|---|
| 0 baris | raise `ParcelNotFound` |
| 1 baris | dipakai |
| >1 baris | raise `AmbiguousParcel` berisi daftar PK — pengguna harus memilih dan mengulang dengan PK (±20 `parcel_id` duplikat aktif di prod) |

## Penyimpanan hasil

Upsert ke `analytics.tree_count` dengan kunci `(land_parcel_pk, 'baseline_density')` — jalankan ulang = timpa, `computed_at` diperbarui. Kolom `image_date` selalu `NULL` (tidak pakai citra). Isi `params`:

| Kunci | Arti |
|---|---|
| `sph_source` | `"custom"` jika SPH di-override, `"default"` jika 136 |
| `year_hint_from_parcel_id` | Tahun dari regex `(19|20)\d{2}` pada `parcel_id`, atau `null` |
| `crop_type` | Snapshot dari prod saat dihitung (sering `null`) |
| `is_psr` | Snapshot status PSR (peremajaan sawit rakyat) |

## API modul (dipanggil CLI & FastAPI)

| Fungsi | Peran |
|---|---|
| `baseline(prod, local, ident, sph=None) -> dict` | Resolve → hitung → upsert → kembalikan baris hasil (nilai numeric sudah jadi `float`, timestamp ISO) |
| `results_for(local, land_parcel_pk) -> list[dict]` | Semua hasil persil, terurut terbaru dulu |
| `resolve_parcel(prod, ident) -> dict` | Dipakai internal; bisa dipakai modul lain |

Konstanta: `DEFAULT_SPH = 136.0`, `BASELINE_VERSION = "baseline_density/v1"` — naikkan versi setiap logika berubah.
