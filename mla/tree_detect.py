"""Deteksi per pohon dari citra resolusi tinggi.

Metode v1: local_maxima — mahkota sawit tampak sebagai gundukan hijau terang
yang terpisah bayangan. Citra dihaluskan pada skala radius mahkota, lalu
puncak lokal dicari dengan jarak minimum dari asumsi jarak tanam. Hasil
per pohon disimpan sebagai titik; agregatnya diupsert ke analytics.tree_count
dengan method terpisah supaya bisa dibandingkan dengan baseline kerapatan.
"""

import json
import math

import numpy as np
from PIL import Image, ImageDraw
from psycopg.rows import dict_row
from scipy.ndimage import gaussian_filter
from skimage.feature import peak_local_max

from mla import imagery
from mla.tree_count import resolve_parcel

METHOD = "detection_esri"
DETECT_VERSION = "local_maxima/v1"

CROWN_RADIUS_M = 3.5      # radius mahkota sawit dewasa (m)
MIN_DIST_FACTOR = 0.8     # jarak minimum antar puncak = faktor x jarak tanam
PEAK_PERCENTILE = 40.0    # puncak di bawah persentil respons ini dibuang


class NoImagery(Exception):
    pass


def rings_of(geometry: dict) -> list[list]:
    """Semua ring luar dari Polygon / MultiPolygon GeoJSON."""
    t = geometry.get("type")
    if t == "Polygon":
        return [geometry["coordinates"][0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    raise ValueError(f"Tipe geometri tidak didukung: {t}")


def bounds_of(geometry: dict) -> tuple:
    xs, ys = [], []
    for ring in rings_of(geometry):
        for lon, lat in ring:
            xs.append(lon)
            ys.append(lat)
    return min(xs), min(ys), max(xs), max(ys)


def spacing_m(sph: float) -> float:
    """Jarak tanam (m) untuk pola segitiga pada kerapatan sph pohon/ha."""
    area_per_palm = 10_000.0 / sph
    return math.sqrt(2.0 * area_per_palm / math.sqrt(3.0))


def parcel_mask(img, geometry: dict) -> np.ndarray:
    """Mask boolean: True di dalam poligon persil."""
    h, w = img.rgb.shape[:2]
    canvas = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(canvas)
    for ring in rings_of(geometry):
        pts = [img.to_colrow(lon, lat) for lon, lat in ring]
        draw.polygon(pts, fill=1)
    return np.asarray(canvas, dtype=bool)


def crown_response(rgb: np.ndarray, sigma_px: float) -> np.ndarray:
    """Respons kehijauan yang dihaluskan pada skala mahkota."""
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    green = 2.0 * g - r - b          # indeks kehijauan visible-band
    return gaussian_filter(green, sigma=sigma_px)


def detect(prod, local, ident: str, sph: float | None = None) -> dict:
    parcel = resolve_parcel(prod, ident)
    geometry = parcel["geometry"]
    if not geometry:
        raise ValueError("Persil tidak punya geometri")

    from mla.tree_count import DEFAULT_SPH
    sph_assumed = float(sph) if sph else DEFAULT_SPH
    bounds = bounds_of(geometry)

    try:
        img = imagery.fetch_parcel_image(bounds)
    except RuntimeError as e:
        raise NoImagery(str(e)) from e

    center_lat = (bounds[1] + bounds[3]) / 2.0
    mpp = imagery.meters_per_pixel(center_lat, img.z)
    sigma_px = max(1.0, CROWN_RADIUS_M / 2.0 / mpp)
    min_dist_px = max(2, int(round(MIN_DIST_FACTOR * spacing_m(sph_assumed) / mpp)))

    mask = parcel_mask(img, geometry)
    response = crown_response(img.rgb, sigma_px)
    # Respons kehijauan berpusat di sekitar nol dengan rentang sempit, jadi
    # ambang harus absolut dari distribusi di dalam persil — threshold_rel
    # (relatif terhadap puncak tertinggi) akan membuang hampir semua puncak.
    threshold_abs = float(np.percentile(response[mask], PEAK_PERCENTILE))
    peaks = peak_local_max(
        response, min_distance=min_dist_px, labels=mask,
        threshold_abs=threshold_abs, exclude_border=False,
    )

    lo, hi = float(response[mask].min()), float(response[mask].max())
    span = (hi - lo) or 1.0
    points = []
    for row, col in peaks:
        lon, lat = img.to_lonlat(float(col), float(row))
        points.append((lon, lat, float((response[row, col] - lo) / span)))

    area_ha = float(parcel["area"])
    params = {
        "image_source": img.source,
        "zoom": img.z,
        "meters_per_pixel": round(mpp, 4),
        "sph_assumed": sph_assumed,
        "spacing_m_assumed": round(spacing_m(sph_assumed), 2),
        "crown_radius_m": CROWN_RADIUS_M,
        "min_distance_px": min_dist_px,
        "peak_percentile": PEAK_PERCENTILE,
        "detected_sph": round(len(points) / area_ha, 1) if area_ha else None,
        "image_px": [int(img.rgb.shape[1]), int(img.rgb.shape[0])],
    }

    with local.cursor(row_factory=dict_row) as cur:
        cur.execute("DELETE FROM analytics.tree WHERE land_parcel_pk = %s AND method = %s",
                    (parcel["id"], METHOD))
        if points:
            cur.executemany(
                """INSERT INTO analytics.tree (land_parcel_pk, method, geom, score)
                   VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s)""",
                [(parcel["id"], METHOD, lon, lat, score) for lon, lat, score in points],
            )
        cur.execute(
            """INSERT INTO analytics.tree_count
                 (land_parcel_pk, parcel_id, method, model_version, image_date,
                  tree_count, sph_used, area_ha, confidence, params)
               VALUES (%s, %s, %s, %s, NULL, %s, NULL, %s, 'medium', %s)
               ON CONFLICT (land_parcel_pk, method) DO UPDATE SET
                 model_version = EXCLUDED.model_version,
                 tree_count    = EXCLUDED.tree_count,
                 area_ha       = EXCLUDED.area_ha,
                 confidence    = EXCLUDED.confidence,
                 params        = EXCLUDED.params,
                 computed_at   = now()
               RETURNING *""",
            (parcel["id"], parcel["parcel_id"], METHOD, DETECT_VERSION,
             len(points), area_ha, json.dumps(params)),
        )
        row = cur.fetchone()
    local.commit()

    row["computed_at"] = row["computed_at"].isoformat()
    row["area_ha"] = float(row["area_ha"])
    row["sph_used"] = float(row["sph_used"]) if row["sph_used"] is not None else None
    return row


def points_for(local, land_parcel_pk: str, method: str = METHOD,
               model_version: str | None = None) -> dict:
    """Titik pohon sebagai GeoJSON FeatureCollection.

    Tanpa `model_version`, dipakai versi terbaru yang tersedia untuk persil
    itu — hasil versi lama tetap tersimpan dan bisa diminta secara eksplisit.
    """
    with local.cursor(row_factory=dict_row) as cur:
        if model_version is None:
            cur.execute(
                """SELECT model_version FROM analytics.tree
                   WHERE land_parcel_pk = %s AND method = %s
                   ORDER BY model_version DESC LIMIT 1""",
                (land_parcel_pk, method),
            )
            row = cur.fetchone()
            if not row:
                return {"type": "FeatureCollection", "features": []}
            model_version = row["model_version"]
        cur.execute(
            """SELECT id, ST_X(geom) AS lon, ST_Y(geom) AS lat, score, category, source
               FROM analytics.tree
               WHERE land_parcel_pk = %s AND method = %s AND model_version = %s
               ORDER BY id""",
            (land_parcel_pk, method, model_version),
        )
        rows = cur.fetchall()
    return {
        "type": "FeatureCollection",
        "model_version": model_version,
        "features": [
            {"type": "Feature",
             "properties": {"id": r["id"], "no": i + 1,
                            "score": round(r["score"], 3) if r["score"] is not None else None,
                            "category": r["category"], "source": r["source"],
                            "lon": round(r["lon"], 6), "lat": round(r["lat"], 6)},
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]}}
            for i, r in enumerate(rows)
        ],
    }
