#!/usr/bin/env python3
"""Analisa kisi tanam untuk semua lahan dalam satu lembaga tani.

Contoh:
  .venv/bin/python batch_analyze.py --group "KUD Intan Makmur"

Lahan yang gagal (citra tidak ada / pola tanam tidak terbaca) dilewati dan
dicatat di ringkasan akhir — bukan menghentikan batch.
"""

import argparse
import time

from psycopg.rows import dict_row

from mla import tree_grid
from mla.db import local_conn, prod_conn
from mla.tree_detect import NoImagery


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, help="Nama lembaga tani persis")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    prod, local = prod_conn(), local_conn()
    with prod.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT p.id, p.parcel_id, p.area
               FROM tbl_land_parcel p
               JOIN tbl_farmer f ON f.id = p.farmer_id
               JOIN tbl_farmer_group g ON g.id = f.farmer_group_id
               WHERE p.is_active AND p.geometry IS NOT NULL AND g.name = %s
               ORDER BY p.parcel_id""",
            (args.group,),
        )
        rows = cur.fetchall()
    if args.limit:
        rows = rows[:args.limit]

    print(f"{len(rows)} lahan di {args.group}", flush=True)
    ok = skipped = 0
    trees = 0
    cats = {"sehat": 0, "lemah": 0, "kosong": 0}
    fails: dict[str, int] = {}
    t0 = time.time()

    for i, r in enumerate(rows, 1):
        try:
            res = tree_grid.fit(prod, local, r["id"])
            p = res["params"]
            ok += 1
            trees += res["tree_count"]
            for k in cats:
                cats[k] += p["kategori"][k]
            if i % 25 == 0 or i == len(rows):
                rate = (time.time() - t0) / i
                print(f"[{i}/{len(rows)}] {r['parcel_id']} -> {res['tree_count']} pohon "
                      f"(SPH {p['sph_from_lattice']}) · {rate:.1f} s/lahan · "
                      f"sisa ~{rate * (len(rows) - i) / 60:.0f} mnt", flush=True)
        except (NoImagery, tree_grid.NoLattice, ValueError) as e:
            skipped += 1
            fails[type(e).__name__] = fails.get(type(e).__name__, 0) + 1
        except Exception as e:                      # jangan hentikan batch
            skipped += 1
            fails[type(e).__name__] = fails.get(type(e).__name__, 0) + 1

    dur = time.time() - t0
    print(f"\nSELESAI dalam {dur/60:.1f} menit")
    print(f"  berhasil : {ok} lahan, {trees:,} pohon")
    print(f"  dilewati : {skipped}" + (f" ({fails})" if fails else ""))
    if ok:
        tot = sum(cats.values()) or 1
        for k, v in cats.items():
            print(f"  {k:7}: {v:6,} ({v/tot*100:.1f}%)")
    prod.close()
    local.close()


if __name__ == "__main__":
    main()
