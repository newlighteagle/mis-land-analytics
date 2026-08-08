#!/usr/bin/env python3
"""CLI analisa lahan by-request per ID lahan.

Contoh:
  python analyze.py tree-count --parcel-id TJP.0001.A.14.06.06.2018
  python analyze.py tree-count --parcel-id TJP.0001.A.14.06.06.2018 --sph 128
"""

import argparse
import json
import sys

from mla import tree_count
from mla.db import local_conn, prod_conn


def main():
    ap = argparse.ArgumentParser(description="Analisa lahan by-request (mis-land-analytics)")
    sub = ap.add_subparsers(dest="module", required=True)

    tc = sub.add_parser("tree-count", help="Estimasi jumlah pohon (baseline)")
    tc.add_argument("--parcel-id", required=True, help="ID lahan (parcel_id) atau primary key")
    tc.add_argument("--sph", type=float, default=None,
                    help=f"Kerapatan pohon/ha (default {tree_count.DEFAULT_SPH})")

    args = ap.parse_args()
    prod, local = prod_conn(), local_conn()
    try:
        if args.module == "tree-count":
            row = tree_count.baseline(prod, local, args.parcel_id, sph=args.sph)
            print(json.dumps(row, indent=2, ensure_ascii=False, default=str))
    except tree_count.ParcelNotFound as e:
        sys.exit(f"Persil tidak ditemukan: {e}")
    except tree_count.AmbiguousParcel as e:
        sys.exit("ID lahan ganda, pakai primary key salah satu dari: " + ", ".join(e.matches))
    finally:
        prod.close()
        local.close()


if __name__ == "__main__":
    main()
