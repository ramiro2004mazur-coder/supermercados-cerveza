"""
Configuracion de cadenas soportadas por el scraper.

La mayoria corre sobre VTEX (motor "vtex", scraper/vtex_client.py) y
expone el mismo catalog_system/pub/products/search publico, sin login.
Para sumar una cadena VTEX nueva: agregar una entrada aca con su
dominio y listo, no hace falta tocar el resto del pipeline.

Coto es distinto (motor "coto", scraper/coto_client.py): no es VTEX,
usa Constructor.io como buscador con una API key publica.
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
    },
    {
        "cadena": "Disco",
        "motor": "vtex",
        "base_url": "https://www.disco.com.ar",
        "category_path": "bebidas/cervezas",
    },
    {
        "cadena": "Vea",
        "motor": "vtex",
        "base_url": "https://www.vea.com.ar",
        "category_path": "bebidas/cervezas",
    },
    {
        "cadena": "Coto",
        "motor": "coto",
        "search_term": "cerveza",
    },
]
