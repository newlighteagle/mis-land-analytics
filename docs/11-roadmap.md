# Roadmap

Modul dikerjakan bertahap; masing-masing modul baru = satu file di `mla/` + tabel hasil sendiri di schema `analytics` + subcommand CLI + endpoint API.

## 1. Tree counting — tahap 2: deteksi per pohon *(dicoba, terhambat resolusi citra)*

Mesin deteksi sudah dibangun (`mla/imagery.py` + `mla/tree_detect.py`, tabel `analytics.tree`), tapi **evaluasi menunjukkan citra Esri (maks. 0,6 m/px di seluruh area) tidak cukup** — detail dan angkanya di [12-modul-tree-detect.md](12-modul-tree-detect.md).

Untuk deteksi individual sejati, butuh citra komersial ≤0,5 m/px (Maxar/Airbus) atau foto drone.

**Namun jalur pengganti sudah jadi dan bekerja:** [fitting kisi tanam](13-modul-tree-grid.md) (`mla/tree_grid.py`) menghasilkan posisi pohon dan SPH terukur per persil dari citra yang sama — tervalidasi 16/16 persil dengan SPH median 135,7. Ini yang dipakai dashboard untuk layer titik pohon.

Lanjutan yang masuk akal untuk modul ini: pakai SPH terukur menggantikan asumsi 136 pada baseline seluruh persil (batch), dan bandingkan titik kisi dengan respons citra untuk menandai posisi yang kemungkinan pohonnya hilang.

## 2. NDVI monitoring (Sentinel-2) *(berikutnya)*

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
tree count baseline ✅ ─▶ deteksi per pohon ⛔ (butuh citra ≤0,5 m/px) ─▶ deteksi HPT
GEE auth ─▶ NDVI ─▶ kesehatan ─▶ (mendukung HPT)
year hint / planting_year ─▶ biomasa/karbon
tbl_production_record ─▶ prediksi panen
```

Karena deteksi per pohon terhambat sumber citra (bukan soal kode), jalur NDVI kini jadi lintasan utama yang bisa diteruskan sekarang.
