# Sumber citra (`mla/imagery.py`)

Semua modul berbasis citra memanggil `imagery.fetch_parcel_image(bounds)`, yang memosaikkan tile XYZ (Web Mercator) untuk bbox persil + padding 20 m, dan mengembalikan `ParcelImage` berisi array RGB plus transform pixel ↔ lon/lat.

## Urutan sumber

Sumber dicoba berurutan; yang pertama punya citra lengkap dipakai. Nama sumber dicatat di `params.image_source` pada tiap hasil analisa.

| Prioritas | Sumber | Zoom native di area proyek | Resolusi |
|---|---|---|---|
| 1 | Google Satellite | 19 | **0,30 m/px** |
| 2 | Esri World Imagery | 18 | 0,60 m/px |

Zoom di atas native hanya dilayani sebagai hasil pembesaran (di area ini Google z20/z21 justru lebih kabur dari z19, ketajaman terukur turun dari 33,8 ke 20,1), jadi tidak ikut dicoba.

Perbedaan keduanya menentukan: pada 0,60 m/px mahkota sawit hanya gumpalan gelap ~12 px, sedangkan pada 0,30 m/px **pelepah tiap pohon terlihat**. Itulah yang membuat penyetelan posisi per pohon ([13-modul-tree-grid.md](13-modul-tree-grid.md)) dan kategori vigor jadi mungkin.

## Deteksi tile kosong

Esri mengembalikan **HTTP 200 berisi gambar abu-abu** bertuliskan *"Map data not yet available"* untuk zoom tanpa citra. Cek `std` tidak cukup karena teks pada placeholder membuat std tetap tinggi. Pembedanya saturasi: citra asli >99% pixel-nya bersaturasi (`max−min > 10` per pixel), placeholder ~0,1%. Tile placeholder diperlakukan sebagai "tidak ada", sehingga zoom/sumber berikutnya dicoba.

## Cache tile

Tile disimpan di `.tilecache/<sumber>/<z>/<x>/<y>.png` (tidak di-commit). Lahan bertetangga banyak berbagi tile, jadi cache memangkas ribuan permintaan saat menganalisa satu lembaga tani — kecepatan turun ke ±1,4 detik per lahan. Tile yang memang tidak ada citranya ditandai file `.miss` supaya tidak diminta ulang.

Lokasi cache bisa diganti lewat variabel lingkungan `TILE_CACHE_DIR`.

## Lisensi — perlu diperhatikan

> Kedua layanan ini berlisensi untuk **visualisasi**, dan tile Google di sini diakses di luar Google Maps Platform resmi — **tidak sesuai ToS Google**. Pemakaian saat ini sebatas prototipe internal atas keputusan pemilik proyek.
>
> Untuk produksi, pakai citra yang memang dilisensikan untuk analisa:
>
> | Opsi | Resolusi | Catatan |
> |---|---|---|
> | Maxar / Airbus | 0,3–0,5 m | Lisensi analisa, berbayar per km² — paling bersih secara hukum |
> | Google Maps Platform (Map Tiles API) | 0,3 m | Resmi & berbayar, tapi ToS-nya membatasi analisa otomatis dan penyimpanan turunan |
> | Drone/UAV | 2–10 cm | Paling akurat, data milik sendiri, butuh operasi lapangan |
