"""Kategorisasi kesehatan pohon dari titik yang SUDAH diregistrasi.

Dijalankan setelah posisi titik dipastikan manusia. Urutan ini penting:
menilai sehat/lemah/kosong dari citra sebelum posisinya benar hanya
menyebarkan kesalahan posisi ke dalam angka kesehatan — titik yang meleset
ke sela antar tajuk terbaca pucat, lalu pohon sehat tervonis mati, dan
kesalahan itu tampak meyakinkan karena sudah berbentuk angka.

Kategori bersifat **relatif terhadap tetangga di lahan yang sama**, memakai
ambang sebaran (MAD) bukan peringkat persentil. Peringkat persentil selalu
menghasilkan proporsi tetap, sehingga kebun yang seragam sehat dan kebun
yang banyak mati akan tampak sama persis.
"""

import json

import numpy as np
from psycopg.rows import dict_row
from scipy.ndimage import gaussian_filter

from mla import imagery
from mla.tree_count import resolve_parcel
from mla.tree_detect import bounds_of, parcel_mask
from mla.tree_grid import METHOD, greenness

VIGOR_VERSION = "vigor_mad/v1"

SAMPLE_RADIUS_M = 1.75   # jari-jari cakram contoh di sekitar titik (m)
CAT_EMPTY_MAD = 3.0      # di bawah median - 3,0 MAD -> kosong/mati
CAT_WEAK_MAD = 1.5       # di bawah median - 1,5 MAD -> lemah


class NoPoints(Exception):
    """Belum ada titik teregistrasi untuk lahan ini."""


def _disk_offsets(radius_px: float):
    r = int(np.ceil(radius_px))
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    keep = (dy ** 2 + dx ** 2) <= radius_px ** 2
    return dy[keep], dx[keep]


def categorize(prod, local, ident: str, method: str = METHOD) -> dict:
    """Beri kategori vigor pada semua titik teregistrasi di satu lahan."""
    parcel = resolve_parcel(prod, ident)
    with local.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT id, ST_X(geom) AS lon, ST_Y(geom) AS lat, model_version
               FROM analytics.tree
               WHERE land_parcel_pk = %s AND method = %s
               ORDER BY id""",
            (parcel["id"], method),
        )
        rows = cur.fetchall()
    if not rows:
        raise NoPoints("Belum ada titik teregistrasi untuk lahan ini")

    geometry = parcel["geometry"]
    bounds = bounds_of(geometry)
    img = imagery.fetch_parcel_image(bounds)
    mpp = imagery.meters_per_pixel((bounds[1] + bounds[3]) / 2, img.z)
    mask = parcel_mask(img, geometry)
    green = gaussian_filter(greenness(img.rgb), sigma=max(1.0, 0.5 / mpp))

    h, w = green.shape
    dy, dx = _disk_offsets(SAMPLE_RADIUS_M / mpp)
    vals = np.empty(len(rows))
    for i, r in enumerate(rows):
        x, y = img.to_colrow(r["lon"], r["lat"])
        rr = np.clip(int(round(y)) + dy, 0, h - 1)
        cc = np.clip(int(round(x)) + dx, 0, w - 1)
        # rata-rata cakram seukuran tajuk, bukan satu pixel — jauh lebih stabil
        vals[i] = float(green[rr, cc].mean())

    median = float(np.median(vals))
    mad = float(np.median(np.abs(vals - median))) or 1e-6
    z = (vals - median) / mad
    cats = np.where(z < -CAT_EMPTY_MAD, "kosong",
                    np.where(z < -CAT_WEAK_MAD, "lemah", "sehat"))
    scores = np.clip((z + 4.0) / 8.0, 0.0, 1.0)

    with local.cursor() as cur:
        cur.executemany(
            "UPDATE analytics.tree SET score = %s, category = %s WHERE id = %s",
            [(float(s), str(c), r["id"]) for s, c, r in zip(scores, cats, rows)],
        )
        # perbarui ringkasan kategori pada baris agregat versi terkait
        counts = {c: int((cats == c).sum()) for c in ("sehat", "lemah", "kosong")}
        for ver in {r["model_version"] for r in rows}:
            cur.execute(
                """UPDATE analytics.tree_count
                   SET tree_count = %s,
                       params = params || %s::jsonb,
                       computed_at = now()
                   WHERE land_parcel_pk = %s AND method = %s AND model_version = %s""",
                (len(rows),
                 json.dumps({"kategori": counts, "vigor_version": VIGOR_VERSION,
                             "vigor_sample_radius_m": SAMPLE_RADIUS_M,
                             "categorized_from": "titik teregistrasi"}),
                 parcel["id"], method, ver),
            )
    local.commit()

    return {
        "parcel_id": parcel["parcel_id"],
        "n_points": len(rows),
        "kategori": counts,
        "vigor_version": VIGOR_VERSION,
        "image_source": img.source,
        "zoom": img.z,
        "median_greenness": round(median, 2),
        "mad": round(mad, 3),
    }
