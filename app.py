"""Dashboard spasial lokal: pilih ID lahan -> peta + hasil analisa persil.

Jalankan: .venv/bin/uvicorn app:app --reload --port 8008
"""

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel

from mla import tree_count, tree_detect, tree_grid
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
                      max(computed_at) AS last_computed,
                      -- angka yang ditampilkan diambil dari metode terbaik yang ada
                      max(tree_count) FILTER (WHERE method = 'grid_fit')     AS trees_grid,
                      max(sph_used)   FILTER (WHERE method = 'grid_fit')     AS sph_grid,
                      max(tree_count) FILTER (WHERE method = 'baseline_density') AS trees_baseline
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
            "trees_grid": r["trees_grid"],
            "sph_grid": float(r["sph_grid"]) if r["sph_grid"] is not None else None,
            "trees_baseline": r["trees_baseline"],
            "last_computed": r["last_computed"].isoformat(),
        })
    out.sort(key=lambda r: r["last_computed"], reverse=True)
    return out


NO_GROUP = "_none"   # sentinel untuk petani tanpa kelompok


@app.get("/api/groups")
def groups():
    """Lembaga tani + progres cakupan analisa (lahan teranalisa / total)."""
    with local_conn() as local:
        analyzed = _analyzed_pks(local)
    with prod_conn() as prod, prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT COALESCE(g.id, %s) AS id, COALESCE(g.name, 'Tanpa kelompok') AS name,
                      count(p.id) AS total, sum(p.area) AS total_area
               FROM tbl_land_parcel p
               JOIN tbl_farmer f ON f.id = p.farmer_id
               LEFT JOIN tbl_farmer_group g ON g.id = f.farmer_group_id
               WHERE p.is_active
               GROUP BY 1, 2""",
            (NO_GROUP,),
        )
        rows = cur.fetchall()
        done = {}
        if analyzed:
            cur.execute(
                """SELECT COALESCE(g.id, %s) AS id, count(p.id) AS n
                   FROM tbl_land_parcel p
                   JOIN tbl_farmer f ON f.id = p.farmer_id
                   LEFT JOIN tbl_farmer_group g ON g.id = f.farmer_group_id
                   WHERE p.is_active AND p.id = ANY(%s)
                   GROUP BY 1""",
                (NO_GROUP, analyzed),
            )
            done = {r["id"]: r["n"] for r in cur.fetchall()}
    out = []
    for r in rows:
        n = done.get(r["id"], 0)
        out.append({
            "id": r["id"], "name": r["name"],
            "total": r["total"], "analyzed": n,
            "pct": round(n / r["total"] * 100, 1) if r["total"] else 0.0,
            "total_area": float(r["total_area"]) if r["total_area"] is not None else 0.0,
        })
    # yang sudah ada progresnya di atas, sisanya menurut jumlah lahan
    out.sort(key=lambda r: (-r["analyzed"], -r["total"]))
    return out


@app.get("/api/group/{gid}/parcels")
def group_parcels(gid: str, status: str = "done"):
    """Lahan dalam satu lembaga tani, disaring status analisanya."""
    with local_conn() as local:
        analyzed = _analyzed_pks(local)
    if status == "done" and not analyzed:
        return []
    clause = ""
    params: list = []
    if gid == NO_GROUP:
        clause_group = "f.farmer_group_id IS NULL"
    else:
        clause_group = "f.farmer_group_id = %s"
        params.append(gid)
    if status == "done":
        clause = "AND p.id = ANY(%s)"
        params.append(analyzed)
    elif status == "new":
        clause = "AND NOT (p.id = ANY(%s))"
        params.append(analyzed)
    with prod_conn() as prod, prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT p.id, p.parcel_id, p.area, f.name AS farmer_name
                FROM tbl_land_parcel p
                JOIN tbl_farmer f ON f.id = p.farmer_id
                WHERE p.is_active AND {clause_group} {clause}
                ORDER BY p.parcel_id LIMIT 500""",
            params,
        )
        rows = cur.fetchall()
    if status != "done":
        return rows
    with local_conn() as local, local.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT land_parcel_pk,
                      max(tree_count) FILTER (WHERE method = 'grid_fit') AS trees_grid,
                      max(sph_used)   FILTER (WHERE method = 'grid_fit') AS sph_grid,
                      max(tree_count) FILTER (WHERE method = 'baseline_density') AS trees_baseline,
                      max(computed_at) AS last_computed
               FROM analytics.tree_count WHERE land_parcel_pk = ANY(%s)
               GROUP BY land_parcel_pk""",
            ([r["id"] for r in rows],),
        )
        res = {r["land_parcel_pk"]: r for r in cur.fetchall()}
    for r in rows:
        m = res.get(r["id"], {})
        r["trees_grid"] = m.get("trees_grid")
        r["sph_grid"] = float(m["sph_grid"]) if m.get("sph_grid") is not None else None
        r["trees_baseline"] = m.get("trees_baseline")
        r["last_computed"] = m["last_computed"].isoformat() if m.get("last_computed") else None
    return rows


@app.get("/api/analyzed/geojson")
def analyzed_geojson(group: str | None = None):
    """Poligon persil yang sudah dianalisa — layer ikhtisar di peta.

    `group` opsional: batasi ke satu lembaga tani (pakai sentinel `_none`
    untuk petani tanpa kelompok).
    """
    summary = {r["id"]: r for r in analyzed()}
    if not summary:
        return {"type": "FeatureCollection", "features": []}
    params: list = [list(summary)]
    clause = ""
    if group == NO_GROUP:
        clause = "AND f.farmer_group_id IS NULL"
    elif group:
        clause = "AND f.farmer_group_id = %s"
        params.append(group)
    with prod_conn() as prod, prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""SELECT p.id, p.geometry FROM tbl_land_parcel p
                JOIN tbl_farmer f ON f.id = p.farmer_id
                WHERE p.id = ANY(%s) {clause}""",
            params,
        )
        rows = cur.fetchall()
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": r["geometry"], "properties": summary[r["id"]]}
            for r in rows if r["geometry"]
        ],
    }


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


@app.post("/api/parcel/{pk}/analyze/tree-grid")
def analyze_tree_grid(pk: str):
    """Petakan posisi pohon dengan fitting kisi tanam dari citra."""
    with prod_conn() as prod, local_conn() as local:
        try:
            return tree_grid.fit(prod, local, pk)
        except tree_count.ParcelNotFound:
            raise HTTPException(404, "Persil tidak ditemukan")
        except tree_detect.NoImagery as e:
            raise HTTPException(422, f"Citra tidak tersedia: {e}")
        except tree_grid.NoLattice as e:
            raise HTTPException(422, f"Pola tanam tidak terbaca: {e}")


@app.get("/api/parcel/{pk}/trees")
def trees(pk: str, method: str = tree_grid.METHOD):
    """Titik pohon sebagai GeoJSON FeatureCollection."""
    with local_conn() as local:
        return tree_detect.points_for(local, pk, method)


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
