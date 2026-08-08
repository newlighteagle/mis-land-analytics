-- Riwayat percobaan model: satu baris per (persil, versi model, waktu jalan).
-- Dipakai membandingkan versi model secara adil memakai metrik yang sama.
CREATE TABLE IF NOT EXISTS analytics.model_run (
    id             bigserial PRIMARY KEY,
    land_parcel_pk text        NOT NULL,
    parcel_id      text        NOT NULL,
    module         text        NOT NULL,   -- 'tree_grid' | ...
    model_version  text        NOT NULL,   -- mis. 'lattice_fit/v3'
    variant        text,                   -- nama percobaan detektor
    n_points       integer     NOT NULL,
    metrics        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    params         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    ran_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS model_run_lookup_idx
    ON analytics.model_run (land_parcel_pk, module, ran_at DESC);
CREATE INDEX IF NOT EXISTS model_run_version_idx
    ON analytics.model_run (model_version, variant);
