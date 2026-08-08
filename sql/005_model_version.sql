-- Simpan hasil tiap versi model berdampingan, bukan saling menimpa, supaya
-- perbaikan model bisa dibandingkan langsung di dashboard.
ALTER TABLE analytics.tree ADD COLUMN IF NOT EXISTS model_version text;

UPDATE analytics.tree SET model_version = 'lattice_fit/v2' WHERE model_version IS NULL;
ALTER TABLE analytics.tree ALTER COLUMN model_version SET NOT NULL;

CREATE INDEX IF NOT EXISTS tree_version_idx
    ON analytics.tree (land_parcel_pk, method, model_version);

-- Unik per (persil, metode, VERSI) — sebelumnya per (persil, metode), yang
-- membuat versi baru menghapus hasil versi lama.
ALTER TABLE analytics.tree_count DROP CONSTRAINT IF EXISTS tree_count_land_parcel_pk_method_key;
ALTER TABLE analytics.tree_count
    ADD CONSTRAINT tree_count_parcel_method_version_key
    UNIQUE (land_parcel_pk, method, model_version);
