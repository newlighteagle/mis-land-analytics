-- Reset hasil analisa pada titik: score, kategori, dan penanda versi model
-- dikosongkan. model_version boleh NULL supaya titik yang sudah diregistrasi
-- manusia tidak lagi mengaku sebagai keluaran model tertentu.
ALTER TABLE analytics.tree ALTER COLUMN model_version DROP NOT NULL;
