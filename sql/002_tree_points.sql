-- Titik per pohon hasil deteksi dari citra. Satu run deteksi mengganti
-- seluruh titik persil untuk method yang sama (delete + insert).
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS analytics.tree (
    id             bigserial PRIMARY KEY,
    land_parcel_pk text        NOT NULL,      -- tbl_land_parcel.id di mis-prod
    method         text        NOT NULL,      -- 'detection_esri' | ...
    geom           geometry(Point, 4326) NOT NULL,
    score          real,                      -- kekuatan puncak deteksi (relatif)
    detected_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tree_parcel_method_idx ON analytics.tree (land_parcel_pk, method);
CREATE INDEX IF NOT EXISTS tree_geom_idx ON analytics.tree USING gist (geom);
