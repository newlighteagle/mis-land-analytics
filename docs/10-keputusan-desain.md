# Keputusan desain

Catatan keputusan beserta alasannya, supaya tidak dibongkar tanpa sadar konteksnya.

## 1. `mis-prod` read-only, ditegakkan di level koneksi

Schema prod milik Prisma/`mis-dashboard`; menulis dari sini berisiko bentrok migrasi dan merusak data produksi. Bukan sekadar konvensi: `prod_conn()` menjalankan `SET default_transaction_read_only = on`, sehingga penulisan tak sengaja gagal keras.

## 2. Hasil analisa di database lokal terpisah (`mis_analytics`)

Konsekuensi dari #1. Bonus: bebas menambah schema/tabel/PostGIS tanpa koordinasi dengan tim MIS.

## 3. By-request per persil, bukan batch

±10.950 persil kecil (rata-rata 1,55 ha); yang dibutuhkan pengguna adalah analisa on-demand saat meninjau satu lahan, bukan pipeline batch yang harus dijaga. CLI dan dashboard memanggil fungsi modul yang sama.

## 4. Satu hasil terkini per `(persil, metode)`, upsert

`UNIQUE (land_parcel_pk, method)` + `ON CONFLICT DO UPDATE`. Menjalankan ulang tidak menumpuk baris. Trade-off yang disadari: tidak ada riwayat antar-run untuk metode yang sama — jika kelak perlu time-series (mis. NDVI bulanan), tabel modul itu harus memakai kunci berbeda (mis. + `image_date`).

## 5. Hasil tree counting kelak per pohon, bukan hanya agregat

Modul kesehatan dan HPT butuh identitas per pohon (pohon yang sama dipantau antar-waktu). Maka saat modul deteksi dibuat, hasil disimpan di tabel titik per pohon; `analytics.tree_count` tetap sebagai agregat.

## 6. Setiap hasil membawa metode + versi model + tanggal citra + params

Supaya hasil bisa direproduksi dan dibandingkan antar-metode/versi. `area_ha` dan `crop_type` juga di-snapshot ke hasil — nilai di prod bisa berubah, hasil analisa tidak boleh ikut "bergeser".

## 7. Resolve persil via PK saat `parcel_id` ganda

`parcel_id` tidak 100% unik (±20 duplikat aktif). Daripada diam-diam memilih salah satu, kode melempar `AmbiguousParcel` dan memaksa pengguna memilih PK. API dashboard sepenuhnya memakai PK.

## 8. `parcel_id` di-denormalisasi ke tabel hasil

Query dan tampilan hasil tidak perlu join balik ke prod hanya untuk menampilkan ID lahan.

## 9. Dashboard satu file tanpa build step

Prototipe internal satu pengguna; MapLibre + fetch polos cukup. Tidak ada framework/bundler = tidak ada biaya pemeliharaan toolchain.

## 10. SPH default 136, bisa di-override per request

136 pohon/ha = jarak tanam 9,2 m segitiga (praktik umum sawit). Kebun swadaya tidak seragam, jadi angka ini default yang bisa diganti, bukan konstanta keras. Sumber nilai dicatat di `params.sph_source`.
