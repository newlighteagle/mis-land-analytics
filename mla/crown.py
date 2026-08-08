"""Detektor pusat tajuk sawit + metrik akurasi posisi.

Tajuk sawit adalah bintang: pelepah memancar dari satu titik pusat. Itu
struktur **simetri radial**, dan Fast Radial Symmetry Transform (FRST,
Loy & Zelinsky 2003) memang dirancang untuk menemukan pusat struktur
semacam itu — jauh lebih tepat daripada mencari puncak kehijauan, yang
gampang tertarik ke pelepah alih-alih ke pusatnya.

Modul ini juga menyediakan detektor pembanding yang **independen** (jarak
dari celah gelap antar tajuk) supaya akurasi posisi bisa diukur lewat
kesepakatan dua metode yang tidak berbagi asumsi.
"""

import numpy as np
from scipy.ndimage import (distance_transform_edt, gaussian_filter,
                           maximum_filter, sobel)
from scipy.spatial import cKDTree
from skimage.feature import peak_local_max


def frst(gray, radii_px, alpha=2.0, beta=0.2, bright=True):
    """Fast Radial Symmetry Transform.

    Return peta simetri radial: nilai tinggi = titik yang dikelilingi
    gradien mengarah ke sana secara merata dari segala arah, yaitu pusat
    struktur memancar seperti tajuk sawit.
    """
    gy = sobel(gray, axis=0)
    gx = sobel(gray, axis=1)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    thr = beta * mag.max()
    strong = mag > thr
    if not strong.any():
        return np.zeros_like(gray)

    ys, xs = np.nonzero(strong)
    ux = (gx[ys, xs] / mag[ys, xs])
    uy = (gy[ys, xs] / mag[ys, xs])
    m = mag[ys, xs]
    h, w = gray.shape
    total = np.zeros((h, w), np.float32)

    sign = 1.0 if bright else -1.0
    for n in radii_px:
        O = np.zeros((h, w), np.float32)
        M = np.zeros((h, w), np.float32)
        py = np.clip((ys + sign * n * uy).astype(np.int32), 0, h - 1)
        px = np.clip((xs + sign * n * ux).astype(np.int32), 0, w - 1)
        np.add.at(O, (py, px), 1.0)
        np.add.at(M, (py, px), m)
        kappa = 9.9 if n > 1 else 8.0
        F = (np.abs(O) / kappa) ** alpha * (M / kappa)
        total += gaussian_filter(F, sigma=max(0.5, 0.25 * n))
    return total / len(radii_px)


def centers_frst(gray, mask, spacing_px, crown_radius_px, min_dist_frac=0.45):
    """Pusat tajuk dari FRST, dicari pada beberapa radius sekitar jari-jari tajuk."""
    radii = [max(2, int(round(crown_radius_px * f))) for f in (0.5, 0.75, 1.0)]
    S = frst(gray.astype(np.float32), radii, bright=True)
    S = np.where(mask, S, 0.0)
    pk = peak_local_max(S, min_distance=max(2, int(min_dist_frac * spacing_px)),
                        labels=mask, exclude_border=False)
    return pk[:, ::-1].astype(float), S      # -> (x, y)


def centers_gap_distance(gray, mask, spacing_px, dark_pct=35.0):
    """Detektor PEMBANDING yang independen: titik terjauh dari celah gelap.

    Tidak memakai gradien maupun kehijauan, jadi kesalahannya tidak
    berkorelasi dengan FRST — cocok sebagai acuan silang.
    """
    sm = gaussian_filter(gray.astype(np.float32), sigma=2.0)
    thr = np.percentile(sm[mask], dark_pct)
    dist = gaussian_filter(distance_transform_edt(sm >= thr), sigma=1.5)
    dist = np.where(mask, dist, 0.0)
    pk = peak_local_max(dist, min_distance=max(2, int(0.5 * spacing_px)),
                        labels=mask, exclude_border=False)
    return pk[:, ::-1].astype(float)


def centers_obia(green, mask, spacing_px, crown_radius_px, weighted=True):
    """OBIA: segmentasi tajuk (watershed) lalu ambil pusat massa tiap objek.

    Pendekatan berbasis objek, bukan titik — batas antar tajuk ditentukan
    lewat celah gelap, sehingga posisi tidak ditentukan satu pixel puncak
    yang gampang tergeser oleh rumpun pelepah. Pusat massa dibobot kehijauan
    supaya tertarik ke bagian tajuk yang paling rimbun.

    Terukur paling baik pada kriteria "titik dalam 1 m dari posisi kisi
    lokal": 63-64% vs 56% untuk puncak kehijauan dan 7% untuk titik acak.
    """
    from skimage.measure import regionprops
    from skimage.segmentation import watershed

    sm = gaussian_filter(green.astype(np.float32), sigma=max(1.0, 0.3 * crown_radius_px))
    pk = peak_local_max(sm, min_distance=max(2, int(0.45 * spacing_px)),
                        labels=mask, exclude_border=False)
    if len(pk) < 5:
        return np.empty((0, 2))
    markers = np.zeros(sm.shape, np.int32)
    markers[tuple(pk.T)] = np.arange(1, len(pk) + 1)
    labels = watershed(-sm, markers, mask=mask)

    cell_px = 0.866 * spacing_px ** 2
    w = np.clip(sm - sm[mask].min(), 0, None) if weighted else None
    cents = []
    for r in regionprops(labels, intensity_image=w):
        # buang segmen yang luasnya jauh menyimpang dari luas sel tanam
        if not (0.25 * cell_px <= r.area <= 2.5 * cell_px):
            continue
        cy, cx = r.centroid_weighted if weighted else r.centroid
        cents.append((cx, cy))
    return np.array(cents, float) if cents else np.empty((0, 2))


def position_metrics(pts, gray, mask, spacing_px, crown_radius_px, mpp):
    """Kuantifikasi seberapa tepat titik berada di pusat tajuk.

    Semua metrik dihitung dari citra, tidak memakai kisi maupun proses fit,
    sehingga bisa dipakai membandingkan versi model secara adil.

    - `symmetry_pct`  : persentil nilai simetri radial di titik, terhadap
      seluruh pixel di dalam persil. 50 = setara titik acak, 100 = persis
      di puncak simetri. Ini ukuran utama "di pusat tajuk atau tidak".
    - `xmethod_offset_m` : jarak median ke pusat tajuk versi detektor
      pembanding yang independen.
    - `xmethod_within_1m`/`_2m` : proporsi titik yang sepakat dalam 1 m / 2 m.
    """
    radii = [max(2, int(round(crown_radius_px * f))) for f in (0.5, 0.75, 1.0)]
    S = frst(gray.astype(np.float32), radii, bright=True)
    inside = S[mask]
    order = np.sort(inside)

    c = np.clip(pts[0].astype(int), 0, gray.shape[1] - 1)
    r = np.clip(pts[1].astype(int), 0, gray.shape[0] - 1)
    vals = S[r, c]
    pct = np.searchsorted(order, vals) / max(len(order), 1) * 100.0

    ref = centers_gap_distance(gray, mask, spacing_px)
    if len(ref):
        d, _ = cKDTree(ref).query(pts.T, k=1)
        d_m = d * mpp
    else:
        d_m = np.full(pts.shape[1], np.nan)

    return {
        "symmetry_pct": round(float(np.median(pct)), 1),
        "symmetry_pct_mean": round(float(np.mean(pct)), 1),
        "xmethod_offset_m": round(float(np.nanmedian(d_m)), 2),
        "xmethod_within_1m": round(float(np.nanmean(d_m <= 1.0)), 3),
        "xmethod_within_2m": round(float(np.nanmean(d_m <= 2.0)), 3),
        "n_points": int(pts.shape[1]),
    }


def lattice_regularity(pts, a1, a2, mpp, phase_steps=40):
    """Seberapa rapi titik membentuk kisi — metrik utama yang netral.

    Sawit ditanam pada jarak teratur, jadi pusat tajuk yang benar HARUS
    membentuk kisi rapi. Metrik ini tidak memakai citra sama sekali dan tidak
    berpihak pada detektor mana pun, sehingga adil untuk membandingkan model.

    Cari fase kisi terbaik, lalu ukur jarak tiap titik ke posisi kisi ideal
    terdekat. Titik acak menghasilkan simpangan besar (~0,3 x jarak tanam),
    deteksi yang benar menghasilkan simpangan kecil.
    """
    if pts.shape[1] < 5:
        return {"lattice_rmse_m": None, "lattice_within_1m": None}
    A = np.column_stack([a1, a2])
    Ainv = np.linalg.inv(A)
    best = None
    for i in range(phase_steps):
        for j in range(phase_steps):
            origin = a1 * (i / phase_steps) + a2 * (j / phase_steps)
            mn = Ainv @ (pts - origin[:, None])
            resid = mn - np.round(mn)                 # sisa dalam satuan sel
            d = np.linalg.norm(A @ resid, axis=0)     # kembali ke pixel
            med = float(np.median(d))
            if best is None or med < best[0]:
                best = (med, d)
    med, d = best
    return {
        "lattice_rmse_m": round(float(np.sqrt(np.mean((d * mpp) ** 2))), 2),
        "lattice_median_m": round(med * mpp, 2),
        "lattice_within_1m": round(float(np.mean(d * mpp <= 1.0)), 3),
        "lattice_within_2m": round(float(np.mean(d * mpp <= 2.0)), 3),
    }


def lattice_regularity_local(pts, a1, a2, mpp, block_cells=4, phase_steps=20):
    """Keteraturan kisi dengan fase dicari ulang per blok.

    Barisan tanam melengkung, jadi metrik kisi kaku menghukum detektor atas
    kesalahan yang sebenarnya milik lahan, bukan milik model. Versi ini
    menyerap lengkungan itu dan jadi ukuran yang lebih adil untuk akurasi
    posisi. Baseline acak tetap harus disertakan sebagai pembanding.
    """
    if pts.shape[1] < 8:
        return {"local_rmse_m": None, "local_within_1m": None}
    A = np.column_stack([a1, a2])
    Ainv = np.linalg.inv(A)
    mn = Ainv @ pts
    bx = np.floor(mn[0] / block_cells).astype(int)
    by = np.floor(mn[1] / block_cells).astype(int)
    ds = []
    for key in set(zip(bx.tolist(), by.tolist())):
        sel = (bx == key[0]) & (by == key[1])
        if sel.sum() < 4:
            continue
        sub = pts[:, sel]
        best = None
        for i in range(phase_steps):
            for j in range(phase_steps):
                o = a1 * (i / phase_steps) + a2 * (j / phase_steps)
                r = Ainv @ (sub - o[:, None])
                d = np.linalg.norm(A @ (r - np.round(r)), axis=0)
                med = float(np.median(d))
                if best is None or med < best[0]:
                    best = (med, d)
        ds.append(best[1])
    if not ds:
        return {"local_rmse_m": None, "local_within_1m": None}
    d = np.concatenate(ds) * mpp
    return {
        "local_rmse_m": round(float(np.sqrt(np.mean(d ** 2))), 2),
        "local_median_m": round(float(np.median(d)), 2),
        "local_within_1m": round(float(np.mean(d <= 1.0)), 3),
        "local_within_2m": round(float(np.mean(d <= 2.0)), 3),
    }


def random_baseline(mask, gray, spacing_px, crown_radius_px, mpp, n, seed=0):
    """Metrik yang sama untuk titik acak di dalam persil — pembanding dasar.

    Tanpa ini, angka simetri/offset tidak punya makna: kita perlu tahu
    seberapa baik "asal tebak" supaya tahu model benar-benar lebih baik.
    """
    rng = np.random.default_rng(seed)
    ys, xs = np.nonzero(mask)
    pick = rng.choice(len(ys), size=min(n, len(ys)), replace=False)
    pts = np.vstack([xs[pick].astype(float), ys[pick].astype(float)])
    return position_metrics(pts, gray, mask, spacing_px, crown_radius_px, mpp)
