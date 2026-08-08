# Evaluasi & riwayat model

Kerangka untuk menjawab satu pertanyaan: **seberapa tepat titik yang kita hasilkan berada di pusat tajuk pohon?** Tanpa angka, perbaikan model hanya tebakan.

```bash
.venv/bin/python eval_models.py --parcel-id ITM.0001.A.14.06.06.2017
```

Tiap varian detektor diukur dengan metrik yang sama lalu dicatat ke `analytics.model_run` (`sql/004_model_run.sql`), sehingga versi model bisa dibandingkan antar waktu.

## Metrik

| Metrik | Arti | Bias |
|---|---|---|
| **`lattice_rmse_m`** | Simpangan titik ke posisi kisi ideal terdekat, setelah fase kisi terbaik dicari. **Metrik utama.** | Netral — tidak memakai citra sama sekali |
| `lattice_within_1m` / `_2m` | Proporsi titik dalam 1 m / 2 m dari posisi kisi ideal | Netral |
| `symmetry_pct` | Persentil nilai simetri radial (FRST) di titik, terhadap seluruh pixel persil | **Bias** ke varian berbasis FRST |
| `xmethod_offset_m` | Jarak median ke pusat tajuk versi detektor celah-gelap | **Bias** ke varian `gap_distance` |
| `ratio_to_expected` | Jumlah titik ÷ perkiraan pohon dari luas & jarak tanam | Netral |

**Kenapa keteraturan kisi jadi metrik utama.** Sawit ditanam pada jarak teratur, jadi pusat tajuk yang benar **harus** membentuk kisi rapi. Kriteria ini berakar pada agronomi, tidak memakai citra, dan tidak berpihak pada detektor mana pun — berbeda dengan metrik berbasis citra yang selalu menguntungkan detektor yang memakai isyarat serupa.

**Baseline acak wajib disertakan.** Tanpa tahu skor "asal tebak", angka apa pun tidak bermakna. Titik acak dalam persil menghasilkan `lattice_rmse_m` ≈ 3,5 m pada jarak tanam 9,2 m.

**Batas bawah metrik tidak diketahui.** Penanaman di lapangan tidak pernah persis teratur, jadi detektor sempurna sekalipun tetap menyisakan simpangan. Karena itu `lattice_rmse_m` bagus untuk **membandingkan** model, tapi tidak bisa dibaca sebagai galat mutlak.

## Hasil pengukuran (ITM.0001.A, Google z19, 0,30 m/px, jarak tanam 9,22 m)

| Varian | n | rasio | kisi rmse (m) | ≤1 m | ≤2 m |
|---|---|---|---|---|---|
| `template_r3` — template tajuk hasil belajar sendiri, 3 iterasi | 294 | 1,10 | **2,48** | 0,19 | 0,53 |
| `v2_greenness` — puncak kehijauan (model terpakai) | 256 | 0,96 | 2,50 | 0,20 | 0,52 |
| `template_r1` | 285 | 1,07 | 2,54 | 0,23 | 0,50 |
| `gap_distance` — jarak dari celah gelap | 236 | 0,88 | 2,83 | 0,14 | 0,41 |
| `bright_peak` — puncak kecerahan | 223 | 0,84 | 2,98 | 0,07 | 0,33 |
| `orient_dispersion` — sebaran arah pelepah | 242 | 0,91 | 3,50 | 0,08 | 0,28 |
| **`random` — baseline acak** | 255 | 0,96 | **3,50** | 0,02 | 0,17 |
| `frst_bright` — simetri radial | 255 | 0,96 | 3,53 | 0,04 | 0,20 |
| `frst_dark` | 280 | 1,05 | 3,54 | 0,07 | 0,20 |

## Temuan kunci: sebagian besar "galat" ternyata milik lahan

Metrik kisi kaku menyalahkan model atas sesuatu yang bukan salahnya. Barisan tanam di kebun swadaya **melengkung dan bergeser**; kisi satu fase untuk seluruh persil memaksa titik meleset di ujung-ujung lahan.

Saat fase kisi dicari ulang **per blok 4×4 sel**, angkanya berubah drastis:

| Varian | rmse kisi kaku | rmse kisi lokal | ≤1 m (lokal) |
|---|---|---|---|
| `v2_greenness` | 2,50 | **1,47** | 0,56 |
| `obia_weighted` | 2,56 | 1,50 | **0,63** |
| `obia_watershed` | 2,48 | 1,59 | **0,64** |
| `template_r3` | 2,48 | 1,58 | 0,56 |
| `random` | 3,54 | 3,33 | 0,07 |

Titik acak nyaris tidak membaik (3,54 → 3,33), jadi perbaikan besar pada detektor asli memang nyata, bukan artefak metrik yang jadi longgar.

**Dua perbaikan yang lahir dari temuan ini, dan keduanya sudah masuk ke model produksi `lattice_fit/v3`:**

1. **Fase kisi per blok** (`fit_phase_local`) — kisi mengikuti lengkungan barisan tanam.
2. **Detektor OBIA** (`crown.centers_obia`) — segmentasi watershed pada peta kehijauan, lalu pusat massa berbobot tiap segmen tajuk. Unggul pada kriteria paling praktis (titik dalam 1 m): 63–64% vs 56%.

Hasil pada persil yang sama, model produksi:

| Versi | Kandidat | Cocok ke tajuk | Simpangan median |
|---|---|---|---|
| `lattice_fit/v2` (puncak kehijauan, fase global) | 256 | 83% | 2,00 m |
| **`lattice_fit/v3` (OBIA + fase per blok)** | 253 | **91%** | **1,08 m** |

## Kesimpulan yang harus dibaca apa adanya

1. **FRST (simetri radial) gagal**, praktis setara acak, meski secara teori paling cocok untuk struktur memancar. Penyebabnya: gradien di tepi pelepah tegak lurus arah pelepah, jadi tidak menunjuk ke pusat tajuk.
2. **Template hasil belajar sendiri** setara dengan puncak kehijauan — menarik tapi tidak mengungguli OBIA pada kriteria ≤1 m.
3. **Yang benar-benar menaikkan akurasi bukan detektornya, melainkan membiarkan kisi melengkung** mengikuti lahan. Ini pelajaran yang mudah terlewat kalau hanya menatap gambar.
4. `symmetry_pct` bukan metrik yang berguna di sini: `frst_bright` meraih 99,4 sambil berkinerja setara acak pada metrik netral — bukti bahwa metrik yang sekelas dengan detektornya akan selalu menyanjung dirinya sendiri.

**Sisa jarak menuju akurasi yang benar-benar tinggi tidak akan ditutup oleh penyetelan parameter.** Yang dibutuhkan berbeda kelas:

- **Detektor terlatih (CNN)** — perlu label pusat tajuk pada beberapa ratus pohon sebagai data latih. Ini jalur standar di literatur dan yang paling mungkin berhasil pada 0,3 m/px.
- **Citra lebih tajam** — drone 5–10 cm membuat pusat tajuk terlihat tegas, dan detektor sederhana pun cukup.
- **Ground truth lapangan** — sekaligus mengubah `lattice_rmse_m` dari metrik pembanding jadi ukuran galat mutlak.

## Hasil tiap versi disimpan berdampingan

`analytics.tree` dan `analytics.tree_count` memakai kunci `(persil, metode, **versi model**)`, jadi menjalankan versi baru **tidak menghapus** hasil versi lama (`sql/005_model_version.sql`). Di dashboard, kartu *Ringkasan pohon* punya pemilih **Versi model** beserta metrik tiap versi, sehingga perbaikan bisa dibandingkan langsung di peta.

Endpoint terkait: `GET /api/parcel/{pk}/versions` (daftar versi + metrik) dan `GET /api/parcel/{pk}/trees?version=...`.

## v4: keluaran gabungan — jangan buang tajuk yang sudah terdeteksi

Pemeriksaan visual pada v3 menemukan tajuk yang jelas terlihat tapi tanpa titik. Penyebabnya struktural: **keluaran v3 digerakkan oleh kisi** — jumlah titik = jumlah simpul kisi di dalam poligon, sehingga tajuk nyata yang tidak sejajar simpul mana pun ikut terbuang.

Terukur pada ITM.0001.A: dari 253 kandidat tajuk, **24 tidak pernah ikut keluar** karena tidak ada simpul kisi yang mencocokinya.

`union_points` mengubah keluaran jadi gabungan:

- tiap kandidat tajuk **selalu** jadi titik (posisinya dari citra),
- simpul kisi tanpa kandidat ditambahkan sebagai **posisi tanam kosong**.

Marker OBIA juga dilonggarkan (jarak minimum 0,45 → 0,38 × jarak tanam), karena marker yang terlewat berarti tajuk hilang selamanya, sedangkan marker berlebih masih tersaring filter luas segmen.

| Versi | n | rasio ke perkiraan | rmse lokal | ≤1 m | ≤2 m | cocok ke tajuk |
|---|---|---|---|---|---|---|
| `v2` puncak kehijauan, fase global | 271 | 1,02 | 1,43 | 0,54 | 0,81 | 83% |
| `v3` OBIA + fase per blok | 266 | 1,00 | 1,53 | 0,64 | 0,84 | 91% |
| **`v4` + keluaran gabungan** | 285 | 1,07 | 1,46 | 0,61 | **0,88** | **97%** |

v4 menaikkan cakupan (≤2 m dari 0,84 → 0,88; tajuk terpakai 97%) dengan rmse yang praktis sama. Jumlah titik jadi 7% di atas perkiraan luas — konsekuensi wajar dari memilih **tidak membuang** tajuk yang terdeteksi.
