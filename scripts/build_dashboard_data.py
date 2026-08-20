"""
Genera docs/data.json (lo que consume el dashboard) a partir de
data/history.json + data/fights_config.json, calculando stats por
marca+cadena y el listado de cadenas/fechas disponibles.

Se corre despues de cada ingest_run.py.
"""

import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DASHBOARD_DATA_PATH,
    FIGHTS_PATH,
    HISTORY_PATH,
    load_json,
    save_json,
)

ML_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|cc|lt|l)\b", re.I)


def volumen_l_de(sku_text):
    """Extrae el volumen exacto en litros del nombre del producto (ej.
    '473 ml' -> 0.473), para la pestana Precio/L. El calibre bucketeado
    del pivot (ej. '710/730') es un rango, no sirve para esta cuenta."""
    m = ML_RE.search(sku_text or "")
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    ml = num * 1000 if unit in ("l", "lt") else num
    return round(ml / 1000, 4) if ml > 0 else None


def build_stats(pivot):
    """Un stat por (cadena, marca, grupo, segmento): permite comparar la
    misma marca entre supermercados y contra la competencia dentro de
    cada uno."""
    groups = defaultdict(list)
    for p in pivot:
        for date, v in p["dates"].items():
            key = (p["cadena"], p["marca"], p["grupo"], p["segmento"])
            groups[key].append((date, v["dinamica"], v["ptc"]))

    stats = []
    for (cadena, marca, grupo, segmento), vals in groups.items():
        dates_seen = {v[0] for v in vals}
        dates_din = {v[0] for v in vals if v[1] > 0}
        stats.append(
            {
                "cadena": cadena,
                "marca": marca,
                "grupo": grupo,
                "segmento": segmento,
                "dias": len(dates_seen),
                "dias_dinamica": len(dates_din),
                "max_dinamica": max(v[1] for v in vals),
                "avg_dinamica": sum(v[1] for v in vals) / len(vals),
                "avg_ptc": sum(v[2] for v in vals) / len(vals),
            }
        )
    return stats


def main():
    history = load_json(HISTORY_PATH, None)
    if history is None:
        sys.exit(f"No existe {HISTORY_PATH}, corre scraper/scrape.py + ingest_run.py primero")

    fights = load_json(FIGHTS_PATH, [])
    pivot = history["pivot"]
    dates = sorted(history.get("dates") or {d for p in pivot for d in p["dates"]})
    cadenas = sorted({p["cadena"] for p in pivot})

    for p in pivot:
        p["volumen_l"] = volumen_l_de(p["sku"])

    registros_validos = sum(len(p["dates"]) for p in pivot)

    dashboard = {
        "pivot": pivot,
        "dates": dates,
        "cadenas": cadenas,
        "stats": build_stats(pivot),
        "fights": fights,
        "meta": {
            "generado": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "sku_rows": len(pivot),
            "registros_validos": registros_validos,
            "dias": len(dates),
            "cadenas": cadenas,
            "plataforma": "Supermercados online",
        },
    }

    save_json(DASHBOARD_DATA_PATH, dashboard)
    print(f"[OK] {DASHBOARD_DATA_PATH} generado: {len(pivot)} filas, {len(dates)} fechas, cadenas: {', '.join(cadenas)}")


if __name__ == "__main__":
    main()
