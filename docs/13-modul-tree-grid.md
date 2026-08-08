# Modul peta pohon: fitting kisi tanam (`mla/tree_grid.py`)

Menghasilkan **posisi pohon** dan **SPH terukur per persil** dari citra 0,6 m/px. Inilah metode yang dipakai dashboard untuk menampilkan titik pohon.

## Kenapa bukan deteksi objek per pohon

Deteksi puncak lokal per mahkota gagal di resolusi ini — maksimal 172 dari ~265 pohon meski mahkota terlihat mata telanjang ([12-modul-tree-detect.md](12-modul-tree-detect.md)). Tapi hal lain terbaca sangat kuat di citra yang sama: **periodisitas tanam**. Modul ini memakai periodisitas itu sebagai *prior* — alih-alih mencari tiap pohon secara independen, ia mencari **satu kisi** yang paling cocok untuk seluruh persil, lalu mengambil titik-titik kisi di dalam poligon.

Konsekuensinya harus dipahami: hasilnya **posisi model**, bukan deteksi individual. Titik mengikuti pola tanam terukur, jadi akurat di kebun teratur dan meleset di bagian yang kosong, mati, atau tidak beraturan. Modul ini **tidak bisa** menemukan pohon hilang — untuk itu tetap butuh deteksi sejati dengan citra ≤0,5 m/px.

## Cara kerja (`lattice_fit/v2`)

1. **Patch & detrend** — ambil kotak di dalam persil, buang gradien besar (`gaussian_filter σ=12`), beri window Hanning agar tepi tidak mencemari spektrum.
2. **Spektrum daya 2D** — FFT, ambil puncak lokal yang jatuh pada rentang jarak tanam masuk akal (6–13 m).
3. **Basis kisi** — puncak terkuat jadi vektor resiprokal `b1`; puncak berikutnya yang menyudut 40°–140° terhadapnya jadi `b2`. Basis nyata `A = inv(Bᵀ)` (karena `aᵢ·bⱼ = δᵢⱼ`), kolomnya vektor kisi `a1, a2` dalam pixel.
4. **Fitting fase + polaritas** — geser titik asal kisi pada 24×24 posisi di dalam satu sel. Mahkota bisa lebih gelap dari sela (kanopi dewasa) atau lebih terang (sawit muda di tanah gundul), jadi kedua polaritas dicoba.
5. **Penyetelan tiap titik (snap)** — tiap titik digeser ke respons terkuat dalam radius 0,3 × jarak tanam. Radius sengaja dibatasi di bawah setengah jarak tanam supaya titik tetap terikat kisinya dan tidak berubah jadi deteksi bebas yang terbukti tidak andal.
6. **Titik & hitung** — semua titik kisi di dalam poligon jadi posisi pohon; jumlahnya jadi `tree_count`, dan `SPH = 10.000 / luas sel kisi`.
7. **Kategori vigor** — tiap titik diberi kategori dari kehijauan mahkotanya (lihat di bawah).

### Pemilihan polaritas: jangan pakai magnitudo

Versi pertama memilih polaritas dari **besarnya** respons rata-rata. Itu salah dan terlihat jelas di citra 0,3 m: bayangan antar mahkota jauh lebih ekstrem daripada mahkotanya sendiri, sehingga kriteria magnitudo selalu menempelkan titik ke **sela**, bukan ke pohon.

Kriteria yang dipakai sekarang bersifat fisik: mahkota adalah vegetasi, jadi dipilih polaritas yang titik-titiknya **paling hijau** (`2G − R − B`). Setelah diperbaiki, polaritas terpilih jadi "terang" dan titik jatuh di pusat mahkota.

## Kategori vigor per pohon

Tiap titik dinilai dari kehijauan di posisinya, lalu dibandingkan dengan **median persil itu sendiri** memakai MAD (median absolute deviation):

| Kategori | Ambang | Arti |
|---|---|---|
| `kosong` | < median − 3,0 MAD | Tidak ada mahkota sehat di posisi tanam ini — bisa mati, tumbang, belum disulam, atau tidak pernah ditanam |
| `lemah` | < median − 1,5 MAD | Mahkota lebih pucat/kecil dari tetangganya |
| `sehat` | selebihnya | — |

**Kenapa MAD, bukan persentil.** Versi awal memakai peringkat persentil (10% terbawah = `kosong`). Itu tautologi: setiap persil otomatis menghasilkan proporsi identik 70/20/10, sehingga kebun yang seragam sehat dan kebun yang banyak kosong tampak sama persis. Dengan ambang sebaran, jumlah tiap kategori mengikuti keadaan lahan — kebun seragam wajar menghasilkan nyaris nol `kosong`.

Kategori ini **indikasi vigor dari citra, bukan diagnosis penyakit**. Untuk deteksi Ganoderma dan sejenisnya tetap perlu modul tersendiri plus verifikasi lapangan.

## Penjagaan kualitas

Mode kegagalan paling umum: basis yang terpilih bukan yang primitif melainkan **diagonal** kisi (mis. 9,2 × √2 = 13,0 m), yang membuat SPH tampak sekitar setengahnya. Karena itu hasil ditandai `confidence='low'` beserta daftar `params.warnings` bila:

- jarak tanam di luar 7,5–11,0 m, atau
- kedua sumbu kisi timpang (rasio > 1,35).

Hasil bersih ditandai `confidence='medium'`. Angka ber-`confidence low` **tetap disimpan** tapi jangan dipakai tanpa diperiksa.

## Hasil validasi

**Uji acak 16 persil (1,5–3,5 ha, lintas grup):** 16/16 berhasil, **SPH median 135,7** — praktis identik dengan asumsi baseline 136, tapi kini terukur per persil, bukan diasumsikan. 15/16 dalam rentang wajar; satu pencilan (APSS.0050.A) tertangkap penjagaan kualitas sebagai kasus diagonal-kisi.

**Uji silang pada ITM.0106.A.14.06.06.2017** (persil dengan 22 catatan panen):

| Ukuran | Nilai |
|---|---|
| Titik kisi | 286 pohon |
| Baseline (136 SPH × 1,951 ha) | 265 pohon |
| SPH terukur | 144,3 (jarak 8,98 × 8,98 m, arah baris 29,6°) |
| Produksi aktual 2025 | 39,40 t → 20,2 t/ha/thn |
| Hasil per pohon | 138 kg/pohon/thn (dengan 286 pohon) |

Pemeriksaan visual: titik kisi jatuh tepat di mahkota gelap di seluruh persil.

## Pemakaian

```bash
# satu lahan
.venv/bin/python analyze.py tree-grid --parcel-id ITM.0106.A.14.06.06.2017

# satu lembaga tani sekaligus (±1,5 detik per lahan berkat cache tile)
.venv/bin/python batch_analyze.py --group "KUD Intan Makmur"
```

Dashboard: tombol **"Petakan pohon dari citra"** pada kartu *Peta pohon (kisi tanam)* di menu *Analisa baru*.

| Fungsi | Peran |
|---|---|
| `fit(prod, local, ident) -> dict` | Fit kisi → simpan titik (`method='grid_fit'`) → upsert agregat |
| `fit_lattice(patch, mpp) -> dict` | Basis kisi dari spektrum; raise `NoLattice` bila pola tidak terbaca |
| `fit_phase(response, mask, lat)` | Cari fase & polaritas terbaik |

Exception: `NoLattice` (pola tanam tidak terbaca), `NoImagery` (citra tidak tersedia).
