"""
scrape.py — scraper de precios de cerveza en supermercados online
--------------------------------------------------------------------------
Recorre las cadenas configuradas en chains.py. La mayoria corre sobre
VTEX (motor "vtex", via su API publico de catalogo); Coto usa un motor
distinto ("coto", Constructor.io) — ver docstrings de vtex_client.py y
coto_client.py. Guarda un unico CSV combinado por corrida con una fila
por SKU y cadena.

Si una cadena entera falla (red, HTTP, o devuelve 0 productos) se loguea
y se sigue con las demas — no corta la corrida completa por una cadena
caida. Si TODAS las cadenas fallan, sale con codigo de error (eso si debe
frenar el job de CI). Si un producto puntual falla al parsearse, se
descarta y se loguea (no rompe la corrida), igual criterio que
pedidosya-nunez/rappi-nunez.

Corre 1 vez por dia (10:15 ART), mismo horario que los scrapers hermanos
para poder comparar por fecha.

Uso:
    python3 scraper/scrape.py
    python3 scraper/scrape.py --fecha 2026-08-20 --out-dir ../data/raw
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import coto_client
import vtex_client
from brands import marca_de
from chains import CHAINS

TZ = ZoneInfo("America/Argentina/Buenos_Aires")
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CSV_FIELDS = ["cadena", "marca", "descripcion", "calibre", "fleje", "precio", "descuento", "promo_nominal"]


def scrape_cadena(chain):
    if chain["motor"] == "coto":
        s = coto_client.session()
        resultados = coto_client.fetch_search(s, chain["search_term"])
        if not resultados:
            return [], [f"[{chain['cadena']}] 0 productos devueltos por la API"]
        return coto_client.productos_a_filas(chain["cadena"], resultados, marca_de)

    s = vtex_client.session()
    productos = vtex_client.fetch_category(s, chain["base_url"], chain["category_path"])
    if not productos:
        return [], [f"[{chain['cadena']}] 0 productos devueltos por la API"]
    return vtex_client.productos_a_filas(chain["cadena"], productos, marca_de)


def guardar_csv(rows, out_dir, fecha):
    out_dir.mkdir(parents=True, exist_ok=True)
    destino = out_dir / f"{fecha}.csv"
    with destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return destino


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--fecha", default=None, help="YYYY-MM-DD (default: hoy en ART)")
    args = ap.parse_args()

    fecha = args.fecha or datetime.now(TZ).strftime("%Y-%m-%d")

    print("=" * 55)
    print("  Scraper supermercados-cerveza")
    print(f"  Cadenas: {', '.join(c['cadena'] for c in CHAINS)}  |  Fecha: {fecha}")
    print("=" * 55)

    all_rows, all_errores, cadenas_ok = [], [], []

    for chain in CHAINS:
        origen = chain.get("base_url") or chain["motor"]
        print(f"\n[INFO] Scrapeando {chain['cadena']} ({origen}) ...")
        try:
            rows, errores = scrape_cadena(chain)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            errores = [f"[{chain['cadena']}] ERROR HTTP {code}: {e}"]
            rows = []
        except requests.RequestException as e:
            errores = [f"[{chain['cadena']}] ERROR de red: {e}"]
            rows = []

        all_rows += rows
        all_errores += errores
        if rows:
            cadenas_ok.append(chain["cadena"])
            print(f"[OK] {chain['cadena']}: {len(rows)} cervezas")
        else:
            print(f"[WARN] {chain['cadena']}: sin datos, ver errores abajo")

    if not cadenas_ok:
        print("\n[ERROR] Ninguna cadena devolvio datos. Corta la corrida.")
        for e in all_errores:
            print("   -", e)
        sys.exit(1)

    destino = guardar_csv(all_rows, args.out_dir, fecha)
    con_desc = sum(1 for r in all_rows if r["descuento"] and r["descuento"] > 0)

    print(f"\n[OK] {len(all_rows)} filas guardadas ({con_desc} con descuento) de {len(cadenas_ok)}/{len(CHAINS)} cadenas")
    print(f"     -> {destino}")
    if all_errores:
        print(f"\n[WARN] {len(all_errores)} avisos (no rompieron la corrida):")
        for e in all_errores:
            print("   -", e)

    gha_out = os.environ.get("GITHUB_OUTPUT")
    if gha_out:
        with open(gha_out, "a", encoding="utf-8") as f:
            f.write(f"csv_path={destino.resolve()}\n")
            f.write(f"fecha={fecha}\n")


if __name__ == "__main__":
    main()
