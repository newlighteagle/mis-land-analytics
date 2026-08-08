# Modul peta pohon: fitting kisi tanam (`mla/tree_grid.py`)

Menghasilkan **posisi pohon** dan **SPH terukur per persil** dari citra 0,6 m/px. Inilah metode yang dipakai dashboard untuk menampilkan titik pohon.

## Kenapa bukan deteksi objek per pohon

Deteksi puncak lokal per mahkota gagal di resolusi ini — maksimal 172 dari ~265 pohon meski mahkota terlihat mata telanjang ([12-modul-tree-detect.md](12-modul-tree-detect.md)). Tapi hal lain terbaca sangat kuat di citra yang sama: **periodisitas tanam**. Modul ini memakai periodisitas itu sebagai *prior* — alih-alih mencari tiap pohon secara independen, ia mencari **satu kisi** yang paling cocok untuk seluruh persil, lalu mengambil titik-titik kisi di dalam poligon.

Konsekuensinya harus dipahami: hasilnya **posisi model**, bukan deteksi individual. Titik mengikuti pola tanam terukur, jadi akurat di kebun teratur dan meleset di bagian yang kosong, mati, atau tidak beraturan. Modul ini **tidak bisa** menemukan pohon hilang — untuk itu tetap butuh deteksi sejati dengan citra ≤0,5 m/px.

## Cara kerja (`lattice_fit/v1`)

1. **Patch & detrend** — ambil kotak di dalam persil, buang gradien besar (`gaussian_filter σ=12`), beri window Hanning agar tepi tidak mencemari spektrum.
2. **Spektrum daya 2D** — FFT, ambil puncak lokal yang jatuh pada rentang jarak tanam masuk akal (6–13 m).
3. **Basis kisi** — puncak terkuat jadi vektor resiprokal `b1`; puncak berikutnya yang menyudut 40°–140° terhadapnya jadi `b2`. Basis nyata `A = inv(Bᵀ)` (karena `aᵢ·bⱼ = δᵢⱼ`), kolomnya vektor kisi `a1, a2` dalam pixel.
4. **Fitting fase** — geser titik asal kisi pada 12×12 posisi di dalam satu sel, pilih yang rata-rata respons mahkotanya paling kuat. Polaritas dicoba dua arah karena mahkota bisa **lebih gelap** dari sela (kanopi dewasa di tanah terang) atau **lebih terang** (sawit muda di tanah gundul).
5. **Titik & hitung** — semua titik kisi di dalam poligon jadi posisi pohon; jumlahnya jadi `tree_count`, dan `SPH = 10.000 / luas sel kisi`.

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
.venv/bin/python analyze.py tree-grid --parcel-id ITM.0106.A.14.06.06.2017
```

Dashboard: tombol **"Petakan pohon dari citra"** pada kartu *Peta pohon (kisi tanam)*.

| Fungsi | Peran |
|---|---|
| `fit(prod, local, ident) -> dict` | Fit kisi → simpan titik (`method='grid_fit'`) → upsert agregat |
| `fit_lattice(patch, mpp) -> dict` | Basis kisi dari spektrum; raise `NoLattice` bila pola tidak terbaca |
| `fit_phase(response, mask, lat)` | Cari fase & polaritas terbaik |

Exception: `NoLattice` (pola tanam tidak terbaca), `NoImagery` (citra tidak tersedia).
