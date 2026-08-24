"""
Configuracion de cadenas soportadas por el scraper.

La mayoria corre sobre VTEX (motor "vtex", scraper/vtex_client.py) y
expone el mismo catalog_system/pub/products/search publico, sin login.
Para sumar una cadena VTEX nueva: agregar una entrada aca con su
dominio y listo, no hace falta tocar el resto del pipeline.

Coto es distinto (motor "coto", scraper/coto_client.py): no es VTEX,
usa Constructor.io como buscador con una API key publica.

Jumbo/Disco/Vea (grupo Cencosud) tienen ademas un "promo_seller": no
usan el motor de promos estandar de VTEX, sino un endpoint propio
(`_v/search-promotions`) que exige un seller id de sucursal/deposito
especifico por cadena (no el sellerId "1" del catalogo) — ver el
docstring de vtex_client.fetch_promotions para como se encontro.

Mas Online (ex Chango Mas) tambien es VTEX, sin promo_seller propio
(usa el motor estandar de VTEX, igual que Carrefour/Dia). OJO: su
categoria de cervezas no cuelga de "bebidas/cervezas" como en el resto
-- el arbol de categorias de masonline.com.ar tiene "Cervezas" como
categoria de primer nivel, asi que el category_path correcto es
"cervezas" a secas (confirmado con /api/catalog_system/pub/category/tree/3).
"""

CHAINS = [
    {
        "cadena": "Carrefour",
        "motor": "vtex",
        "base_url": "https://www.carrefour.com.ar",
        "category_path": "bebidas/cervezas",
    },
    {
        "cadena": "Dia",
        "motor": "vtex",
        "base_url": "https://diaonline.supermercadosdia.com.ar",
        "category_path": "bebidas/cervezas",
    },
    {
        "cadena": "Jumbo",
        "motor": "vtex",
        "base_url": "https://www.jumbo.com.ar",
        "category_path": "bebidas/cervezas",
        "promo_seller": "jumboargentinaj5202martinez",
    },
    {
        "cadena": "Disco",
        "motor": "vtex",
        "base_url": "https://www.disco.com.ar",
        "category_path": "bebidas/cervezas",
        "promo_seller": "jumboargentinad061",
    },
    {
        "cadena": "Vea",
        "motor": "vtex",
        "base_url": "https://www.vea.com.ar",
        "category_path": "bebidas/cervezas",
        "promo_seller": "jumboargentinav700cordoba700",
    },
    {
        "cadena": "Coto",
        "motor": "coto",
        "search_term": "cerveza",
    },
    {
        "cadena": "Más Online",
        "motor": "vtex",
        "base_url": "https://www.masonline.com.ar",
        "category_path": "cervezas",
    },
]
