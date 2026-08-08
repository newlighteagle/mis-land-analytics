"""Dashboard spasial lokal: pilih ID lahan -> peta + hasil analisa persil.

Jalankan: .venv/bin/uvicorn app:app --reload --port 8008
"""

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel

from mla import tree_count
from mla.db import local_conn, prod_conn

app = FastAPI(title="mis-land-analytics")


def _analyzed_pks(local) -> list[str]:
    """PK persil yang sudah punya hasil analisa (DB lokal)."""
    with local.cursor() as cur:
        cur.execute("SELECT DISTINCT land_parcel_pk FROM analytics.tree_count")
        return [r[0] for r in cur.fetchall()]


@app.get("/api/search")
def search(q: str, status: str = "all"):
    """Cari persil aktif by ID lahan / nama petani.

    status: 'all' | 'new' (belum pernah dianalisa) | 'done' (sudah).
    Filter lintas-database, jadi daftar PK hasil analisa diambil dari DB lokal
    lalu dipakai sebagai parameter query ke prod.
    """
    if len(q) < 3:
        return []
    with local_conn() as local:
        analyzed = _analyzed_pks(local)
    clause = ""
    params = [f"%{q}%", f"%{q}%"]
    if status == "new":
        clause = "AND NOT (p.id = ANY(%s))"
        params.append(analyzed)
    elif status == "done":
        if not analyzed:
            return []
        clause = "AND p.id = ANY(%s)"
        params.append(analyzed)
    with prod_conn() as prod, prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT p.id, p.parcel_id, p.area, p.crop_type, f.name AS farmer_name
                FROM tbl_land_parcel p
                JOIN tbl_farmer f ON f.id = p.farmer_id
                WHERE p.is_active AND (p.parcel_id ILIKE %s OR f.name ILIKE %s) {clause}
                ORDER BY p.parcel_id LIMIT 20""",
            params,
        )
        return cur.fetchall()


@app.get("/api/analyzed")
def analyzed():
    """Semua persil yang sudah dianalisa, untuk select box di dashboard.

    Jumlahnya kecil (hanya yang pernah dianalisa), jadi dikirim sekaligus dan
    difilter di klien — tidak perlu round-trip per ketikan.
    """
    with local_conn() as local, local.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT land_parcel_pk, parcel_id, count(*) AS n_methods,
                      max(computed_at) AS last_computed
               FROM analytics.tree_count GROUP BY land_parcel_pk, parcel_id"""
        )
        rows = cur.fetchall()
    if not rows:
        return []
    by_pk = {r["land_parcel_pk"]: r for r in rows}
    with prod_conn() as prod, prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.id, p.area, f.name AS farmer_name
               FROM tbl_land_parcel p
               JOIN tbl_farmer f ON f.id = p.farmer_id
               WHERE p.id = ANY(%s)""",
            (list(by_pk),),
        )
        meta = {r["id"]: r for r in cur.fetchall()}
    out = []
    for pk, r in by_pk.items():
        m = meta.get(pk, {})
        out.append({
            "id": pk,
            "parcel_id": r["parcel_id"],
            "farmer_name": m.get("farmer_name"),
            "area": float(m["area"]) if m.get("area") is not None else None,
            "n_methods": r["n_methods"],
            "last_computed": r["last_computed"].isoformat(),
        })
    out.sort(key=lambda r: r["last_computed"], reverse=True)
    return out


@app.get("/api/parcel/{pk}")
def parcel(pk: str):
    with prod_conn() as prod, prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.id, p.parcel_id, p.area, p.crop_type, p.species,
                      p.land_status, p.blok, p.is_psr, p.notes, p.geometry,
                      f.name AS farmer_name, g.name AS farmer_group_name
               FROM tbl_land_parcel p
               JOIN tbl_farmer f ON f.id = p.farmer_id
               LEFT JOIN tbl_farmer_group g ON g.id = f.farmer_group_id
               WHERE p.is_active AND p.id = %s""",
            (pk,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Persil tidak ditemukan")
    geometry = row.pop("geometry")
    return {"type": "Feature", "geometry": geometry, "properties": row}


@app.get("/api/parcel/{pk}/results")
def results(pk: str):
    with local_conn() as local:
        return tree_count.results_for(local, pk)


class TreeCountReq(BaseModel):
    sph: float | None = None


@app.post("/api/parcel/{pk}/analyze/tree-count")
def analyze_tree_count(pk: str, req: TreeCountReq):
    with prod_conn() as prod, local_conn() as local:
        try:
            return tree_count.baseline(prod, local, pk, sph=req.sph)
        except tree_count.ParcelNotFound:
            raise HTTPException(404, "Persil tidak ditemukan")


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
