# Konfigurasi `.env`

Kredensial dan konfigurasi dibaca dari `.env` di root proyek via `python-dotenv` (`load_dotenv()` dipanggil di `mla/db.py` saat modul di-import). File ini **tidak di-commit** (ada di `.gitignore`) — jangan pernah memindahkan nilainya ke kode.

## Variabel

| Variabel | Wajib | Dipakai oleh | Isi |
|---|---|---|---|
| `PROD_DATABASE_URL` | Ya | `mla/db.py::prod_conn()` | URL koneksi ke `mis-prod`, format `postgresql://user:pass@host:1234/mis-prod` |
| `LOCAL_DATABASE_URL` | Ya | `mla/db.py::local_conn()` | URL koneksi ke DB lokal, format `postgresql://localhost:5432/mis_analytics` |
| `GEE_PROJECT` | Belum (disiapkan) | Modul citra mendatang | ID project Google Earth Engine |

## Contoh template

```dotenv
PROD_DATABASE_URL=postgresql://USER:PASSWORD@HOST:1234/mis-prod
LOCAL_DATABASE_URL=postgresql://localhost:5432/mis_analytics
GEE_PROJECT=nama-project-gee
```

## Catatan

- Kedua URL dibaca dengan `os.environ[...]` (tanpa default) — jika variabel hilang, aplikasi langsung gagal dengan `KeyError`, bukan diam-diam memakai koneksi lain.
- Sifat read-only koneksi prod **tidak** bergantung pada isi URL; ditegakkan oleh `SET default_transaction_read_only = on` di `prod_conn()` (lihat [01-arsitektur.md](01-arsitektur.md)).
