# Modul deteksi per pohon (`mla/tree_detect.py`)

Modul 1 tahap 2: menghitung pohon dari citra, bukan dari asumsi kerapatan seperti [baseline](09-modul-tree-count.md).

> **Status: belum bisa dipakai untuk produksi.** Deteksi per pohon konsisten undercount 3–8×. Penyebabnya bukan sekadar resolusi: pada sebagian persil mahkota **jelas terlihat terpisah** di citra 0,6 m/px, tapi detektor puncak lokal tetap gagal mengisolasinya. Lihat [Hasil evaluasi](#hasil-evaluasi) dan [Yang justru berhasil](#yang-justru-berhasil-jarak-tanam-spektral).

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

**Koreksi penting (uji lanjutan pada ITM.0106.A.14.06.06.2017):** pemeriksaan visual persil ini menunjukkan mahkota sawit **jelas terpisah dalam pola grid teratur** pada 0,6 m/px — jadi anggapan awal "citra terlalu kasar di semua tempat" terlalu luas. Meski begitu deteksi hanya menemukan 48 pohon (vs baseline 265). Uji 32 kombinasi respons (kehijauan `2G−R−B`, kegelapan `−(R+G+B)`, ExG ternormalisasi, `G−B`) × sigma × jarak minimum × ambang menghasilkan maksimum **172 pohon** — masih jauh di bawah 265. Kesimpulan yang lebih tepat: **detektor puncak lokal sederhana yang tidak memadai**, bukan semata-mata citranya.

**Hasil uji ini sengaja dihapus dari database** supaya tidak ada angka menyesatkan di `analytics.tree_count` / `analytics.tree`.

## Yang justru berhasil: jarak tanam spektral

Alih-alih mengisolasi tiap mahkota, **periodisitas** tanaman terbaca sangat kuat dari citra yang sama lewat spektrum daya 2D (FFT pada patch di dalam persil, setelah gradien besar dibuang dan diberi window Hanning).

Pada ITM.0106.A puncak spektral dominan = **8,87 m** (14,9 px), dengan puncak pendukung di 8,47 m dan 9,31 m. Turunannya:

| Pola tanam | SPH tersirat |
|---|---|
| Segitiga | 147 pohon/ha |
| Persegi | 127 pohon/ha |

Baseline memakai 136 pohon/ha (asumsi 9,21 m) — **berada tepat di antara keduanya**, jadi asumsi baseline tervalidasi untuk persil ini lewat pengukuran langsung dari citra.

Ini jalur yang jauh lebih menjanjikan daripada hitung per pohon pada resolusi ini: mengukur jarak tanam nyata per persil untuk **mengganti asumsi SPH global 136 dengan SPH terukur per persil**, tanpa perlu mengisolasi tiap pohon. Belum diimplementasikan sebagai modul.

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
