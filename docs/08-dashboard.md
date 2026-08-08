# Dashboard: `static/index.html`

Dashboard spasial satu file (HTML + CSS + JS, tanpa build step). Peta **MapLibre GL** dengan basemap **Esri World Imagery** (citra satelit), panel kiri untuk pencarian dan analisa.

## Cara melihat

```bash
.venv/bin/uvicorn app:app --reload --port 8008
```

lalu buka **http://localhost:8008**. Butuh internet (MapLibre dimuat dari unpkg CDN, tile basemap dari server Esri) dan koneksi ke kedua database.

## Dua menu

Panel dipisah menurut pekerjaannya: **melihat hasil** vs **menjalankan analisa**. Alat analisa (tombol hitung) hanya muncul di menu kedua, supaya menelusuri hasil tidak tercampur dengan menjalankan proses.

### Menu "Hasil analisa" (default) — telusur per lembaga tani

**Tingkat 1 — daftar lembaga tani.** Semua 27 lembaga tampil beserta progres cakupan analisanya:

```
KUD Intan Makmur                              0.6%
2 / 317 lahan teranalisa · 619 ha
▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

Terurut dari yang paling banyak dianalisa. Kotak di atas menyaring daftar per nama lembaga (difilter di klien).

**Tingkat 2 — lahan dalam satu lembaga.** Klik lembaga untuk melihat daftar lahannya yang **sudah dianalisa**, tiap baris langsung menampilkan hasilnya (jumlah pohon dan SPH terukur). Peta serentak menggambar poligon biru semua lahan teranalisa di lembaga itu dan zoom ke sebarannya; poligonnya bisa diklik langsung. Tautan **← Semua lembaga tani** kembali ke tingkat 1.

**Tingkat 3 — detail lahan.** Klik lahan (dari daftar atau dari peta) untuk melihat atribut, kartu *Hasil analisa*, dan titik pohon.

### Menu "Analisa baru"

Pencarian penuh ke database prod (ketik ≥3 karakter ID lahan atau nama petani, debounce 250 ms, maks. 20 hasil). Lahan yang **sudah** punya hasil dikecualikan, jadi daftar ini berfungsi sebagai antrean kerja. Setelah memilih lahan, dua kartu alat muncul:

- **Tree count (baseline)** — atur SPH (50–200, default 136) lalu **Hitung**. Hasil tampil sebagai `± N pohon`.
- **Peta pohon (kisi tanam)** — **Petakan pohon dari citra**: sistem mengambil citra, mengukur kisi tanam, lalu menggambar **titik pohon merah** di peta. Kartu menampilkan jumlah titik, jarak tanam, arah baris, SPH terukur, dan peringatan bila hasilnya `confidence: low`. Titik ini **posisi model**, bukan deteksi tiap pohon — lihat [13-modul-tree-grid.md](13-modul-tree-grid.md).

## Alur pemakaian

1. **Pilih lembaga tani** → **pilih lahan** dari daftarnya (menu Hasil analisa), atau **cari lahan** yang belum dianalisa (menu Analisa baru).
2. Panel menampilkan atribut lahan (petani, kelompok, luas, komoditas, status lahan, blok, PSR); peta menggambar poligon lahan (kuning) dan zoom ke bounding box-nya (maks. zoom 17), plus titik pohon merah bila sudah dipetakan.
3. Kartu **Ringkasan pohon** menampilkan jumlah total dan sebaran kategori (sehat / lemah / kosong) dengan batang proporsi. **Klik titik pohon di peta** untuk popup berisi nomor pohon, kategori, vigor relatif, dan koordinatnya.
4. Kartu **Hasil analisa** menampilkan semua hasil tersimpan untuk lahan itu — metode, jumlah pohon, SPH, confidence, tanggal (per metode; menjalankan ulang metode yang sama menimpa hasil lamanya, lihat [05-database-mis-analytics.md](05-database-mis-analytics.md)).

## Detail implementasi

- Tiga layer peta bertumpuk: `done` (garis biru, ikhtisar lahan teranalisa), `parcel` (garis kuning, lahan terpilih), `trees` (titik, radius ikut skala zoom, **warna menurut kategori**: hijau `sehat`, kuning `lemah`, merah `kosong`). Layer `done-fill` tetap ada dengan `fill-opacity: 0` — tidak terlihat, tapi itulah yang menangkap klik poligon.
- **Legenda di kanan atas peta** menyalakan/mematikan tiap layer lewat `setLayoutProperty(..., 'visibility', ...)`. Mematikan "Lahan teranalisa" ikut mematikan `done-fill`, supaya klik tidak nyasar ke poligon yang tak terlihat. Kontrol zoom bawaan dipindah ke kanan bawah agar tidak menutupi legenda.
- **Pilihan peta dasar** di legenda: Google Satellite (default, 0,30 m/px) atau Esri World Imagery (0,60 m/px). Keduanya dimuat sebagai layer raster sekaligus dan dipilih lewat visibility — bukan ganti style — supaya layer analisa di atasnya tidak perlu dibangun ulang.

  > Peta dasar Google dipakai **hanya untuk tampilan** di dashboard. Analisa (`mla/imagery.py`) tetap mengambil citra dari Esri. Perlu dicatat bahwa mengakses tile Google di luar Google Maps Platform resmi tidak sesuai ToS-nya; untuk produksi, pakai penyedia berlisensi.
- Peta di-inisialisasi di sekitar Riau (`center [100.7, 0.82]`, zoom 9).
- Poligon persil dirender dari respons `GET /api/parcel/{pk}` (GeoJSON Feature) ke satu source `parcel` dengan layer `fill` + `line`.
- Bounding box dihitung sendiri di klien (`bboxOf`) dari koordinat `Polygon`/`MultiPolygon` karena GeoJSON dari prod tidak membawa `bbox`.
- Semua interaksi lewat 4 endpoint di [07-api.md](07-api.md); tidak ada state selain `currentPk`.

## Keterbatasan saat ini

- Hanya satu persil tampil di peta pada satu waktu.
- Titik pohon adalah posisi model dari kisi tanam, jadi tidak menunjukkan pohon yang mati/hilang.
- Nilai SPH di UI dibatasi 50–200; API sendiri tidak membatasi.
