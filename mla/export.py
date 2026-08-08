"""Ekspor titik pohon ke CSV, GeoJSON, dan shapefile (zip).

Semua format memuat kolom yang sama supaya hasilnya bisa dibandingkan lintas
alat. Kolom `source` dan `model_version` sengaja ikut: penerima data harus
bisa membedakan titik hasil registrasi manusia dari draf model.
"""

import csv
import io
import json
import zipfile
from datetime import datetime

import shapefile

from mla.tree_detect import points_for
from mla.tree_grid import METHOD

# Nama field dibatasi 10 karakter karena format DBF pada shapefile.
FIELDS = [
    ("no", "N", 10, 0),
    ("tree_id", "N", 12, 0),
    ("parcel_id", "C", 40, 0),
    ("farmer", "C", 60, 0),
    ("lon", "F", 19, 8),
    ("lat", "F", 19, 8),
    ("category", "C", 12, 0),
    ("vigor", "F", 8, 4),
    ("source", "C", 10, 0),
    ("model_ver", "C", 24, 0),
]

WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def collect(local, land_parcel_pk: str, parcel_id: str, farmer: str,
            method: str = METHOD) -> tuple[list[dict], str | None]:
    """Ambil titik satu lahan sebagai baris siap ekspor."""
    fc = points_for(local, land_parcel_pk, method)
    version = fc.get("model_version")
    rows = []
    for f in fc["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        rows.append({
            "no": p["no"],
            "tree_id": p["id"],
            "parcel_id": parcel_id,
            "farmer": farmer or "",
            "lon": round(lon, 8),
            "lat": round(lat, 8),
            "category": p.get("category") or "unknown",
            "vigor": p.get("score"),
            "source": p.get("source") or "auto",
            "model_ver": version or "",
        })
    return rows, version


def to_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[f[0] for f in FIELDS])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")     # BOM supaya rapi di Excel


def to_geojson(rows: list[dict], parcel_id: str) -> bytes:
    fc = {
        "type": "FeatureCollection",
        "name": f"pohon_{parcel_id}",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
             "properties": {k: v for k, v in r.items() if k not in ("lon", "lat")}}
            for r in rows
        ],
    }
    return json.dumps(fc, ensure_ascii=False, indent=1).encode("utf-8")


def to_shapefile_zip(rows: list[dict], parcel_id: str) -> bytes:
    """Shapefile titik + .prj WGS84, dibungkus zip."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT)
    for name, typ, size, dec in FIELDS:
        w.field(name, typ, size, dec)
    for r in rows:
        w.point(r["lon"], r["lat"])
        w.record(*[r[name] for name, *_ in FIELDS])
    w.close()

    base = f"pohon_{parcel_id}".replace(".", "_")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{base}.shp", shp.getvalue())
        z.writestr(f"{base}.shx", shx.getvalue())
        z.writestr(f"{base}.dbf", dbf.getvalue())
        z.writestr(f"{base}.prj", WGS84_PRJ)
        z.writestr(f"{base}.cpg", "UTF-8")
        z.writestr("README.txt",
                   f"Titik pohon {parcel_id}\n"
                   f"Diekspor {datetime.now():%Y-%m-%d %H:%M}\n"
                   f"CRS: WGS84 (EPSG:4326)\n\n"
                   f"Kolom source: auto=draf model, moved=digeser manusia, "
                   f"added=ditambah manusia, verified=diperiksa manusia.\n")
    return out.getvalue()
