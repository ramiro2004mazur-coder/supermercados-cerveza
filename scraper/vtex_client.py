"""
Cliente generico para el API publico de catalogo de VTEX
(catalog_system/pub/products/search), usado por Carrefour, Dia y —
cuando se sumen — Jumbo/Disco/Vea (las 3 corren sobre la misma
plataforma, confirmado inspeccionando sus paginas).

No requiere login ni headers especiales: es el mismo endpoint que usa la
pagina web para listar productos de una categoria. VTEX pagina de a
_from/_to (maximo 50 items por page) y devuelve el total en el header
"resources: X-Y/TOTAL".

Se filtran productos sin stock (AvailableQuantity <= 0 o precio <= 0) y
packs/combos (six-packs, "x6", "+ vaso/copa/botella"), igual criterio que
usa el scraper de Rappi para no mezclar precio-por-pack con precio unitario.

Promos por cantidad ("2do al X% OFF", detectado en Carrefour): no se
reflejan en Price/ListPrice, solo aparecen en commertialOffer.Teasers /
PromotionTeasers con un nombre tipo "PROMO-2do al 50% ... -Reg-2-50-...".
El sufijo "-Reg-{qty}-{pct}-" es machine-parseable: qty = cantidad minima
para activar la promo, pct = % OFF que se aplica a la ultima unidad. Se
calcula el precio efectivo promedio por unidad (ver `parse_qty_promo` /
`aplicar_promo_qty`) en vez de reportar 0% de descuento, que es lo que
hacia el scraper antes de esto.
"""

import re
import time

import requests

PAGE_SIZE = 50
MAX_PAGES = 60           # tope de seguridad (60*50 = 3000 productos)
REQUEST_DELAY = 0.35     # pausa entre paginas, para no forzar el sitio

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CALIBRE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|cc|lt|l)\b", re.I)
PACK_RE = re.compile(
    r"\bpack\b|\bcombo\b|\bsix\s*pack\b|\bx\s*\d+\b|\+\s*(copa|vaso|botella|regalo)",
    re.I,
)
PROMO_QTY_RE = re.compile(r"-Reg-(\d+)-(\d+)-")


def session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    })
    return s


def fetch_category(s, base_url, category_path, max_pages=MAX_PAGES):
    """Trae todos los productos de una categoria VTEX, paginando por
    _from/_to segun el total que devuelve el header 'resources'."""
    url = f"{base_url}/api/catalog_system/pub/products/search/{category_path}"
    items = []
    seen_ids = set()
    total = None
    for page in range(max_pages):
        frm = page * PAGE_SIZE
        to = frm + PAGE_SIZE - 1
        if total is not None and frm > total:
            break
        r = s.get(url, params={"map": "c,c", "_from": frm, "_to": to}, timeout=25)
        if r.status_code not in (200, 206):
            r.raise_for_status()
        if total is None:
            resources = r.headers.get("resources", "")
            m = re.search(r"/(\d+)$", resources)
            if m:
                total = int(m.group(1))
        data = r.json()
        if not data:
            break
        for p in data:
            pid = p.get("productId")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            items.append(p)
        if total is not None and len(seen_ids) >= total:
            break
        time.sleep(REQUEST_DELAY)
    return items


def es_pack(product_name):
    return bool(PACK_RE.search(product_name or ""))


def calibre_de(product_name):
    m = CALIBRE_RE.search(product_name or "")
    if not m:
        return "-"
    num = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    ml = num * 1000 if unit in ("l", "lt") else num
    return f"{int(round(ml))} ml"


def parse_qty_promo(offer):
    """Busca una promo tipo 'Nva unidad al X% OFF' en Teasers/PromotionTeasers
    y devuelve (cantidad_minima, pct_off, nombre_nominal) o None si no hay.
    Solo se toma la primera promo de este tipo que aparezca (no se vieron
    SKUs con mas de una en la inspeccion inicial de Carrefour)."""
    teasers = offer.get("PromotionTeasers") or offer.get("Teasers") or []
    for t in teasers:
        name = t.get("Name") or t.get("<Name>k__BackingField") or ""
        m = PROMO_QTY_RE.search(name)
        if not m:
            continue
        min_qty, pct = int(m.group(1)), int(m.group(2))
        if min_qty < 2 or not (0 < pct <= 100):
            continue
        nominal = name.split("-Reg-")[0].replace("PROMO-", "").strip()
        return min_qty, pct, nominal
    return None


def aplicar_promo_qty(precio_base, min_qty, pct):
    """Precio efectivo promedio por unidad si se compra la cantidad minima
    de la promo: (min_qty - 1) unidades al precio de lista + 1 unidad al
    (100 - pct)% de descuento, todo dividido por min_qty.
    Ej. Price=2589, '2do al 50%' -> (2589 + 2589*0.5) / 2 = 1941.75
    (25% de descuento efectivo, no el 50% nominal de la promo)."""
    return precio_base * ((min_qty - 1) + (1 - pct / 100)) / min_qty


def producto_a_fila(cadena, product, marca_de_fn):
    nombre = (product.get("productName") or "").strip()
    if not nombre:
        raise ValueError(f"producto sin nombre (productId={product.get('productId')})")

    items = product.get("items") or []
    if not items:
        raise ValueError(f"producto sin items/variantes: {nombre!r}")
    it = items[0]
    sellers = it.get("sellers") or []
    if not sellers:
        raise ValueError(f"producto sin seller: {nombre!r}")
    offer = sellers[0].get("commertialOffer") or {}

    precio = offer.get("Price")
    fleje = offer.get("ListPrice") or precio
    disponible = offer.get("AvailableQuantity", 0)
    if not precio or precio <= 0 or not disponible:
        return None  # sin stock / sin precio valido, se descarta sin error

    if es_pack(nombre):
        return None  # pack/combo, no es precio unitario

    marca = marca_de_fn(nombre, product.get("brand"))
    if not fleje or fleje < precio:
        fleje = precio

    promo_nominal = ""
    qty_promo = parse_qty_promo(offer)
    if qty_promo:
        min_qty, pct, promo_nominal = qty_promo
        precio = round(aplicar_promo_qty(precio, min_qty, pct), 2)

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


def productos_a_filas(cadena, productos, marca_de_fn):
    """Igual contrato que el resto de los scrapers: 1 producto que falla
    al parsearse se loguea y no corta la corrida."""
    rows, errores = [], []
    for p in productos:
        try:
            row = producto_a_fila(cadena, p, marca_de_fn)
            if row is not None:
                rows.append(row)
        except Exception as e:  # noqa: BLE001 - por diseno: nunca cortar la corrida por 1 SKU
            pid = p.get("productId") if isinstance(p, dict) else "?"
            errores.append(f"[{cadena}] producto id={pid} descartado: {e}")
    return rows, errores
