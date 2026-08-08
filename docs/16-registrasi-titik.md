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

## Rencana lanjutan

- **Ekspor data latih** dari titik `moved`/`added`/`verified` untuk melatih detektor CNN.
- **Ukur galat mutlak** model dengan membandingkan draf terhadap titik hasil registrasi pada lahan yang sama.
- **Tandai lahan selesai registrasi** supaya laporan bisa memisahkan angka terverifikasi dari angka draf.
