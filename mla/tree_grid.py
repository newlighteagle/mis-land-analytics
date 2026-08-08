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
from scipy.spatial import cKDTree
from skimage.feature import peak_local_max

from mla import crown, imagery
from mla.tree_count import resolve_parcel
from mla.tree_detect import NoImagery, bounds_of, parcel_mask, rings_of

METHOD = "grid_fit"
# v4: keluaran gabungan - tiap tajuk terdeteksi selalu ikut, simpul kisi
# tanpa tajuk ditambahkan sebagai posisi kosong (v3 membuang 24 tajuk/persil)
GRID_VERSION = "lattice_fit/v4"
CROWN_RADIUS_M = 3.5   # jari-jari tajuk sawit dewasa (m)

MIN_SPACING_M = 6.0    # rentang jarak tanam yang dianggap masuk akal
MAX_SPACING_M = 13.0
PHASE_STEPS = 24       # resolusi pencarian fase per sumbu kisi
CROWN_SIGMA_M = 1.0    # skala penghalusan untuk mencari puncak mahkota (m)
CAND_MIN_DIST = 0.45   # jarak minimum antar kandidat mahkota, x jarak tanam
MATCH_RADIUS = 0.40    # toleransi pencocokan titik kisi <-> kandidat, x jarak tanam

# Ambang vigor untuk titik yang BERHASIL dicocokkan ke mahkota, dalam satuan
# MAD di bawah median. Sengaja bukan peringkat persentil: persentil selalu
# menghasilkan proporsi tetap (10% terbawah selalu 10%), sehingga kebun seragam
# sehat dan kebun banyak kosong akan tampak sama persis.
CAT_WEAK_MAD = 2.0
CATEGORIES = ("unknown", "kosong", "lemah", "sehat")

# Draf sengaja TIDAK dikategorikan. Tahap registrasi hanya memastikan lokasi
# pohon; menilai sehat/lemah/kosong dari citra sebelum posisinya benar hanya
# menyebarkan kesalahan posisi ke dalam angka kesehatan. Skor vigor tetap
# dihitung dan disimpan supaya bisa dipakai saat tahap kategorisasi nanti.
DRAFT_CATEGORY = "unknown"

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
    """Respons mahkota: band-pass pada skala mahkota.

    Mahkota bisa lebih gelap dari sela (kanopi dewasa di tanah terang) atau
    lebih terang (sawit muda di tanah gundul), jadi kedua polaritas dicoba
    dan yang kontrasnya lebih kuat pada kisi yang dipakai.
    """
    gray = rgb.astype(np.float32).mean(axis=2)
    sm = gaussian_filter(gray, sigma=sigma_px)
    return sm - gaussian_filter(gray, sigma=sigma_px * 4)


def crown_candidates(green, mask, spacing_px, sigma_px):
    """Puncak lokal peta kehijauan = calon posisi mahkota nyata.

    Ini yang jadi acuan posisi, bukan tebakan respons: tiap kandidat adalah
    titik di citra yang memang paling hijau di lingkungannya.
    """
    cm = gaussian_filter(green, sigma=sigma_px)
    pk = peak_local_max(cm, min_distance=max(2, int(CAND_MIN_DIST * spacing_px)),
                        labels=mask, exclude_border=False)
    return pk[:, ::-1].astype(float), cm      # -> (x, y)


def match_to_candidates(pts, cand, radius_px):
    """Cocokkan tiap titik kisi ke kandidat mahkota terdekat dalam radius.

    Return (titik hasil, ketemu, jarak). Titik yang tidak menemukan kandidat
    tetap di posisi kisinya — itu justru sinyal: di posisi tanam tersebut tidak
    ada mahkota yang menonjol.
    """
    if len(cand) == 0:
        return pts, np.zeros(pts.shape[1], bool), np.full(pts.shape[1], np.inf)
    tree = cKDTree(cand)
    dist, idx = tree.query(pts.T, k=1)
    hit = dist <= radius_px
    out = pts.copy()
    out[:, hit] = cand[idx[hit]].T
    return out, hit, dist


def union_points(nodes, cand, mask, radius_px):
    """Gabungkan tajuk terdeteksi dengan simpul kisi yang kosong.

    Keluaran versi sebelumnya digerakkan oleh kisi: jumlah titik = jumlah
    simpul kisi, sehingga tajuk nyata yang tidak sejajar simpul mana pun
    ikut terbuang (terukur 24 tajuk hilang di satu persil). Di sini
    keluarannya gabungan:

      - tiap kandidat tajuk SELALU jadi titik (posisi dari citra),
      - simpul kisi tanpa kandidat ditambahkan sebagai posisi tanam kosong.

    Jadi tidak ada tajuk terdeteksi yang hilang, dan posisi tanam yang
    kehilangan pohon tetap terlaporkan.
    """
    h, w = mask.shape
    if len(cand) == 0:
        return nodes, np.zeros(nodes.shape[1], bool), np.full(nodes.shape[1], np.inf)

    cand_in = cand[mask[np.clip(cand[:, 1].astype(int), 0, h - 1),
                        np.clip(cand[:, 0].astype(int), 0, w - 1)]]
    if len(cand_in) == 0:
        return nodes, np.zeros(nodes.shape[1], bool), np.full(nodes.shape[1], np.inf)

    tree = cKDTree(cand_in)
    dist, _ = tree.query(nodes.T, k=1)
    empty = nodes[:, dist > radius_px]          # simpul tanpa tajuk

    pts = np.hstack([cand_in.T, empty])
    hit = np.concatenate([np.ones(len(cand_in), bool), np.zeros(empty.shape[1], bool)])
    d = np.concatenate([np.zeros(len(cand_in)), np.full(empty.shape[1], np.inf)])
    return pts, hit, d


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


def greenness(rgb: np.ndarray) -> np.ndarray:
    """Indeks kehijauan visible-band (2G - R - B), dihaluskan tipis."""
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    return gaussian_filter(2.0 * g - r - b, sigma=1.0)


def _best_phase(response, mask, lat):
    """Fase kisi dengan respons rata-rata tertinggi (untuk polaritas apa adanya)."""
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
            if best is None or score > best[0]:
                best = (score, origin)
    return best


def fit_phase_local(mask, lat, cand, match_px, block_cells=4):
    """Fase kisi dicari ULANG per blok, bukan satu fase untuk seluruh persil.

    Barisan tanam di kebun swadaya melengkung dan bergeser; kisi kaku satu
    fase memaksa titik meleset di ujung-ujung persil. Terukur: rmse ke kisi
    turun dari 2,50 m (fase global) ke 1,47 m (fase per blok), dan titik yang
    berada dalam 1 m naik dari 20% ke 56%.

    Offset tiap blok dicari mandiri lalu dipakai untuk membangkitkan titik
    kisi blok itu saja, sehingga kisi mengikuti lengkungan barisan.
    """
    a1, a2 = lat["a1"], lat["a2"]
    A = np.column_stack([a1, a2])
    Ainv = np.linalg.inv(A)
    tree = cKDTree(cand) if len(cand) else None

    # jangkauan indeks sel yang menutupi seluruh citra
    h, w = mask.shape
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], float).T
    mn = Ainv @ corners
    m0, m1 = int(np.floor(mn[0].min())), int(np.ceil(mn[0].max()))
    n0, n1 = int(np.floor(mn[1].min())), int(np.ceil(mn[1].max()))

    pts_all, hits_all = [], []
    for bm in range(m0, m1 + 1, block_cells):
        for bn in range(n0, n1 + 1, block_cells):
            mm, nn = np.meshgrid(np.arange(bm, min(bm + block_cells, m1 + 1)),
                                 np.arange(bn, min(bn + block_cells, n1 + 1)))
            base = a1[:, None] * mm.ravel() + a2[:, None] * nn.ravel()
            best = None
            for i in range(PHASE_STEPS):
                for j in range(PHASE_STEPS):
                    origin = a1 * (i / PHASE_STEPS) + a2 * (j / PHASE_STEPS)
                    pts = base + origin[:, None]
                    c = np.clip(pts[0].astype(int), 0, w - 1)
                    r = np.clip(pts[1].astype(int), 0, h - 1)
                    sel = mask[r, c]
                    if sel.sum() < 2:
                        continue
                    sub = pts[:, sel]
                    if tree is None:
                        score, hit = 0.0, np.zeros(sub.shape[1], bool)
                    else:
                        d, _ = tree.query(sub.T, k=1)
                        hit = d <= match_px
                        score = float(hit.mean() - 0.05 * d.mean() / match_px)
                    if best is None or score > best[0]:
                        best = (score, sub, hit)
            if best is not None:
                pts_all.append(best[1])
                hits_all.append(best[2])

    if not pts_all:
        raise NoLattice("Kisi tidak bisa dipasang di dalam persil")
    return np.hstack(pts_all), float(np.concatenate(hits_all).mean())


def fit_phase(mask, lat, cand, match_px):
    """Pilih fase kisi yang paling banyak mencocokkan kandidat mahkota.

    Kriterianya jumlah titik yang menemukan mahkota — bukan besarnya respons.
    Versi sebelumnya memakai magnitudo respons dan selalu tertarik ke bayangan
    antar mahkota, karena bayangan jauh lebih ekstrem daripada mahkotanya.
    """
    a1, a2 = lat["a1"], lat["a2"]
    tree = cKDTree(cand) if len(cand) else None
    best = None
    for i in range(PHASE_STEPS):
        for j in range(PHASE_STEPS):
            origin = a1 * (i / PHASE_STEPS) + a2 * (j / PHASE_STEPS)
            pts = _lattice_points(a1, a2, origin, mask.shape)
            cols = np.clip(pts[0].astype(int), 0, mask.shape[1] - 1)
            rows = np.clip(pts[1].astype(int), 0, mask.shape[0] - 1)
            pts = pts[:, mask[rows, cols]]
            if pts.shape[1] < 5:
                continue
            if tree is None:
                score = 0.0
            else:
                dist, _ = tree.query(pts.T, k=1)
                score = float((dist <= match_px).mean() - 0.05 * dist.mean() / match_px)
            if best is None or score > best[0]:
                best = (score, origin, pts)
    if best is None:
        raise NoLattice("Kisi tidak bisa dipasang di dalam persil")
    return best[1], best[2], best[0]


def classify(pts, hit, green, mask):
    """Skor vigor tiap titik + kategori berdasar simpangan dari median persil.

    Titik dengan kehijauan jauh di bawah median tetangganya berarti di posisi
    tanam itu tidak ada mahkota sehat — bisa pohon mati, tumbang, belum
    disulam, atau memang tidak pernah ditanam. Ambangnya memakai MAD supaya
    jumlah tiap kategori mengikuti keadaan lahan; kebun yang seragam sehat
    menghasilkan nyaris nol "kosong".

    Kategori ini indikasi vigor dari citra, **bukan diagnosis penyakit**.
    """
    h, w = green.shape
    c = np.clip(pts[0].astype(int), 0, w - 1)
    r = np.clip(pts[1].astype(int), 0, h - 1)
    vals = green[r, c].astype(np.float64)
    if len(vals) == 0:
        return np.array([]), []
    ref = vals[hit] if hit.any() else vals          # acuan = pohon yang ketemu
    median = float(np.median(ref))
    mad = float(np.median(np.abs(ref - median))) or 1e-6
    z = (vals - median) / mad                       # simpangan robust
    # 'kosong' ditentukan oleh TIDAK ADANYA mahkota di posisi tanam itu,
    # bukan oleh peringkat kehijauan — jadi kebun yang penuh bisa nol kosong.
    cats = np.where(~hit, "kosong", np.where(z < -CAT_WEAK_MAD, "lemah", "sehat"))
    vigor = np.clip((z + 4.0) / 8.0, 0.0, 1.0)
    return vigor, list(cats)


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
    green = greenness(img.rgb)

    spacing_px = min(np.linalg.norm(lat["a1"]), np.linalg.norm(lat["a2"]))
    match_px = max(2.0, MATCH_RADIUS * spacing_px)
    cand = crown.centers_obia(green, mask, spacing_px, CROWN_RADIUS_M / mpp)
    if len(cand) < 5:      # kebun tidak beraturan / tajuk tidak terpisah
        cand, _ = crown_candidates(green, mask, spacing_px,
                                   sigma_px=max(1.0, CROWN_SIGMA_M / mpp))

    nodes, score = fit_phase_local(mask, lat, cand, match_px)
    pts, hit, dist = union_points(nodes, cand, mask, match_px)

    vigor, _auto_cat = classify(pts, hit, green, mask)
    categories = [DRAFT_CATEGORY] * len(_auto_cat)
    match_rate = float(hit.mean()) if len(hit) else 0.0
    median_offset_m = float(np.median(dist[hit]) * mpp) if hit.any() else None
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
        "image_source": img.source,
        "zoom": img.z,
        "meters_per_pixel": round(mpp, 4),
        "spacing_a1_m": round(s1, 2),
        "spacing_a2_m": round(s2, 2),
        "row_angle_deg": round(lat["angle_deg"], 1),
        "cell_area_m2": round(float(cell_area_m2), 2),
        "sph_from_lattice": round(10_000.0 / cell_area_m2, 1) if cell_area_m2 else None,
        "detector": "obia_weighted",
        "n_candidates": int(len(cand)),
        "match_rate": round(match_rate, 3),
        "phase": "per-blok",
        "median_offset_m": round(median_offset_m, 2) if median_offset_m is not None else None,
        "phase_score": round(float(score), 3),
        "kategori": {c: int(categories.count(c)) for c in CATEGORIES},
        "warnings": warnings,
        "note": "posisi model dari kisi tanam terukur, bukan deteksi tiap pohon; "
                "kategori vigor bersifat relatif antar pohon di persil yang sama",
    }

    with local.cursor(row_factory=dict_row) as cur:
        # hanya hasil VERSI INI yang diganti; versi lain tetap tersimpan
        cur.execute(
            """DELETE FROM analytics.tree
               WHERE land_parcel_pk = %s AND method = %s AND model_version = %s""",
            (parcel["id"], METHOD, GRID_VERSION))
        if points:
            cur.executemany(
                """INSERT INTO analytics.tree
                     (land_parcel_pk, method, model_version, geom, score, category)
                   VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)""",
                [(parcel["id"], METHOD, GRID_VERSION, lon, lat_, float(v), c)
                 for (lon, lat_), v, c in zip(points, vigor, categories)],
            )
        cur.execute(
            """INSERT INTO analytics.tree_count
                 (land_parcel_pk, parcel_id, method, model_version, image_date,
                  tree_count, sph_used, area_ha, confidence, params)
               VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
               ON CONFLICT (land_parcel_pk, method, model_version) DO UPDATE SET
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
