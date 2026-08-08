# Modul deteksi per pohon (`mla/tree_detect.py`)

Modul 1 tahap 2: menghitung pohon dari citra, bukan dari asumsi kerapatan seperti [baseline](09-modul-tree-count.md).

> **Status: belum bisa dipakai untuk produksi.** Mesin deteksinya sudah jalan, tapi citra yang tersedia (Esri World Imagery, maks. 0,6 m/px) **tidak cukup resolusinya** untuk area ini. Lihat [Hasil evaluasi](#hasil-evaluasi). Kode disimpan karena akan langsung berguna begitu ada citra yang lebih tajam.

## Metode `local_maxima/v1`

1. **Ambil citra** (`mla/imagery.py`) — mosaik tile XYZ Esri untuk bbox persil + padding 20 m, pada zoom tertinggi yang tersedia (dicoba 19 → 18 → 17).
2. **Respons mahkota** — indeks kehijauan visible-band `2G − R − B`, dihaluskan Gaussian dengan `sigma = radius mahkota / 2` (radius diasumsikan 3,5 m).
3. **Puncak lokal** — `peak_local_max` dengan jarak minimum `0,8 × jarak tanam` (jarak tanam dihitung dari SPH pola segitiga: `s = √(2·(10000/SPH)/√3)`, jadi 9,21 m pada SPH 136).
4. **Masking** — hanya puncak di dalam poligon persil (poligon dirasterisasi via PIL `ImageDraw`).
5. **Ambang** — puncak di bawah persentil 40 dari distribusi respons **di dalam persil** dibuang.

### Catatan implementasi yang mudah salah

- **Ambang harus absolut, bukan `threshold_rel`.** Respons `2G − R − B` berpusat di sekitar nol dengan rentang sempit (mis. −0,75 … +0,18). `threshold_rel` pada skimage dihitung relatif terhadap **puncak tertinggi**, sehingga pada respons semacam ini hampir semua puncak terbuang (percobaan awal: 609 puncak → 4 puncak).
- **Tile placeholder harus dideteksi lewat saturasi.** Esri mengembalikan HTTP 200 berisi gambar abu-abu bertuliskan *"Map data not yet available"* untuk zoom yang tidak punya citra. Cek `std` tidak cukup — teks pada placeholder membuat std tetap tinggi. Yang membedakan: citra asli >99% pixel-nya bersaturasi (`max−min > 10` per pixel), placeholder ~0,1%.

## Hasil evaluasi

Survei ketersediaan citra pada 12 grup tani (satu persil per grup, tersebar di seluruh dataset): **semuanya maksimal zoom 18 ≈ 0,60 m/px**; zoom 19–20 selalu placeholder.

Deteksi pada 9 persil (2 kelompok umur):

| Kelompok | Persil | SPH terdeteksi | SPH baseline |
|---|---|---|---|
| Tanaman tua (hint 2006–2012) | 6 | 17,7 – 43,3 | 136 |
| Tanaman muda (hint 2019–2021) | 3 | 31,4 – 33,3 | 136 |

Dua hal yang menyimpulkan metode ini belum valid di citra tersebut:

1. **Undercount 3–8×** terhadap baseline.
2. **Kerapatan hasil hampir konstan (~32 SPH) lintas umur tanam.** Detektor yang benar-benar menemukan pohon akan memberi angka berbeda antara tegakan muda (mahkota terpisah) dan tua (kanopi rapat). Angka yang seragam menandakan yang tertangkap adalah tekstur kanopi pada skala tertentu, bukan pohon.

Pemeriksaan visual mendukung: pada 0,6 m/px mahkota sawit hanya ~12 px dan pada kanopi tertutup batasnya tidak terlihat.

**Hasil uji ini sengaja dihapus dari database** supaya tidak ada angka menyesatkan di `analytics.tree_count` / `analytics.tree`.

## Yang dibutuhkan supaya modul ini valid

Deteksi mahkota sawit umumnya butuh **≤ 0,5 m/px**, idealnya 0,3 m/px. Opsi, dari yang paling ringan:

| Sumber | Resolusi | Catatan |
|---|---|---|
| Drone/UAV | 2–10 cm | Paling akurat; butuh operasi lapangan, cocok untuk sampel validasi |
| Maxar / Airbus (komersial) | 0,3–0,5 m | Berbayar per km²; layak untuk sampel persil, mahal untuk 10.950 persil |
| Sentinel-2 (GEE) | 10 m | **Tidak bisa** untuk hitung pohon; tetap berguna untuk NDVI/kesehatan |
| Planet NICFI | 4,7 m | Tidak cukup untuk hitung pohon |

Selama belum ada sumber di atas, **baseline kerapatan tetap angka rujukan** untuk jumlah pohon.

## Lisensi citra

Esri World Imagery berlisensi untuk **visualisasi** (basemap). Pemakaian di sini sebatas prototipe internal untuk uji kelayakan. Jika modul ini dilanjutkan dengan sumber komersial, ikuti lisensi sumber tersebut.

## API modul

| Fungsi | Peran |
|---|---|
| `detect(prod, local, ident, sph=None) -> dict` | Deteksi → simpan titik ke `analytics.tree` → upsert agregat (`method='detection_esri'`, confidence `medium`) |
| `points_for(local, pk, method) -> dict` | Titik pohon sebagai GeoJSON FeatureCollection |
| `bounds_of` / `rings_of` / `spacing_m` / `parcel_mask` | Helper geometri, dipakai juga oleh modul lain |

Raise `NoImagery` jika tidak ada citra non-placeholder di semua zoom.
