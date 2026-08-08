-- Kategori vigor per pohon (relatif terhadap tetangga di persil yang sama).
ALTER TABLE analytics.tree ADD COLUMN IF NOT EXISTS category text;

CREATE INDEX IF NOT EXISTS tree_category_idx ON analytics.tree (land_parcel_pk, category);
