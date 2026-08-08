import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def prod_conn():
    """Koneksi ke mis-prod. READ-ONLY — jangan pernah menulis lewat koneksi ini."""
    conn = psycopg.connect(os.environ["PROD_DATABASE_URL"])
    conn.execute("SET default_transaction_read_only = on")
    return conn


def local_conn():
    """Koneksi ke DB lokal mis_analytics (hasil analisa)."""
    return psycopg.connect(os.environ["LOCAL_DATABASE_URL"])
