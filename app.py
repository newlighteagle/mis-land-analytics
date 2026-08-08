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


@app.get("/api/search")
def search(q: str):
    if len(q) < 3:
        return []
    with prod_conn() as prod, prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.id, p.parcel_id, p.area, p.crop_type, f.name AS farmer_name
               FROM tbl_land_parcel p
               JOIN tbl_farmer f ON f.id = p.farmer_id
               WHERE p.is_active AND (p.parcel_id ILIKE %s OR f.name ILIKE %s)
               ORDER BY p.parcel_id LIMIT 20""",
            (f"%{q}%", f"%{q}%"),
        )
        return cur.fetchall()


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
