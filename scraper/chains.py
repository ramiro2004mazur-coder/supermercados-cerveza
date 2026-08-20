"""
Configuracion de cadenas soportadas por el scraper VTEX generico
(scraper/vtex_client.py). Todas corren sobre la misma plataforma (VTEX)
y exponen el mismo catalog_system/pub/products/search publico, sin login.

Para sumar una cadena nueva que tambien sea VTEX (ver README, seccion
"Roadmap de cadenas"): agregar una entrada aca con su dominio y listo,
no hace falta tocar el resto del pipeline.
"""

CHAINS = [
    {
        "cadena": "Carrefour",
        "base_url": "https://www.carrefour.com.ar",
        "category_path": "bebidas/cervezas",
    },
    {
        "cadena": "Dia",
        "base_url": "https://diaonline.supermercadosdia.com.ar",
        "category_path": "bebidas/cervezas",
    },
]
