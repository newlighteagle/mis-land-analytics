"""Ambil citra resolusi tinggi per persil dari tile XYZ (Web Mercator).

Mosaik tile untuk bbox persil, dengan transform pixel <-> lon/lat. Satu
sumber saja — Google Satellite, zoom native 19 (0,30 m/px) di area proyek —
supaya citra analisa dan peta dasar dashboard memakai acuan yang sama.
Esri dibuang karena 0,60 m/px tidak cukup untuk posisi per pohon.

Catatan lisensi: kedua layanan ini berlisensi untuk visualisasi, dan tile
Google diakses di luar Google Maps Platform resmi — tidak sesuai ToS-nya.
Pemakaian di sini sebatas prototipe internal. Untuk produksi, pakai citra
berlisensi analisa (Maxar/Airbus) atau foto drone.
"""

import math
import os
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from io import BytesIO

TILE_SIZE = 256
CACHE_DIR = Path(os.environ.get("TILE_CACHE_DIR", ".tilecache"))

# Urutan prioritas. Zoom native di area proyek: Google 19 (0,30 m/px),
# Esri 18 (0,60 m/px). Zoom di atas native dilayani sebagai hasil pembesaran
# saja, jadi tidak dicoba.
SOURCES = (
    {
        "name": "google",
        "url": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "zooms": (19, 18),
    },
)

TILE_URL = SOURCES[0]["url"]
ZOOMS = (19, 18)


def _lonlat_to_pixel(lon, lat, z):
    """Koordinat pixel global Web Mercator pada zoom z."""
    scale = TILE_SIZE * (2 ** z)
    x = (lon + 180.0) / 360.0 * scale
    siny = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
    return x, y


def _pixel_to_lonlat(px, py, z):
    scale = TILE_SIZE * (2 ** z)
    lon = px / scale * 360.0 - 180.0
    n = math.pi - 2.0 * math.pi * py / scale
    lat = math.degrees(math.atan(math.sinh(n)))
    return lon, lat


def meters_per_pixel(lat, z):
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)


class ParcelImage:
    """Mosaik RGB (numpy uint8 HxWx3) + transform pixel <-> lon/lat."""

    def __init__(self, rgb, z, origin_px, origin_py, source=None):
        self.rgb = rgb
        self.z = z
        self.origin_px = origin_px  # pixel global kiri-atas mosaik
        self.origin_py = origin_py
        self.source = source        # nama sumber tile, dicatat di hasil analisa

    def to_lonlat(self, col, row):
        return _pixel_to_lonlat(self.origin_px + col, self.origin_py + row, self.z)

    def to_colrow(self, lon, lat):
        px, py = _lonlat_to_pixel(lon, lat, self.z)
        return px - self.origin_px, py - self.origin_py


def _is_placeholder(arr: np.ndarray) -> bool:
    """Tile 'Map data not yet available': abu-abu + teks, praktis tanpa warna.

    Citra asli punya saturasi tinggi hampir di semua pixel (mean ~25, >99%
    pixel bersaturasi); placeholder mean ~0 karena R=G=B. Cek std saja tidak
    cukup — teks pada placeholder membuat std tetap tinggi.
    """
    a = arr.astype(np.int16)
    saturation = a.max(axis=2) - a.min(axis=2)
    return float((saturation > 10).mean()) < 0.10


def _cache_path(source, z, x, y):
    d = CACHE_DIR / source / str(z) / str(x)
    return d / f"{y}.png"


def _fetch_tile(session, source, url, z, x, y):
    """Ambil satu tile, lewat cache lokal.

    Lahan bertetangga banyak berbagi tile yang sama, jadi cache memangkas
    ribuan permintaan saat analisa satu kelompok tani. File `.miss` menandai
    tile yang memang tidak ada citranya, supaya tidak diminta ulang.
    """
    path = _cache_path(source, z, x, y)
    miss = path.with_suffix(".miss")
    if miss.exists():
        return None
    if path.exists():
        try:
            return np.asarray(Image.open(path).convert("RGB"))
        except Exception:
            path.unlink(missing_ok=True)   # cache rusak, ambil ulang

    r = session.get(url.format(z=z, x=x, y=y), timeout=20)
    if r.status_code != 200:
        return None
    arr = np.asarray(Image.open(BytesIO(r.content)).convert("RGB"))
    path.parent.mkdir(parents=True, exist_ok=True)
    if _is_placeholder(arr):
        miss.touch()
        return None
    Image.fromarray(arr).save(path)
    return arr


def fetch_parcel_image(bounds, pad_m=20.0):
    """Mosaik citra untuk bbox (min_lon, min_lat, max_lon, max_lat) + padding.

    Coba tiap sumber di SOURCES berurutan, masing-masing dari zoom tertinggi.
    Return ParcelImage pertama yang lengkap; raise RuntimeError kalau tidak
    ada sumber yang punya citra untuk area ini.
    """
    min_lon, min_lat, max_lon, max_lat = bounds
    session = requests.Session()
    session.headers["User-Agent"] = "mis-land-analytics/1.0"
    pad_deg = pad_m / 111_320.0
    for src in SOURCES:
        for z in src["zooms"]:
            x0, y1 = _lonlat_to_pixel(min_lon - pad_deg, min_lat - pad_deg, z)
            x1, y0 = _lonlat_to_pixel(max_lon + pad_deg, max_lat + pad_deg, z)
            tx0, tx1 = int(x0 // TILE_SIZE), int(x1 // TILE_SIZE)
            ty0, ty1 = int(y0 // TILE_SIZE), int(y1 // TILE_SIZE)
            cols = (tx1 - tx0 + 1) * TILE_SIZE
            rows = (ty1 - ty0 + 1) * TILE_SIZE
            mosaic = np.zeros((rows, cols, 3), dtype=np.uint8)
            ok = True
            for ty in range(ty0, ty1 + 1):
                for tx in range(tx0, tx1 + 1):
                    tile = _fetch_tile(session, src["name"], src["url"], z, tx, ty)
                    if tile is None:
                        ok = False
                        break
                    r0, c0 = (ty - ty0) * TILE_SIZE, (tx - tx0) * TILE_SIZE
                    mosaic[r0:r0 + TILE_SIZE, c0:c0 + TILE_SIZE] = tile
                if not ok:
                    break
            if not ok:
                continue
            img = ParcelImage(mosaic, z, tx0 * TILE_SIZE, ty0 * TILE_SIZE, src["name"])
            # crop ke bbox+pad supaya analisa tidak memproses area luar
            c0, r0 = img.to_colrow(min_lon - pad_deg, max_lat + pad_deg)
            c1, r1 = img.to_colrow(max_lon + pad_deg, min_lat - pad_deg)
            c0, r0 = max(0, int(c0)), max(0, int(r0))
            c1, r1 = min(cols, int(c1) + 1), min(rows, int(r1) + 1)
            return ParcelImage(mosaic[r0:r1, c0:c1], z,
                               img.origin_px + c0, img.origin_py + r0, src["name"])
    raise RuntimeError("Tidak ada citra tersedia untuk area ini (zoom 17-19)")
