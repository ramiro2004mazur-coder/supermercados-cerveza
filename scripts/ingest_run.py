"""
Mergea un CSV crudo de una corrida del scraper (data/raw/YYYY-MM-DD.csv,
con filas de todas las cadenas) dentro de data/history.json. Se corre
despues de cada scrapeo (1 vez por dia).

Cada fila del pivot es unica por (cadena, marca, descripcion): el mismo
SKU puede tener una serie de precios distinta en cada supermercado, asi
que "cadena" es parte de la clave, no solo un atributo mas. La
clasificacion (grupo/segmento) en cambio se busca en data/catalog.json
por marca+descripcion sin cadena, porque la taxonomia CMQ/Competencia de
una marca es la misma sin importar donde se vendio.

Nunca revienta por una fila individual mala: la loguea en
data/logs/ingest_warnings.log y sigue con las demas.

Sanity check de precio vs. historico: si el precio nuevo de un SKU cae
mas de SOSPECHA_CAIDA (50%) o sube mas de SOSPECHA_SUBA (100%) respecto
a la ultima lectura de ese mismo SKU, no se descarta (podria ser una
promo real muy agresiva) pero se marca "sospechoso": true en esa fecha
del pivot y se loguea — asi el dashboard puede resaltarlo en vez de
tratarlo como un dato mas. Aplica a cualquier cadena, no solo a la que
disparo el caso (Coto/Budweiser, ver README).

Uso:
    python3 scripts/ingest_run.py --csv data/raw/2026-08-20.csv --date 2026-08-20
"""

import argparse
import csv as csvmod
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    CATALOG_PATH,
    HISTORY_PATH,
    bucket_calibre,
    catalog_key,
    load_json,
    log_warning,
    pivot_key,
    save_json,
    slugify,
)

SOSPECHA_CAIDA = 0.5    # precio nuevo < 50% del anterior -> sospechoso
SOSPECHA_SUBA = 2.0     # precio nuevo > 200% del anterior -> sospechoso


def detectar_sospechoso(entry, date_key, precio_nuevo):
    """Compara contra la lectura mas reciente anterior a date_key (no
    necesariamente ayer -- puede haber huecos). None si no hay historico
    previo para comparar (SKU nuevo)."""
    fechas_previas = sorted(d for d in entry["dates"] if d < date_key)
    if not fechas_previas:
        return None
    anterior = entry["dates"][fechas_previas[-1]]["ptc"]
    if not anterior:
        return None
    ratio = precio_nuevo / anterior
    if ratio < SOSPECHA_CAIDA:
        return f"cayo {(1-ratio)*100:.0f}% vs {fechas_previas[-1]} (${anterior:.0f} -> ${precio_nuevo:.0f})"
    if ratio > SOSPECHA_SUBA:
        return f"subio {(ratio-1)*100:.0f}% vs {fechas_previas[-1]} (${anterior:.0f} -> ${precio_nuevo:.0f})"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"No existe {csv_path}")

    catalog_list = load_json(CATALOG_PATH, [])
    catalog = {catalog_key(c["marca"], c["sku"]): c for c in catalog_list}

    history = load_json(
        HISTORY_PATH,
        {"meta": {"plataforma": "Supermercados"}, "dates": [], "pivot": []},
    )
    pivot_by_key = {
        pivot_key(p["cadena"], p["marca"], p["sku"]): p for p in history["pivot"]
    }

    date_key = args.date

    errores = 0
    nuevos = 0
    ok = 0
    sospechosos = 0
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csvmod.DictReader(f, delimiter=";")
        for row in reader:
            try:
                cadena = (row.get("cadena") or "").strip()
                marca = (row.get("marca") or "").strip()
                descripcion = (row.get("descripcion") or "").strip()
                precio_raw = row.get("precio")
                if not cadena or not marca or not descripcion or not precio_raw:
                    raise ValueError("fila sin cadena/marca/descripcion/precio")

                ckey = catalog_key(marca, descripcion)
                cat = catalog.get(ckey)
                if cat is None:
                    cat = {
                        "id": slugify(marca, descripcion),
                        "marca": marca,
                        "sku": descripcion,
                        "calibre": bucket_calibre(row.get("calibre")),
                        "grupo": "Sin clasificar",
                        "segmento": "Sin clasificar",
                    }
                    catalog[ckey] = cat
                    log_warning(
                        f"{csv_path.name}: SKU nuevo sin catalogo -> "
                        f"'{cadena} | {marca} | {descripcion}' "
                        "(agregado como 'Sin clasificar', revisar data/catalog.json)",
                        log_file="ingest_warnings.log",
                    )
                    nuevos += 1

                pkey = pivot_key(cadena, marca, descripcion)
                entry = pivot_by_key.get(pkey)
                if entry is None:
                    entry = {
                        "id": slugify(cadena, marca, descripcion),
                        "cadena": cadena,
                        "marca": cat["marca"],
                        "sku": cat["sku"],
                        "calibre": cat["calibre"],
                        "grupo": cat["grupo"],
                        "segmento": cat["segmento"],
                        "dates": {},
                    }
                    pivot_by_key[pkey] = entry

                precio = float(precio_raw)
                fleje = float(row.get("fleje") or precio)
                dinamica = round(max(1 - precio / fleje, 0.0), 4) if fleje else 0.0
                motivo_sospecha = detectar_sospechoso(entry, date_key, precio)
                fecha_entry = {
                    "fleje": fleje,
                    "ptc": precio,
                    "dinamica": dinamica,
                    "promo_nominal": (row.get("promo_nominal") or "").strip(),
                }
                if motivo_sospecha:
                    fecha_entry["sospechoso"] = True
                    sospechosos += 1
                    log_warning(
                        f"{csv_path.name}: precio sospechoso -> "
                        f"'{cadena} | {marca} | {descripcion}': {motivo_sospecha}",
                        log_file="ingest_warnings.log",
                    )
                entry["dates"][date_key] = fecha_entry
                ok += 1
            except Exception as e:  # noqa: BLE001 - una fila mala no debe tumbar la corrida
                errores += 1
                log_warning(
                    f"{csv_path.name}: fila descartada ({e}): {row}",
                    log_file="ingest_warnings.log",
                )

    pivot = list(pivot_by_key.values())
    dates = sorted({d for p in pivot for d in p["dates"]})

    history["pivot"] = pivot
    history["dates"] = dates
    history["meta"]["ultima_corrida"] = datetime.now(timezone.utc).isoformat()
    history["meta"]["sku_count"] = len(pivot)
    history["meta"]["cadenas"] = sorted({p["cadena"] for p in pivot})

    save_json(HISTORY_PATH, history)
    save_json(CATALOG_PATH, list(catalog.values()))

    print(f"[OK] {date_key}: {ok} filas ok, {nuevos} SKUs nuevos, {errores} filas con error, "
          f"{sospechosos} precios sospechosos")
    if errores or sospechosos:
        print("     ver data/logs/ingest_warnings.log")


if __name__ == "__main__":
    main()
