"""
Cliente para Coto, que NO corre sobre VTEX (plataforma propia ATG/Endeca)
pero usa Constructor.io como buscador de productos, con una API key
publica embebida en su JS de frontend (misma que usa la propia pagina
para renderizar resultados de busqueda, no es un endpoint privado).

A diferencia de VTEX (1 catalogo por dominio), Coto devuelve un precio
por CADA sucursal en el mismo request (`data.price`, lista de ~34
sucursales). Se fija en una sola sucursal (ver STORE_ID) para que el
historico sea comparable dia a dia, igual criterio que "Nunez" en
pedidosya-nunez/rappi-nunez. Ninguna sucursal de Coto en el barrio
Nunez (108, 170) tiene lista de precios online — de las que si tienen
catalogo digital completo, se eligio Saavedra (181, CABA), la mas
cercana geograficamente.

Descuentos: `data.discounts[0]` es el descuento publico de base (precio
de contado, sin tarjeta/membresia). Si hay un `discounts[1]` en
adelante suele ser un extra solo para "Comunidad Coto" (programa de
fidelidad) — se ignora a proposito, mismo criterio que el resto del
proyecto de no mezclar descuentos que no ve cualquier comprador.

Listados obsoletos: el indice de Constructor.io de Coto tiene productos
"fantasma" — SKUs viejos/discontinuados que nunca se purgaron, con un
precio desactualizado que nunca se volvio a tocar. Ejemplo real
detectado: "Cerveza Budweiser Botella 710 CC" (precio $572, un ~82% mas
barato que el precio real $3106 mostrado en la pagina) convivia en la
misma busqueda con "Cerveza Budweiser 710ml" (el SKU correcto y
actualizado, mismo producto fisico, EAN distinto). Barrido de todo el
catalogo de cerveza: **47% de los resultados (222/473)** comparten el
mismo patron sospechoso: precio identico en TODAS las sucursales +
`discounts` vacio + `store_availability` vacio. Se trata como listado
obsoleto y se descarta (ver `parece_obsoleto`) — mejor faltante que
mal, mismo criterio que el resto del proyecto.

Por el mismo motivo se saco el filtro anterior de "descartar si la
sucursal de referencia no esta en store_availability": ese filtro
estaba descartando el SKU *correcto* de Budweiser (su
store_availability no incluye la sucursal 181 aunque su precio para esa
sucursal es valido), mientras dejaba pasar el obsoleto (que tiene
store_availability vacio, no dispara el filtro). store_availability
resulto ser un campo demasiado inconsistente en los datos de Coto como
para usarlo de esa forma.
"""

import re
import time

import requests

CONSTRUCTOR_KEY = "key_r6xzz4IAoTWcipni"
CLIENT_VERSION = "ciojs-client-2.0.0"
SEARCH_URL = "https://ac.cnstrc.com/search/{term}"
STORE_ID = "181"   # Saavedra, CABA (ver docstring del modulo)
PAGE_SIZE = 100
MAX_PAGES = 20

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CALIBRE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|cc|lt|l)\b", re.I)
PACK_RE = re.compile(
    r"\bpack\b|\bcombo\b|\bunidades\b|\bsix\s*pack\b|\bx\s*\d+\b|\+\s*(copa|vaso|botella|regalo)",
    re.I,
)


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    return s


def fetch_search(s, term, max_pages=MAX_PAGES):
    """Trae todos los resultados de busqueda de Constructor.io para `term`,
    paginando hasta agotar total_num_results."""
    url = SEARCH_URL.format(term=term)
    results = []
    total = None
    for page in range(1, max_pages + 1):
        params = {
            "key": CONSTRUCTOR_KEY,
            "c": CLIENT_VERSION,
            "num_results_per_page": PAGE_SIZE,
            "page": page,
        }
        r = s.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        resp = data.get("response") or {}
        page_results = resp.get("results") or []
        if total is None:
            total = resp.get("total_num_results", 0)
        results.extend(page_results)
        if not page_results or len(results) >= total:
            break
        time.sleep(0.3)
    return results


def es_pack(nombre):
    return bool(PACK_RE.search(nombre or ""))


def calibre_de(nombre):
    m = CALIBRE_RE.search(nombre or "")
    if not m:
        return "-"
    num = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    ml = num * 1000 if unit in ("l", "lt") else num
    return f"{int(round(ml))} ml"


def _parse_money(text):
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", text)
    cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parece_obsoleto(d):
    """Heuristica para listados fantasma de Coto (ver docstring del
    modulo): sin disponibilidad declarada, sin descuento activo, y el
    mismo precio identico en todas las sucursales (>=5, para no
    disparar con productos que solo tienen unas pocas sucursales
    cargadas). Las 3 condiciones juntas son necesarias -- cualquiera
    de ellas sola es comun tambien en productos vigentes (ej. una
    marca chica sin promo hoy, con precio plano a nivel nacional)."""
    prices = [p.get("listPrice") for p in (d.get("price") or []) if p.get("listPrice") is not None]
    if len(prices) < 5:
        return False
    return (
        not d.get("store_availability")
        and not d.get("discounts")
        and len(set(prices)) == 1
    )


def producto_a_fila(cadena, result, marca_de_fn, store_id=STORE_ID):
    d = result.get("data") or {}
    nombre = (result.get("value") or d.get("sku_display_name") or "").strip()
    if not nombre:
        raise ValueError(f"producto sin nombre (id={d.get('id')})")

    if not nombre.lower().startswith("cerveza"):
        return None  # busqueda "cerveza" trae tambien vasos/copas/kits, no son el producto

    if es_pack(nombre):
        return None

    if parece_obsoleto(d):
        raise ValueError(
            f"listado obsoleto sospechoso (precio identico en todas las sucursales, "
            f"sin disponibilidad ni descuento): {nombre!r}"
        )

    price_entry = next((p for p in (d.get("price") or []) if p.get("store") == store_id), None)
    if not price_entry:
        return None  # sin precio para la sucursal de referencia

    fleje = price_entry.get("listPrice")
    if not fleje or fleje <= 0:
        return None

    precio = fleje
    promo_nominal = ""
    discounts = d.get("discounts") or []
    if discounts:
        base = discounts[0]
        parsed = _parse_money(base.get("discountPrice"))
        if parsed and 0 < parsed <= fleje:
            precio = parsed
            promo_nominal = (base.get("discountText") or "").strip()

    marca = marca_de_fn(nombre, d.get("product_brand"))
    descuento = int(round(max(1 - precio / fleje, 0.0) * 100)) if fleje else 0

    return {
        "cadena": cadena,
        "marca": marca,
        "descripcion": nombre,
        "calibre": calibre_de(nombre),
        "fleje": fleje,
        "precio": precio,
        "descuento": descuento,
        "promo_nominal": promo_nominal,
    }


def productos_a_filas(cadena, resultados, marca_de_fn, store_id=STORE_ID):
    rows, errores = [], []
    for r in resultados:
        try:
            row = producto_a_fila(cadena, r, marca_de_fn, store_id=store_id)
            if row is not None:
                rows.append(row)
        except Exception as e:  # noqa: BLE001 - por diseno: nunca cortar la corrida por 1 SKU
            pid = (r.get("data") or {}).get("id") if isinstance(r, dict) else "?"
            errores.append(f"[{cadena}] producto id={pid} descartado: {e}")
    return rows, errores
