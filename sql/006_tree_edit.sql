-- Registrasi titik: titik hasil model bisa digeser/ditambah/dihapus manusia.
-- Asal-usul tiap titik dilacak supaya hasil koreksi bisa dipakai sebagai data
-- latih, dan supaya jelas mana angka model dan mana angka hasil verifikasi.
ALTER TABLE analytics.tree ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'auto';
ALTER TABLE analytics.tree ADD COLUMN IF NOT EXISTS edited_at timestamptz;

-- 'auto'     : draf dari model, belum disentuh
-- 'moved'    : posisi digeser manusia
-- 'added'    : ditambahkan manusia (model melewatkannya)
-- 'verified' : diperiksa manusia dan dinyatakan sudah benar
CREATE INDEX IF NOT EXISTS tree_source_idx ON analytics.tree (land_parcel_pk, source);
