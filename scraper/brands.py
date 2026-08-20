"""
Deteccion de marca a partir del nombre del producto.

El campo "brand" que devuelve VTEX es poco confiable en varias cadenas
(ej. Carrefour): hay productos de Brahma etiquetados "brand": "Generico",
o de Kunstmann etiquetados "brand": "Barbara" (marca de otro producto mal
cargada). Mismo problema ya detectado en el scraper de Rappi. Por eso,
igual que alli, se prioriza reconocer la marca por el nombre del producto
con esta lista de patrones (orden importa: mas especifico primero) y solo
se cae al campo "brand" de VTEX si ningun patron matchea.
"""

import re

# Alineado con el roster de marcas ya usado en pedidosya-nunez/rappi-nunez
# (data/catalog.json) mas las marcas adicionales que aparecen en las
# categorias de cerveza de los supermercados.
NAME_BRAND_PATTERNS = [
    ("Andes Origen", r"andes\s*origen"),
    ("Bajo Cero", r"bajo\s*cero"),
    ("Salta Cautiva", r"salta\s+cautiva"),
    ("Estrella De Galicia", r"estrella\s*(de\s*)?galicia"),
    ("Michelob Ultra", r"michelob\s*ultra|ultra\s*michelob"),
    ("Pampa Brewing", r"pampa\s*brewing"),
    ("Peñon del Aguila", r"pe[ñn]o?n\s*del\s*[aá]guila"),
    ("Quilmes", r"quilmes"),
    ("Stella Artois", r"stella\s*artois"),
    ("Budweiser", r"budweiser"),
    ("Corona", r"corona"),
    ("Michelob", r"michelob"),
    ("Patagonia", r"patagonia"),
    ("Andes", r"\bandes\b"),
    ("Brahma", r"brahma"),
    ("Heineken", r"heineken"),
    ("Amstel", r"amstel"),
    ("Schneider", r"schneider|scheider"),
    ("Imperial", r"imperial"),
    ("Cordoba", r"c[oó]rdoba"),
    ("Ortuzar", r"ortuzar"),
    ("Salta", r"\bsalta\b"),
    ("Kunstmann", r"kunstmann"),
    ("Antares", r"antares"),
    ("Pampa", r"\bpampa\b"),
    ("Rabieta", r"rabieta|rabiata"),
    ("Grolsch", r"grolsch|golsch"),
    ("Guinness", r"guinness|guinnes"),
    ("Bitburger", r"bitburge?r?"),
    ("Kostritzer", r"k[oö]stritzer"),
    ("Warsteiner", r"warsteiner"),
    ("Peroni", r"peroni"),
    ("Miller", r"miller"),
    ("Blue Moon", r"blue\s*moon"),
    ("Asahi", r"asahi"),
    ("1890", r"\b1890\b"),
    ("Temple", r"\btemple\b"),
    ("Goose Island", r"goose\s*island"),
    ("Starberg", r"starberg"),
    ("Santa Fe", r"santa\s*f[ée]"),
    ("Sol", r"\bsol\b"),
    ("Beepure", r"beepure"),
    ("Bierhaus", r"bierhaus"),
]


def marca_de(product_name, vtex_brand=None):
    nombre = (product_name or "").lower()
    for marca, pattern in NAME_BRAND_PATTERNS:
        if re.search(pattern, nombre):
            return marca
    brand = (vtex_brand or "").strip()
    if brand and brand.lower() not in ("generico", "genérico", "sin marca"):
        # VTEX a veces devuelve la marca en mayusculas (ej. "IMPERIAL"); se
        # normaliza a Title Case para no duplicar grupos en el dashboard
        # (ej. "Imperial" vs "IMPERIAL" tratados como marcas distintas).
        return brand if not brand.isupper() else brand.title()
    return ""
