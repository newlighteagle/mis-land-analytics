"""Posisi pohon dari fitting kisi tanam (lattice fitting).

Latar: deteksi puncak lokal per mahkota gagal pada citra 0,6 m/px
(lihat docs/12), TAPI periodisitas tanam terbaca sangat kuat di spektrum
daya. Modul ini memanfaatkan prior itu: ukur kisi tanam (jarak + arah)
dari FFT, lalu pasang kisi tersebut pada citra dengan fase yang paling
cocok, dan ambil titik kisi di dalam persil sebagai posisi pohon.

Hasilnya adalah **posisi model**, bukan deteksi tiap pohon: titik mengikuti
pola tanam terukur, jadi akurat di kebun yang teratur dan meleset di bagian
yang kosong/tidak beraturan. Jumlahnya dilaporkan sebagai jumlah titik kisi
di dalam poligon.
"""

import json

import numpy as np
from PIL import Image, ImageDraw
from psycopg.rows import dict_row
from scipy.ndimage import gaussian_filter

from mla import imagery
from mla.tree_count import resolve_parcel
from mla.tree_detect import NoImagery, bounds_of, parcel_mask, rings_of

METHOD = "grid_fit"
GRID_VERSION = "lattice_fit/v1"

MIN_SPACING_M = 6.0    # rentang jarak tanam yang dianggap masuk akal
MAX_SPACING_M = 13.0
PHASE_STEPS = 12       # resolusi pencarian fase per sumbu kisi

# Rentang jarak tanam sawit yang lazim di lapangan (SPH ~110-180). Di luar ini
# biasanya basis kisi yang terpilih bukan yang primitif — mis. diagonal kisi
# persegi (9,2 x sqrt2 = 13,0 m) yang membuat SPH tampak setengahnya.
PLAUSIBLE_SPACING = (7.5, 11.0)
MAX_AXIS_RATIO = 1.35  # kedua sumbu mestinya mirip panjangnya


class NoLattice(Exception):
    """Pola tanam periodik tidak terbaca (kebun tidak beraturan / citra buruk)."""


def _detrended_patch(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Patch persegi terbesar di dalam mask, tanpa gradien besar, ber-window."""
    ys, xs = np.where(mask)
    y0, y1 = ys.min() + 8, ys.max() - 8
    x0, x1 = xs.min() + 8, xs.max() - 8
    if y1 - y0 < 32 or x1 - x0 < 32:
        raise NoLattice("Persil terlalu kecil untuk analisis spektral")
    patch = rgb[y0:y1, x0:x1].astype(np.float32).mean(axis=2)
    patch = patch - gaussian_filter(patch, sigma=12)
    win = np.hanning(patch.shape[0])[:, None] * np.hanning(patch.shape[1])[None, :]
    return patch * win


def _spectral_peaks(patch: np.ndarray, mpp: float, n: int = 12):
    """Puncak spektrum daya dalam rentang jarak tanam yang masuk akal.

    Return list (freq_vector_px, power) terurut daya menurun. Frekuensi dalam
    siklus per pixel, sebagai vektor (fx, fy).
    """
    P = np.fft.fftshift(np.abs(np.fft.fft2(patch)) ** 2)
    h, w = patch.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.indices(P.shape)
    fy = (yy - cy) / h
    fx = (xx - cx) / w
    freq = np.sqrt(fx ** 2 + fy ** 2)
    with np.errstate(divide="ignore"):
        spacing_m = np.where(freq > 0, 1.0 / np.maximum(freq, 1e-9) * mpp, np.inf)
    band = (spacing_m >= MIN_SPACING_M) & (spacing_m <= MAX_SPACING_M)
    if not band.any():
        raise NoLattice("Tidak ada frekuensi dalam rentang jarak tanam")

    Pb = np.where(band, P, 0.0)
    # puncak lokal sederhana: lebih besar dari tetangga 3x3
    from scipy.ndimage import maximum_filter
    is_peak = (Pb == maximum_filter(Pb, size=5)) & (Pb > 0)
    idx = np.argwhere(is_peak)
    order = np.argsort([Pb[r, c] for r, c in idx])[::-1][:n]
    return [(np.array([fx[r, c], fy[r, c]]), float(Pb[r, c]))
            for r, c in (idx[i] for i in order)]


def fit_lattice(patch: np.ndarray, mpp: float) -> dict:
    """Cari dua vektor basis kisi dari dua puncak spektral non-kolinear."""
    peaks = _spectral_peaks(patch, mpp)
    if not peaks:
        raise NoLattice("Tidak ada puncak spektral")
    b1 = peaks[0][0]
    b2 = None
    a1_deg = np.degrees(np.arctan2(b1[1], b1[0])) % 180
    for vec, _ in peaks[1:]:
        deg = np.degrees(np.arctan2(vec[1], vec[0])) % 180
        diff = abs(deg - a1_deg)
        diff = min(diff, 180 - diff)
        if 40 <= diff <= 140:            # cukup menyudut untuk jadi basis
            b2 = vec
            break
    if b2 is None:
        raise NoLattice("Hanya satu arah periodik terbaca (pola tanam tidak jelas)")

    B = np.column_stack([b1, b2])        # basis resiprokal (siklus/px)
    try:
        A = np.linalg.inv(B.T)           # basis real (px), kolom = a1, a2
    except np.linalg.LinAlgError as e:
        raise NoLattice("Basis kisi singular") from e

    a1, a2 = A[:, 0], A[:, 1]
    return {
        "a1": a1, "a2": a2,
        "spacing_a1_m": float(np.linalg.norm(a1) * mpp),
        "spacing_a2_m": float(np.linalg.norm(a2) * mpp),
        "angle_deg": float(np.degrees(np.arctan2(a1[1], a1[0])) % 180),
    }


def _crown_response(rgb: np.ndarray, sigma_px: float):
    """Respons mahkota + tandanya.

    Mahkota bisa lebih gelap dari sela (kanopi dewasa di tanah terang) atau
    lebih terang (sawit muda di tanah gundul), jadi kedua polaritas dicoba
    dan yang kontrasnya lebih kuat pada kisi yang dipakai.
    """
    gray = rgb.astype(np.float32).mean(axis=2)
    sm = gaussian_filter(gray, sigma=sigma_px)
    return sm - gaussian_filter(gray, sigma=sigma_px * 4)


def _lattice_points(a1, a2, origin, shape):
    """Semua titik kisi yang jatuh di dalam citra."""
    h, w = shape
    A = np.column_stack([a1, a2])
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], dtype=float).T
    mn = np.linalg.solve(A, corners - origin[:, None])
    m0, m1 = int(np.floor(mn[0].min())) - 1, int(np.ceil(mn[0].max())) + 1
    n0, n1 = int(np.floor(mn[1].min())) - 1, int(np.ceil(mn[1].max())) + 1
    m, n = np.meshgrid(np.arange(m0, m1 + 1), np.arange(n0, n1 + 1))
    pts = origin[:, None] + a1[:, None] * m.ravel() + a2[:, None] * n.ravel()
    inside = (pts[0] >= 0) & (pts[0] < w) & (pts[1] >= 0) & (pts[1] < h)
    return pts[:, inside]


def fit_phase(response, mask, lat):
    """Geser kisi untuk memaksimalkan |respons| rata-rata di titik kisi."""
    a1, a2 = lat["a1"], lat["a2"]
    best = None
    for i in range(PHASE_STEPS):
        for j in range(PHASE_STEPS):
            origin = a1 * (i / PHASE_STEPS) + a2 * (j / PHASE_STEPS)
            pts = _lattice_points(a1, a2, origin, mask.shape)
            cols = np.clip(pts[0].astype(int), 0, mask.shape[1] - 1)
            rows = np.clip(pts[1].astype(int), 0, mask.shape[0] - 1)
            sel = mask[rows, cols]
            if sel.sum() < 5:
                continue
            score = float(response[rows[sel], cols[sel]].mean())
            for sign in (1.0, -1.0):
                s = score * sign
                if best is None or s > best[0]:
                    best = (s, origin, sign)
    if best is None:
        raise NoLattice("Kisi tidak bisa dipasang di dalam persil")
    return best[1], best[2], best[0]


def fit(prod, local, ident: str) -> dict:
    parcel = resolve_parcel(prod, ident)
    geometry = parcel["geometry"]
    if not geometry:
        raise ValueError("Persil tidak punya geometri")

    bounds = bounds_of(geometry)
    img = imagery.fetch_parcel_image(bounds)
    mpp = imagery.meters_per_pixel((bounds[1] + bounds[3]) / 2, img.z)
    mask = parcel_mask(img, geometry)

    patch = _detrended_patch(img.rgb, mask)
    lat = fit_lattice(patch, mpp)
    response = _crown_response(img.rgb, sigma_px=max(1.0, 2.0 / mpp))
    origin, sign, score = fit_phase(response * 1.0, mask, lat)

    pts = _lattice_points(lat["a1"], lat["a2"], origin, mask.shape)
    cols = np.clip(pts[0].astype(int), 0, mask.shape[1] - 1)
    rows = np.clip(pts[1].astype(int), 0, mask.shape[0] - 1)
    sel = mask[rows, cols]
    pts = pts[:, sel]

    area_ha = float(parcel["area"])
    a1, a2 = lat["a1"], lat["a2"]
    cell_area_m2 = abs(a1[0] * a2[1] - a1[1] * a2[0]) * mpp * mpp  # luas sel kisi
    points = [img.to_lonlat(float(x), float(y)) for x, y in pts.T]

    s1, s2 = lat["spacing_a1_m"], lat["spacing_a2_m"]
    lo, hi = PLAUSIBLE_SPACING
    ratio = max(s1, s2) / min(s1, s2)
    warnings = []
    if not (lo <= s1 <= hi and lo <= s2 <= hi):
        warnings.append(f"jarak tanam di luar rentang lazim {lo}-{hi} m")
    if ratio > MAX_AXIS_RATIO:
        warnings.append(f"kedua sumbu kisi timpang (rasio {ratio:.2f})")
    confidence = "medium" if not warnings else "low"

    params = {
        "zoom": img.z,
        "meters_per_pixel": round(mpp, 4),
        "spacing_a1_m": round(s1, 2),
        "spacing_a2_m": round(s2, 2),
        "row_angle_deg": round(lat["angle_deg"], 1),
        "cell_area_m2": round(float(cell_area_m2), 2),
        "sph_from_lattice": round(10_000.0 / cell_area_m2, 1) if cell_area_m2 else None,
        "crown_polarity": "gelap" if sign < 0 else "terang",
        "phase_score": round(float(score), 3),
        "warnings": warnings,
        "note": "posisi model dari kisi tanam terukur, bukan deteksi tiap pohon",
    }

    with local.cursor(row_factory=dict_row) as cur:
        cur.execute("DELETE FROM analytics.tree WHERE land_parcel_pk = %s AND method = %s",
                    (parcel["id"], METHOD))
        if points:
            cur.executemany(
                """INSERT INTO analytics.tree (land_parcel_pk, method, geom, score)
                   VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), NULL)""",
                [(parcel["id"], METHOD, lon, lat_) for lon, lat_ in points],
            )
        cur.execute(
            """INSERT INTO analytics.tree_count
                 (land_parcel_pk, parcel_id, method, model_version, image_date,
                  tree_count, sph_used, area_ha, confidence, params)
               VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
               ON CONFLICT (land_parcel_pk, method) DO UPDATE SET
                 model_version = EXCLUDED.model_version,
                 tree_count    = EXCLUDED.tree_count,
                 sph_used      = EXCLUDED.sph_used,
                 area_ha       = EXCLUDED.area_ha,
                 confidence    = EXCLUDED.confidence,
                 params        = EXCLUDED.params,
                 computed_at   = now()
               RETURNING *""",
            (parcel["id"], parcel["parcel_id"], METHOD, GRID_VERSION, len(points),
             params["sph_from_lattice"], area_ha, confidence, json.dumps(params)),
        )
        row = cur.fetchone()
    local.commit()

    row["computed_at"] = row["computed_at"].isoformat()
    row["area_ha"] = float(row["area_ha"])
    row["sph_used"] = float(row["sph_used"]) if row["sph_used"] is not None else None
    return row
