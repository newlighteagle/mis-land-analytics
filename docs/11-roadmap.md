# Roadmap

Modul dikerjakan bertahap; masing-masing modul baru = satu file di `mla/` + tabel hasil sendiri di schema `analytics` + subcommand CLI + endpoint API.

## 1. Tree counting — tahap 2: deteksi per pohon *(berikutnya)*

- Deteksi mahkota sawit dari citra resolusi tinggi pada **sampel** persil (baseline kerapatan tetap untuk semua persil sebagai pembanding).
- Hasil per pohon disimpan sebagai titik (tabel baru, mis. `analytics.tree`, geometri PostGIS `Point`) — dibutuhkan modul kesehatan/HPT ([10-keputusan-desain.md](10-keputusan-desain.md) #5).
- Agregatnya di-upsert ke `analytics.tree_count` dengan `method` berbeda (mis. `detection_esri`) + `image_date` terisi, sehingga bisa dibandingkan langsung dengan baseline per persil.

## 2. NDVI monitoring (Sentinel-2)

- Via Google Earth Engine — **prasyarat**: autentikasi GEE (akun `sofyan.agus18@gmail.com`, project di `GEE_PROJECT`) dan tambah `earthengine-api` ke `requirements.txt`.
- Time-series NDVI per persil (clip ke geometri persil). Perlu tabel dengan kunci `(persil, tanggal citra)` — bukan pola upsert satu-baris seperti tree_count ([10-keputusan-desain.md](10-keputusan-desain.md) #4).

## 3. Estimasi biomasa/karbon

- Persamaan allometrik sawit + umur tanam. **Blocker data**: `planting_year` kosong di prod; sementara pakai hint tahun dari `parcel_id` yang sudah dicatat di `params` hasil tree count.

## 4. Analisa kesehatan

- Deteksi anomali pada time-series vigor (basis: data modul NDVI), level persil dan — setelah modul deteksi jadi — level pohon.

## 5. Deteksi HPT (Ganoderma, dll.)

- Bergantung pada data level pohon (modul 1 tahap 2) dan time-series kesehatan (modul 4).

## 6. Analisa/prediksi panen

- Model estimasi produksi, dikalibrasi terhadap ground truth `tbl_production_record` di prod.

## Urutan ketergantungan

```
tree count baseline ✅ ─▶ deteksi per pohon ─▶ deteksi HPT
GEE auth ─▶ NDVI ─▶ kesehatan ─▶ (mendukung HPT)
year hint / planting_year ─▶ biomasa/karbon
tbl_production_record ─▶ prediksi panen
```
