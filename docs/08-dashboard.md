# Dashboard: `static/index.html`

Dashboard spasial satu file (HTML + CSS + JS, tanpa build step). Peta **MapLibre GL** dengan basemap **Esri World Imagery** (citra satelit), panel kiri untuk pencarian dan analisa.

## Cara melihat

```bash
.venv/bin/uvicorn app:app --reload --port 8008
```

lalu buka **http://localhost:8008**. Butuh internet (MapLibre dimuat dari unpkg CDN, tile basemap dari server Esri) dan koneksi ke kedua database.

## Dua mode pemilihan persil

Tombol di atas kotak pencarian memilih mode:

| Mode | Perilaku |
|---|---|
| **Belum dianalisa** (default) | Pencarian penuh ke database prod, ketik ≥3 karakter ID lahan atau nama petani (debounce 250 ms, maks. 20 hasil). Persil yang sudah punya hasil analisa **dikecualikan** — jadi daftar ini adalah antrean kerja. |
| **Sudah dianalisa** | Select box yang bisa dicari: seluruh daftar persil yang pernah dianalisa dimuat sekali dari `/api/analyzed` lalu difilter di klien saat mengetik. Menampilkan nama petani, luas, jumlah metode, dan tanggal analisa terakhir. Daftar kosong menampilkan "Belum ada persil yang dianalisa." |

Setelah menjalankan analisa, daftar "sudah dianalisa" otomatis dimuat ulang sehingga persil itu langsung berpindah mode.

## Alur pemakaian

1. **Cari / pilih persil** — sesuai mode di atas.
2. **Klik hasil** — panel menampilkan atribut (petani, kelompok, luas, komoditas, status lahan, blok, PSR); peta menggambar poligon persil (kuning, semi-transparan) dan zoom ke bounding box-nya (maks. zoom 17).
3. **Analisa** — kartu *Tree count*: atur SPH (input angka, 50–200, default 136) lalu klik **Hitung (baseline)**. Hasil tampil sebagai `± N pohon` beserta luas, SPH, versi metode, dan confidence.
4. **Peta pohon** — kartu *Peta pohon (kisi tanam)*: klik **Petakan pohon dari citra**. Sistem mengambil citra persil, mengukur kisi tanam, lalu menggambar **titik pohon merah** di peta. Kartu menampilkan jumlah titik, jarak tanam, arah baris, dan SPH terukur. Titik ini adalah **posisi model** dari pola tanam terukur, bukan deteksi tiap pohon — lihat [13-modul-tree-grid.md](13-modul-tree-grid.md).
5. **Riwayat** — kartu *Riwayat hasil* menampilkan semua hasil tersimpan untuk persil itu (per metode; menjalankan ulang metode yang sama menimpa hasil lamanya — lihat [05-database-mis-analytics.md](05-database-mis-analytics.md)).

## Detail implementasi

- Peta di-inisialisasi di sekitar Riau (`center [100.7, 0.82]`, zoom 9).
- Poligon persil dirender dari respons `GET /api/parcel/{pk}` (GeoJSON Feature) ke satu source `parcel` dengan layer `fill` + `line`.
- Bounding box dihitung sendiri di klien (`bboxOf`) dari koordinat `Polygon`/`MultiPolygon` karena GeoJSON dari prod tidak membawa `bbox`.
- Semua interaksi lewat 4 endpoint di [07-api.md](07-api.md); tidak ada state selain `currentPk`.

## Keterbatasan saat ini

- Hanya satu persil tampil di peta pada satu waktu.
- Titik pohon adalah posisi model dari kisi tanam, jadi tidak menunjukkan pohon yang mati/hilang.
- Nilai SPH di UI dibatasi 50–200; API sendiri tidak membatasi.
