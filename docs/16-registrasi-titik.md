# Registrasi titik pohon (draf model + koreksi manusia)

Model menghasilkan **draf** posisi pohon; manusia membetulkannya di peta. Alur ini dipilih setelah pengukuran menunjukkan deteksi otomatis mentok di ~60% titik dalam 1 m dari posisi seharusnya ([15-evaluasi-model.md](15-evaluasi-model.md)) — jarak sisanya lebih murah ditutup oleh koreksi manusia daripada oleh penyetelan algoritma.

Manfaat gandanya: hasil koreksi **menjadi ground truth**. Itulah yang selama ini hilang, dan yang dibutuhkan baik untuk melatih detektor yang lebih baik maupun untuk mengubah metrik evaluasi dari sekadar pembanding jadi ukuran galat mutlak.

## Cara pakai di dashboard

1. Pilih lahan, lalu pada kartu *Ringkasan pohon* klik **✏️ Mode registrasi titik**.
2. **Geser** titik untuk membetulkan posisinya — perubahan langsung tersimpan saat tombol tetikus dilepas.
3. **Klik peta kosong** untuk menambah titik yang dilewatkan model.
4. **Klik titik** untuk memilihnya, lalu **Hapus titik terpilih** untuk membuang titik palsu.

Titik hasil koreksi manusia diberi **garis tepi putih** agar langsung terbedakan dari draf model. Penghitung di bawah tombol menunjukkan komposisinya secara langsung.

## Asal-usul tiap titik

Kolom `source` di `analytics.tree` (`sql/006_tree_edit.sql`) melacak siapa yang menentukan posisi:

| Nilai | Arti |
|---|---|
| `auto` | Draf model, belum disentuh |
| `moved` | Posisi digeser manusia |
| `added` | Ditambahkan manusia (model melewatkannya) |
| `verified` | Diperiksa manusia dan dinyatakan sudah benar |

Kolom `edited_at` mencatat kapan disunting. Pemisahan ini penting: angka jumlah pohon dari lahan yang sudah diregistrasi punya keandalan berbeda dengan yang masih draf, dan laporan tidak boleh mencampur keduanya begitu saja.

## Endpoint

| Endpoint | Fungsi |
|---|---|
| `POST /api/parcel/{pk}/trees` | Tambah titik (`{lon, lat, category}`) → `source='added'` |
| `PATCH /api/trees/{id}` | Geser (`{lon, lat}` → `moved`) dan/atau ubah kategori (→ `verified`) |
| `DELETE /api/trees/{id}` | Hapus titik |

Semua perubahan masuk ke versi model yang sedang ditampilkan, sehingga draf tiap versi bisa diregistrasi terpisah.

## Tahap 2: kategorisasi (`mla/vigor.py`)

Setelah posisi titik dipastikan, tombol **🔬 Analisa kategori pohon** memberi label sehat/lemah/kosong pada seluruh titik lahan itu.

Urutannya sengaja dipisah. Menilai kesehatan sebelum posisi benar hanya menyebarkan kesalahan posisi ke dalam angka kesehatan: titik yang meleset ke sela antar tajuk terbaca pucat, lalu pohon sehat tervonis mati — dan kesalahan itu tampak meyakinkan karena sudah berbentuk angka.

Cara kerjanya:

1. Ambil semua titik teregistrasi lahan itu, apa pun asalnya (`auto`, `moved`, `added`).
2. Contoh kehijauan pada **cakram berjari-jari 1,75 m** di sekitar tiap titik — rata-rata seukuran tajuk, jauh lebih stabil daripada satu pixel.
3. Bandingkan dengan median lahan itu sendiri memakai MAD:

| Kategori | Ambang |
|---|---|
| `kosong` | < median − 3,0 MAD |
| `lemah` | < median − 1,5 MAD |
| `sehat` | selebihnya |

Ambang sebaran dipakai, **bukan peringkat persentil**: persentil selalu menghasilkan proporsi tetap, sehingga kebun yang seragam sehat dan kebun yang banyak mati akan tampak sama persis.

Hasil dicatat di kolom `score` (vigor 0–1) dan `category` tiap titik, serta diringkas ke `params.kategori` pada baris agregat. Endpoint: `POST /api/parcel/{pk}/categorize`.

Kategori ini tetap **relatif antar pohon di lahan yang sama dan bukan diagnosis penyakit** — untuk Ganoderma dan sejenisnya perlu modul tersendiri plus verifikasi lapangan.

## Ekspor

Tiga tombol di kartu *Ringkasan pohon* mengunduh titik lahan terpilih:

| Format | Isi |
|---|---|
| **CSV** | Tabel datar, ber-BOM UTF-8 supaya rapi dibuka di Excel |
| **Shapefile** | `.shp/.shx/.dbf/.prj/.cpg` dibungkus zip, plus README penjelasan kolom |
| **GeoJSON** | FeatureCollection CRS84, siap dibuka di QGIS/web |

Semua format memuat kolom sama: `no`, `tree_id`, `parcel_id`, `farmer`, `lon`, `lat`, `category`, `vigor`, `source`, `model_ver`.

Kolom `source` dan `model_ver` sengaja ikut diekspor. Penerima data harus bisa membedakan titik hasil registrasi manusia dari draf model — tanpa itu, angka draf gampang dipakai seolah sudah terverifikasi. Koordinat dalam WGS84 (EPSG:4326).

Endpoint: `GET /api/parcel/{pk}/export.{csv|geojson|shp}`.

## Rencana lanjutan

- **Ekspor data latih** dari titik `moved`/`added`/`verified` untuk melatih detektor CNN.
- **Ukur galat mutlak** model dengan membandingkan draf terhadap titik hasil registrasi pada lahan yang sama.
- **Tandai lahan selesai registrasi** supaya laporan bisa memisahkan angka terverifikasi dari angka draf.
