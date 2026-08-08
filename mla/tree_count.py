"""Modul tree counting.

Metode v1: baseline_density — estimasi jumlah pohon = luas (ha) x SPH.
SPH default 136 pohon/ha (jarak tanam 9,2 m segitiga), bisa di-override per
request karena kebun swadaya jarak tanamnya tidak seragam. planting_year di
mis-prod kosong semua, jadi belum ada koreksi umur; tahun yang tersirat di
parcel_id disimpan sebagai hint di params.
"""

import json
import re
from psycopg.rows import dict_row

DEFAULT_SPH = 136.0
BASELINE_VERSION = "baseline_density/v1"

YEAR_RE = re.compile(r"(19|20)\d{2}")


class ParcelNotFound(Exception):
    pass


class AmbiguousParcel(Exception):
    def __init__(self, matches):
        self.matches = matches
        super().__init__(f"{len(matches)} persil aktif memakai ID ini")


def resolve_parcel(prod, ident: str) -> dict:
    """Cari persil aktif berdasarkan parcel_id (ID lahan) atau primary key."""
    with prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT id, parcel_id, farmer_id, area, crop_type, species,
                      land_status, blok, is_psr, geometry
               FROM tbl_land_parcel
               WHERE is_active AND (parcel_id = %s OR id = %s)""",
            (ident, ident),
        )
        rows = cur.fetchall()
    if not rows:
        raise ParcelNotFound(ident)
    if len(rows) > 1:
        raise AmbiguousParcel([r["id"] for r in rows])
    return rows[0]


def year_hint(parcel_id: str):
    m = YEAR_RE.search(parcel_id or "")
    return int(m.group()) if m else None


def baseline(prod, local, ident: str, sph: float | None = None) -> dict:
    parcel = resolve_parcel(prod, ident)
    sph_used = float(sph) if sph else DEFAULT_SPH
    area_ha = float(parcel["area"])
    count = round(area_ha * sph_used)
    params = {
        "sph_source": "custom" if sph else "default",
        "year_hint_from_parcel_id": year_hint(parcel["parcel_id"]),
        "crop_type": parcel["crop_type"],
        "is_psr": parcel["is_psr"],
    }
    with local.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """INSERT INTO analytics.tree_count
                 (land_parcel_pk, parcel_id, method, model_version, image_date,
                  tree_count, sph_used, area_ha, confidence, params)
               VALUES (%s, %s, 'baseline_density', %s, NULL, %s, %s, %s, 'low', %s)
               ON CONFLICT (land_parcel_pk, method) DO UPDATE SET
                 model_version = EXCLUDED.model_version,
                 tree_count    = EXCLUDED.tree_count,
                 sph_used      = EXCLUDED.sph_used,
                 area_ha       = EXCLUDED.area_ha,
                 confidence    = EXCLUDED.confidence,
                 params        = EXCLUDED.params,
                 computed_at   = now()
               RETURNING *""",
            (parcel["id"], parcel["parcel_id"], BASELINE_VERSION,
             count, sph_used, area_ha, json.dumps(params)),
        )
        row = cur.fetchone()
    local.commit()
    row["computed_at"] = row["computed_at"].isoformat()
    for k in ("sph_used", "area_ha"):
        row[k] = float(row[k])
    return row


def results_for(local, land_parcel_pk: str) -> list[dict]:
    with local.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT method, model_version, image_date, tree_count, sph_used,
                      area_ha, confidence, params, computed_at
               FROM analytics.tree_count
               WHERE land_parcel_pk = %s
               ORDER BY computed_at DESC""",
            (land_parcel_pk,),
        )
        rows = cur.fetchall()
    for r in rows:
        r["computed_at"] = r["computed_at"].isoformat()
        r["image_date"] = r["image_date"].isoformat() if r["image_date"] else None
        r["sph_used"] = float(r["sph_used"]) if r["sph_used"] is not None else None
        r["area_ha"] = float(r["area_ha"])
    return rows
