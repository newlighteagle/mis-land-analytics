#!/usr/bin/env python3
"""Bandingkan varian detektor pusat tajuk pada satu/beberapa persil.

Tiap varian diukur dengan metrik yang sama lalu dicatat ke
`analytics.model_run`, sehingga perbaikan model bisa ditelusuri antar waktu.

  .venv/bin/python eval_models.py --parcel-id ITM.0001.A.14.06.06.2017
"""

import argparse
import json

import numpy as np
from scipy.ndimage import gaussian_filter, sobel, uniform_filter
from skimage.feature import peak_local_max

from mla import crown, imagery, tree_detect, tree_grid
from mla.db import local_conn, prod_conn
from mla.tree_count import resolve_parcel

MODULE = "tree_grid"


def orientation_dispersion(gray, mask, spacing_px, win_px):
    """Pusat tajuk = tempat banyak arah pelepah bertemu.

    Sepanjang satu pelepah, arah gradien seragam (anisotropik). Di pusat
    tajuk, pelepah memancar ke segala arah sehingga arah gradien beragam.
    Jadi pusat = MINIMUM koherensi tensor struktur di dalam kanopi.
    """
    g = gaussian_filter(gray.astype(np.float32), 1.0)
    gy, gx = sobel(g, axis=0), sobel(g, axis=1)
    Jxx = uniform_filter(gx * gx, win_px)
    Jyy = uniform_filter(gy * gy, win_px)
    Jxy = uniform_filter(gx * gy, win_px)
    tmp = np.sqrt(np.maximum((Jxx - Jyy) ** 2 + 4 * Jxy ** 2, 0))
    denom = Jxx + Jyy + 1e-6
    coherence = tmp / denom                    # 1 = searah, 0 = segala arah
    inv = gaussian_filter(-coherence, sigma=2.0)
    return inv


def template_match(gray, mask, lat, mpp, rounds=3):
    """Template tajuk yang dipelajari dari citra itu sendiri, lalu diiterasi.

    Semua sawit di satu persil terlihat mirip, jadi rata-rata potongan citra
    di posisi kisi menghasilkan "wajah" tajuk khas kebun tersebut. Template
    itu dikorelasikan silang ke seluruh citra; puncaknya jadi posisi tajuk,
    lalu template dibangun ulang dari posisi baru (gaya EM). Tidak perlu
    label manual maupun asumsi bentuk seperti FRST.
    """
    from scipy.signal import fftconvolve

    a1, a2 = lat["a1"], lat["a2"]
    sp = min(np.linalg.norm(a1), np.linalg.norm(a2))
    half = max(4, int(round(0.45 * sp)))
    g = (gray - gray.mean()) / (gray.std() + 1e-6)

    # posisi awal: kisi dengan fase terbaik menurut kecerahan
    best = None
    for i in range(16):
        for j in range(16):
            origin = a1 * (i / 16) + a2 * (j / 16)
            pts = tree_grid._lattice_points(a1, a2, origin, mask.shape)
            c = np.clip(pts[0].astype(int), 0, mask.shape[1] - 1)
            r = np.clip(pts[1].astype(int), 0, mask.shape[0] - 1)
            sel = mask[r, c]
            if sel.sum() < 5:
                continue
            s = float(g[r[sel], c[sel]].mean())
            if best is None or s > best[0]:
                best = (s, pts[:, sel])
    pts = best[1]

    for _ in range(rounds):
        acc = np.zeros((2 * half + 1, 2 * half + 1), np.float32)
        n = 0
        for x, y in pts.T:
            xi, yi = int(round(x)), int(round(y))
            if xi - half < 0 or yi - half < 0 or xi + half + 1 > g.shape[1] or yi + half + 1 > g.shape[0]:
                continue
            acc += g[yi - half:yi + half + 1, xi - half:xi + half + 1]
            n += 1
        if n < 5:
            break
        tpl = acc / n
        tpl -= tpl.mean()
        resp = fftconvolve(g, tpl[::-1, ::-1], mode="same")
        resp = np.where(mask, resp, resp.min())
        pk = peak_local_max(resp, min_distance=max(2, int(0.45 * sp)),
                            labels=mask, exclude_border=False)
        if len(pk) < 5:
            break
        pts = pk[:, ::-1].astype(float).T
    return pts


def obia_watershed(gray, green, mask, spacing_px, crown_radius_px):
    """OBIA: segmentasi tajuk lalu ambil sentroid tiap objek.

    Pendekatan berbasis objek, bukan titik: citra dibagi menjadi wilayah
    tajuk memakai watershed (marker = puncak lokal, batas = celah gelap),
    lalu pusat massa tiap wilayah dipakai sebagai posisi pohon. Segmen yang
    luasnya jauh menyimpang dari luas sel tanam dibuang.
    """
    from skimage.measure import regionprops
    from skimage.segmentation import watershed

    sm = gaussian_filter(green.astype(np.float32), sigma=max(1.0, 0.3 * crown_radius_px))
    markers_pk = peak_local_max(sm, min_distance=max(2, int(0.45 * spacing_px)),
                                labels=mask, exclude_border=False)
    if len(markers_pk) < 5:
        return np.empty((2, 0))
    markers = np.zeros(sm.shape, np.int32)
    markers[tuple(markers_pk.T)] = np.arange(1, len(markers_pk) + 1)

    labels = watershed(-sm, markers, mask=mask)
    cell_px = 0.866 * spacing_px ** 2
    cents = []
    for r in regionprops(labels):
        if 0.25 * cell_px <= r.area <= 2.5 * cell_px:
            cents.append((r.centroid[1], r.centroid[0]))       # (x, y)
    return np.array(cents, float).T if cents else np.empty((2, 0))


def obia_intensity_weighted(gray, green, mask, spacing_px, crown_radius_px):
    """Varian OBIA: sentroid berbobot kehijauan, bukan sentroid geometris.

    Pusat massa geometris bisa tergeser oleh bentuk segmen yang tidak simetris;
    membobot dengan kehijauan menarik titik ke bagian tajuk yang paling rimbun.
    """
    from skimage.measure import regionprops
    from skimage.segmentation import watershed

    sm = gaussian_filter(green.astype(np.float32), sigma=max(1.0, 0.3 * crown_radius_px))
    pk = peak_local_max(sm, min_distance=max(2, int(0.45 * spacing_px)),
                        labels=mask, exclude_border=False)
    if len(pk) < 5:
        return np.empty((2, 0))
    markers = np.zeros(sm.shape, np.int32)
    markers[tuple(pk.T)] = np.arange(1, len(pk) + 1)
    labels = watershed(-sm, markers, mask=mask)
    w = np.clip(sm - sm[mask].min(), 0, None)
    cell_px = 0.866 * spacing_px ** 2
    cents = []
    for r in regionprops(labels, intensity_image=w):
        if 0.25 * cell_px <= r.area <= 2.5 * cell_px:
            cy, cx = r.centroid_weighted
            cents.append((cx, cy))
    return np.array(cents, float).T if cents else np.empty((2, 0))


def variants(img, mask, mpp, lat):
    gray = img.rgb.astype(np.float32).mean(axis=2)
    green = tree_grid.greenness(img.rgb)
    sp = min(np.linalg.norm(lat["a1"]), np.linalg.norm(lat["a2"]))
    cr = 3.5 / mpp
    md = max(2, int(0.45 * sp))
    out = {}

    out["v2_greenness"] = tree_grid.crown_candidates(green, mask, sp, max(1.0, 1.0 / mpp))[0]
    out["frst_bright"] = crown.centers_frst(gray, mask, sp, cr)[0]
    S = crown.frst(gray, [max(2, int(cr * f)) for f in (0.5, 0.75, 1.0)], bright=False)
    out["frst_dark"] = peak_local_max(np.where(mask, S, 0), min_distance=md,
                                      labels=mask, exclude_border=False)[:, ::-1].astype(float)
    out["gap_distance"] = crown.centers_gap_distance(gray, mask, sp)
    disp = orientation_dispersion(gray, mask, sp, max(3, int(0.35 * sp)))
    out["orient_dispersion"] = peak_local_max(np.where(mask, disp, disp.min()),
                                              min_distance=md, labels=mask,
                                              exclude_border=False)[:, ::-1].astype(float)
    sm = gaussian_filter(gray, sigma=max(1.0, 0.35 * cr))
    out["bright_peak"] = peak_local_max(np.where(mask, sm, 0), min_distance=md,
                                        labels=mask, exclude_border=False)[:, ::-1].astype(float)
    res = {k: v.T for k, v in out.items() if len(v)}      # -> (2, N)
    for rounds in (1, 3):
        res[f"template_r{rounds}"] = template_match(gray, mask, lat, mpp, rounds=rounds)
    for name, fn in (("obia_watershed", obia_watershed),
                     ("obia_weighted", obia_intensity_weighted)):
        pts = fn(gray, green, mask, sp, cr)
        if pts.shape[1]:
            res[name] = pts
    for label, r in (("frond_conv", 1.0), ("frond_conv_r08", 0.8), ("frond_conv_r13", 1.3)):
        pts = crown.centers_frond(gray, mask, sp, cr * r)[0]
        if len(pts):
            res[label] = pts.T
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parcel-id", required=True)
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()

    prod, local = prod_conn(), local_conn()
    parcel = resolve_parcel(prod, args.parcel_id)
    geom = parcel["geometry"]
    b = tree_detect.bounds_of(geom)
    img = imagery.fetch_parcel_image(b)
    mask = tree_detect.parcel_mask(img, geom)
    mpp = imagery.meters_per_pixel((b[1] + b[3]) / 2, img.z)
    gray = img.rgb.astype(np.float32).mean(axis=2)

    lat = tree_grid.fit_lattice(tree_grid._detrended_patch(img.rgb, mask), mpp)
    sp = min(np.linalg.norm(lat["a1"]), np.linalg.norm(lat["a2"]))
    cr = 3.5 / mpp
    expect = mask.sum() * mpp * mpp / ((sp * mpp) ** 2 * 0.866)

    print(f"{parcel['parcel_id']} · {img.source} z{img.z} ({mpp:.3f} m/px) · "
          f"jarak tanam {sp*mpp:.2f} m · perkiraan {expect:.0f} pohon\n")

    cands = variants(img, mask, mpp, lat)
    cands["random"] = None       # diisi di bawah, pakai jumlah rata-rata

    n_ref = int(np.median([v.shape[1] for v in cands.values() if v is not None]))
    rng = np.random.default_rng(0)
    ys, xs = np.nonzero(mask)
    pick = rng.choice(len(ys), size=min(n_ref, len(ys)), replace=False)
    cands["random"] = np.vstack([xs[pick].astype(float), ys[pick].astype(float)])

    rows = []
    for name, pts in cands.items():
        m = crown.position_metrics(pts, gray, mask, sp, cr, mpp)
        m.update(crown.lattice_regularity(pts, lat["a1"], lat["a2"], mpp))
        m.update(crown.lattice_regularity_local(pts, lat["a1"], lat["a2"], mpp))
        m["ratio_to_expected"] = round(pts.shape[1] / expect, 2)
        rows.append((name, m))

    rows.sort(key=lambda r: (r[1]["local_rmse_m"] is None, r[1]["local_rmse_m"]))
    print(f"{'varian':20} {'n':>5} {'rasio':>6} | {'LOKAL rmse':>10} {'<=1m':>6} {'<=2m':>6} | "
          f"{'global rmse':>11} | {'simetri%':>9}")
    print("-" * 84)
    for name, m in rows:
        print(f"{name:20} {m['n_points']:5} {m['ratio_to_expected']:6.2f} | "
              f"{m['local_rmse_m']:10.2f} {m['local_within_1m']:6.2f} {m['local_within_2m']:6.2f} | "
              f"{m['lattice_rmse_m']:11.2f} | {m['symmetry_pct']:9.1f}")

    print("\nLOKAL rmse = simpangan ke kisi yang fasenya dicari ulang per blok — "
          "menyerap lengkungan\n             barisan tanam, jadi ukuran akurasi model yang lebih adil."
          "\nglobal rmse = kisi kaku satu fase (menghukum lengkungan lahan)."
          "\nsimetri%    = persentil simetri radial (bias ke varian FRST).")

    if not args.no_store:
        with local.cursor() as cur:
            for name, m in rows:
                cur.execute(
                    """INSERT INTO analytics.model_run
                         (land_parcel_pk, parcel_id, module, model_version, variant,
                          n_points, metrics, params)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (parcel["id"], parcel["parcel_id"], MODULE, "eval/v3", name,
                     m["n_points"], json.dumps(m),
                     json.dumps({"image_source": img.source, "zoom": img.z,
                                 "mpp": round(mpp, 4), "spacing_m": round(sp * mpp, 2)})),
                )
        local.commit()
        print(f"\n{len(rows)} baris dicatat ke analytics.model_run")


if __name__ == "__main__":
    main()
