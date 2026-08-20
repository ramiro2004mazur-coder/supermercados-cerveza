# Supermercados online — histórico de precios de cerveza

Scraper + dashboard automatizado para trackear precios de cerveza (CMQ +
competencia) en las páginas de e-commerce de los principales
supermercados argentinos. Corre 1 vez por día (10:15 ART), consolida el
histórico y publica el dashboard en GitHub Pages. Hermano de
[pedidosya-nunez](https://github.com/ramiro2004mazur-coder/pedidosya-nunez)
y [rappi-nunez](https://github.com/ramiro2004mazur-coder/rappi-nunez)
(mismo criterio de categoría, formato de datos parecido, plataformas
distintas).

## Estado actual: Carrefour, Día, Jumbo, Disco y Vea

Arranque incremental pedido por el negocio: primero se validó
scraping → guardado → dashboard con Carrefour + Día, después se sumó el
resto de las cadenas VTEX de una. Hoy el scraper cubre **5 de las 7
cadenas** — faltan Coto y La Anónima.

## Por qué las VTEX primero (y lo que encontré al inspeccionar las 7)

Antes de programar nada inspeccioné las 7 páginas reales:

| Cadena | Plataforma | Anti-bot | Estado |
|---|---|---|---|
| **Carrefour** | VTEX | Ninguno (Cloudflare presente pero sin challenge) | ✅ Scraper activo |
| **Día** | VTEX | Ninguno | ✅ Scraper activo |
| **Jumbo** | VTEX | Ninguno | ✅ Scraper activo |
| **Disco** | VTEX | Ninguno | ✅ Scraper activo |
| **Vea** | VTEX | Ninguno | ✅ Scraper activo |
| Coto | Plataforma propia (no VTEX, JSF + Constructor.io) | Sin bloqueo evidente en la inspección inicial, pero la navegación por categoría es 100% AJAX (`/sitios/cdigi/constructor/search`), falta terminar de mapear la API | ⏸ Pendiente |
| La Anónima | Desconocida | La carga devolvió **403 Forbidden** en la primera visita — no está confirmado todavía si es anti-bot real o otra causa | ⏸ Pendiente, avisar antes de invertir tiempo si resulta ser un bloqueo duro |

Carrefour, Día, Jumbo, Disco y Vea corren todos sobre **VTEX** y exponen
el mismo API público de catálogo
(`/api/catalog_system/pub/products/search/...`), sin login, sin API key
y sin bloqueo anti-bot para este endpoint. Es el mismo patrón que usan
las propias páginas para listar productos — no es un endpoint "secreto".
Gracias a esto, `scraper/vtex_client.py` es **genérico**: sumar cada
cadena nueva fue agregar 3 líneas a `scraper/chains.py`, no escribir un
scraper nuevo (a diferencia de PedidosYa/Rappi, que necesitaron motores
completamente distintos por cadena).

### Bug de datos encontrado en Jumbo/Disco/Vea (grupo Cencosud)

El campo `ListPrice` que devuelve el API de estas 3 cadenas viene **roto**:
es sistemáticamente ~82.6x el precio real (`Price`) en casi todo el
catálogo — no es un descuento genuino, es basura de origen (probablemente
un precio de referencia viejo nunca actualizado). Si se usaba tal cual,
el dashboard mostraba "-99% de descuento" en case todo el catálogo de
esas 3 cadenas. Se detectó comparando varios SKUs a mano contra lo que
muestra la propia web (que no muestra tachado/descuento para esos
productos, solo el precio actual).

Fix en `scraper/vtex_client.py` (`LISTPRICE_SANITY_RATIO`): si
`ListPrice` supera 3x el `Price` actual, se descarta como no confiable y
se usa `Price` como `fleje` (0% de descuento "de lista", no se inventa
uno). El límite de 3x da margen de sobra: el descuento plano más grande
visto en datos reales (Carrefour) fue 40%, es decir ratio ~1.67x. Las
promos por cantidad ("2do al X%", ver más abajo) no dependen de
`ListPrice`, así que este fix no las afecta.

Coto y La Anónima quedan para cuando les toque el turno.

## Estructura

```
scraper/chains.py          config de cadenas soportadas (dominio + path de categoria VTEX)
scraper/vtex_client.py     cliente generico del API de catalogo VTEX (paginado, filtra packs/sin stock)
scraper/brands.py          deteccion de marca por nombre de producto (el campo "brand" de VTEX no es confiable)
scraper/scrape.py          orquesta todas las cadenas, guarda 1 CSV combinado por corrida
data/history.json          historico consolidado, fuente de verdad (1 fecha = 1 lectura por cadena+SKU)
data/catalog.json          clasificacion marca/sku -> grupo (CMQ/Competencia) y segmento
data/fights_config.json    "luchas" CMQ vs competencia, accesos rapidos de la pestana Comparar
data/raw/                  snapshot crudo de cada corrida (auditoria)
data/logs/                 avisos de SKUs sin clasificar / filas descartadas
docs/index.html            dashboard (esto es lo que sirve GitHub Pages)
docs/data.json             generado, no se edita a mano
scripts/ingest_run.py      mergea 1 corrida nueva en data/history.json
scripts/build_dashboard_data.py   data/history.json -> docs/data.json (stats por marca+cadena)
.github/workflows/scrape_and_deploy.yml   cron 10:15 ART
```

## Formato de datos

A diferencia de pedidosya-nunez/rappi-nunez (una sola tienda), acá cada
fila del pivot es única por **(cadena, marca, descripción)**: el mismo
SKU puede tener una serie de precios distinta en cada supermercado, así
que `cadena` es parte de la clave, no un atributo más. La clasificación
CMQ/Competencia en cambio se busca en `data/catalog.json` solo por
marca+descripción (sin cadena), porque la taxonomía de una marca es la
misma sin importar dónde se vendió.

```json
{
  "meta": {"plataforma": "Supermercados", "cadenas": ["Carrefour", "Dia"]},
  "dates": ["2026-08-20"],
  "pivot": [
    {
      "id": "carrefour-quilmes-cerveza-blanca-quilmes-ipa-473-ml",
      "cadena": "Carrefour",
      "marca": "Quilmes",
      "sku": "Cerveza blanca Quilmes Ipa 473 ml",
      "calibre": "473",
      "grupo": "CMQ",
      "segmento": "Core",
      "dates": {
        "2026-08-20": {"fleje": 2589.0, "ptc": 2589.0, "dinamica": 0.0}
      }
    }
  ]
}
```

## Criterios del scraper (mismo espíritu que Rappi/PedidosYa)

- **Solo categoría cerveza**: se recorre el árbol de categoría VTEX
  `Bebidas/Cervezas` completo (no búsqueda por keyword, que puede traer
  ruido) — es la misma taxonomía en Carrefour y Día.
- **Se excluyen packs/combos**: sixpacks, "x6"/"x10", y bundles tipo
  "+ copa"/"+ vaso" se descartan por regex sobre el nombre — no queremos
  mezclar precio-por-pack con precio unitario (mismo criterio que
  `rappi-nunez`).
- **Se excluyen productos sin stock o sin precio válido** (`AvailableQuantity`
  o `Price` en 0) — VTEX los sigue listando en la categoría aunque no se
  puedan comprar.
- **Marca por nombre, no por el campo `brand` de VTEX**: se detectó que
  varias cadenas taggean mal la marca (ej. Carrefour devuelve `"brand":
  "Generico"` para un Brahma, o `"brand": "Barbara"` para un Kunstmann).
  `scraper/brands.py` reconoce la marca por patrones sobre el nombre del
  producto primero, y solo cae al campo de VTEX si ningún patrón matchea
  — mismo problema y misma solución que ya se había validado en el
  scraper de Rappi.
- **Resiliente por SKU**: si un producto puntual falla al parsearse, se
  descarta y se loguea (no corta la corrida). Si **todas** las cadenas
  fallan en una corrida, sale con error (eso sí debe frenar el job de
  CI); si solo alguna cadena falla, se sigue con las demás.

## Setup único (a hacer vos, no lo hace el workflow)

1. Crear el repo en GitHub y pushear este proyecto.
2. **Settings → Pages → Source: "Deploy from a branch" → Branch: `main` / `docs`.**
   Cada vez que el workflow commitea un cambio en `docs/data.json`,
   GitHub Pages se re-despliega solo.
3. Revisar `data/catalog.json`: se pre-cargó clasificando ~150 de 183
   SKUs detectados en la primera corrida (los mismos ~30 nombres de
   marca CMQ/Competencia que ya usan pedidosya-nunez/rappi-nunez). El
   resto (marcas artesanales/importadas: República Artesanal,
   Mecklenburger, Denninghoffs, Bierhaus, etc.) quedó como "Sin
   clasificar" — revisar y completar a mano si interesa trackearlas.
4. No hace falta ninguna variable de entorno hoy (el API de VTEX es
   público, sin login) — ver `.env.example` por si se necesita más
   adelante (ej. proxy).
5. **Sin confirmar todavía si GitHub Actions puede pegarle a VTEX sin
   bloqueo desde su IP de datacenter** (a diferencia de PedidosYa, que sí
   bloquea). El cron queda activo desde el arranque porque no hay
   evidencia de bloqueo, pero conviene revisar el primer run programado
   (o disparar el workflow a mano desde *Actions*) por si hace falta el
   mismo fallback local que usa `pedidosya-nunez`.

## Correr manualmente

```bash
pip install -r scraper/requirements.txt
cd scraper && python3 scrape.py --out-dir ../data/raw && cd ..
python3 scripts/ingest_run.py --csv data/raw/2026-08-20.csv --date 2026-08-20
python3 scripts/build_dashboard_data.py
```

## Roadmap de cadenas

1. ~~Carrefour~~ ✅
2. ~~Día~~ ✅
3. ~~Jumbo / Disco / Vea~~ ✅ — mismo motor VTEX, agregadas a `scraper/chains.py`.
4. Coto — plataforma propia (JSF + Constructor.io), falta terminar de
   mapear la API de búsqueda por categoría antes de programar el scraper.
5. La Anónima — devolvió 403 en la primera visita, falta confirmar si es
   un bloqueo anti-bot real antes de invertir tiempo.

## Dashboard vs Rappi/PedidosYa

Por ahora el dashboard de este repo solo compara las cadenas de
supermercado entre sí (Carrefour vs Día vs las que se vayan sumando).
Integrar los canales de delivery (Rappi, PedidosYa) en una misma vista
queda para una fase futura, una vez que el dashboard de supermercados
esté sólido con las 7 cadenas.
