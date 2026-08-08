-- Schema hasil analisa. DB lokal mis_analytics — mis-prod tidak pernah ditulis.
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.tree_count (
    id             bigserial PRIMARY KEY,
    land_parcel_pk text        NOT NULL,  -- tbl_land_parcel.id di mis-prod
    parcel_id      text        NOT NULL,  -- ID lahan (business key)
    method         text        NOT NULL,  -- 'baseline_density' | 'detection_esri' | ...
    model_version  text        NOT NULL,
    image_date     date,                  -- NULL untuk baseline (tanpa citra)
    tree_count     integer     NOT NULL,
    sph_used       numeric,               -- kerapatan yang dipakai (pohon/ha)
    area_ha        numeric     NOT NULL,
    confidence     text        NOT NULL,  -- 'low' | 'medium' | 'high'
    params         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    computed_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (land_parcel_pk, method)
);

CREATE INDEX IF NOT EXISTS tree_count_parcel_id_idx ON analytics.tree_count (parcel_id);
