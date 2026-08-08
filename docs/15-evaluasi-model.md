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

## Kesimpulan yang harus dibaca apa adanya

1. **Semua detektor klasik mentok di sekitar 2,5 m rmse** — hanya sedikit lebih baik daripada acak (3,5 m), dan cuma ~20% titik berada dalam 1 m dari posisi kisi ideal.
2. **FRST (simetri radial) gagal**, praktis setara acak, meski secara teori paling cocok untuk struktur memancar. Penyebabnya: gradien di tepi pelepah tegak lurus arah pelepah, jadi tidak menunjuk ke pusat tajuk.
3. **Template hasil belajar sendiri sedikit unggul** tapi bedanya tipis terhadap puncak kehijauan — belum layak disebut perbaikan berarti.
4. `symmetry_pct` model terpakai hanya 17,4 (acak 46,3), artinya titiknya justru **menjauhi** pusat simetri — konsisten dengan pengamatan visual bahwa titik menempel ke rumpun pelepah.

**Artinya penyetelan parameter sudah tidak akan banyak menolong.** Untuk melompat ke akurasi yang benar-benar bagus, yang dibutuhkan berbeda kelas:

- **Detektor terlatih (CNN)** — perlu label pusat tajuk pada beberapa ratus pohon sebagai data latih. Ini jalur standar di literatur dan yang paling mungkin berhasil pada 0,3 m/px.
- **Citra lebih tajam** — drone 5–10 cm membuat pusat tajuk terlihat tegas, dan detektor sederhana pun cukup.
- **Ground truth lapangan** — sekaligus mengubah `lattice_rmse_m` dari metrik pembanding jadi ukuran galat mutlak.
