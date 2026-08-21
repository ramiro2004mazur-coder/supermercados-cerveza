# CLAUDE.md

Guía para trabajar en este repo con Claude Code (u otro asistente).

## 1. Qué es este proyecto

Scraper + dashboard de precios de **cerveza** (CMQ vs. Competencia) en
supermercados online argentinos. Corre 1 vez por día, guarda un
histórico diario por SKU y cadena, y publica un dashboard estático en
GitHub Pages.

Hermano de [pedidosya-nunez](https://github.com/ramiro2004mazur-coder/pedidosya-nunez)
y [rappi-nunez](https://github.com/ramiro2004mazur-coder/rappi-nunez)
(mismo criterio de categoría — solo cerveza, sin packs/combos — y
espíritu de dashboard), pero para supermercados en vez de delivery.

**Cadenas cubiertas hoy (6 de 7):** Carrefour, Día, Jumbo, Disco, Vea y
Coto. Falta **La Anónima** — tiene anti-bot real confirmado (403 ante
ciertos patrones de request), no está scrapeada todavía.

## 2. Cómo correrlo manualmente

```bash
pip install -r scraper/requirements.txt

cd scraper
python3 scrape.py --out-dir ../data/raw
cd ..

python3 scripts/ingest_run.py --csv data/raw/YYYY-MM-DD.csv --date YYYY-MM-DD
python3 scripts/build_dashboard_data.py
```

`scrape.py` recorre todas las cadenas de `scraper/chains.py` y guarda
**un solo CSV combinado** en `data/raw/YYYY-MM-DD.csv` (columna
`cadena` identifica cada fila). Sin `--fecha`, usa la fecha de hoy en
horario ART.

Para ver el dashboard localmente: `python3 -m http.server` desde
`docs/` y abrir `http://localhost:8000`.

## 3. Estructura

```
scraper/chains.py               config de cadenas: motor (vtex|coto), dominio, category_path o search_term
scraper/vtex_client.py          cliente generico VTEX (Carrefour, Dia, Jumbo, Disco, Vea)
scraper/coto_client.py          cliente de Coto (Constructor.io, NO es VTEX)
scraper/brands.py               deteccion de marca por nombre de producto
scraper/scrape.py               orquesta todas las cadenas segun su "motor", guarda 1 CSV combinado

data/raw/YYYY-MM-DD.csv         snapshot crudo de cada corrida (auditoria, 1 archivo por dia)
data/history.json               HISTORICO CONSOLIDADO — fuente de verdad. 1 fila de "pivot" por
                                 (cadena, marca, descripcion), con un objeto por fecha:
                                 {fleje, ptc, dinamica, promo_nominal, sospechoso?}
data/catalog.json               clasificacion marca/sku -> grupo (CMQ/Competencia) y segmento
data/fights_config.json         "luchas" CMQ vs competencia para la pestana Comparar del dashboard
data/logs/ingest_warnings.log   SKUs sin clasificar, filas descartadas, precios sospechosos

docs/index.html                 dashboard (lo sirve GitHub Pages)
docs/data.json                  GENERADO por build_dashboard_data.py, no se edita a mano

scripts/ingest_run.py           mergea 1 CSV crudo dentro de data/history.json (ver sanity check, seccion 5)
scripts/build_dashboard_data.py data/history.json -> docs/data.json (stats por marca+cadena)
scripts/common.py               helpers compartidos (normalizacion, slugify, buckets de calibre)
```

**Dónde está la lógica de parseo de precio por cadena:**
- VTEX (Carrefour/Día/Jumbo/Disco/Vea): `scraper/vtex_client.py`,
  función `producto_a_fila()`. Lee `commertialOffer.Price`/`ListPrice`
  del API pública de catálogo VTEX.
- Coto: `scraper/coto_client.py`, función `producto_a_fila()`. Lee
  `data.price[]` (un precio por sucursal) del buscador Constructor.io.

**Formato de `data/history.json`** (1 fila de pivot):
```json
{
  "id": "coto-budweiser-cerveza-budweiser-710ml",
  "cadena": "Coto",
  "marca": "Budweiser",
  "sku": "Cerveza Budweiser 710ml",
  "calibre": "710/730",
  "grupo": "CMQ",
  "segmento": "Core",
  "dates": {
    "2026-08-21": {"fleje": 4142.0, "ptc": 3106.5, "dinamica": 0.25, "promo_nominal": "25%Dto"}
  }
}
```
`fleje` = precio de lista, `ptc` = precio final al consumidor,
`dinamica` = 1 - ptc/fleje. Si un día viene marcado `"sospechoso": true`
en su objeto de fecha, ver sección 5.

## 4. Automatización

`.github/workflows/scrape_and_deploy.yml`:
- **Cron: `15 13 * * *`** (10:15 ART), + `workflow_dispatch` para
  disparo manual desde la pestaña *Actions*.
- Flujo: `scrape.py` → `ingest_run.py` → `build_dashboard_data.py` →
  commit + push de `data/` y `docs/data.json` (si hubo cambios) → ese
  push dispara el redeploy de GitHub Pages automáticamente (Pages está
  configurado como "Deploy from a branch: main / docs").
- Si una cadena falla, se loguea y se sigue con las demás — solo corta
  la corrida si **todas** fallan.
- Logs de errores/sospechosos se suben como artifact de la corrida
  (`data/logs/`), 30 días de retención.

## 5. Reglas importantes

### No tocar la lógica de parseo de precio sin avisar antes

`producto_a_fila()` en `vtex_client.py` y `coto_client.py` (y las
funciones que llama: `parse_qty_promo`, `aplicar_promo_qty`,
`parece_obsoleto`, `fetch_promotions`) son el corazón del scraper. Un
cambio ahí sin entender el contexto puede:
- Romper el histórico ya guardado (los `fleje`/`ptc` quedan
  inconsistentes entre fechas).
- Volver a introducir bugs ya resueltos y documentados en el README
  (ver "Bug de VTEX...", "Cencosud no usa las promos...", "Coto tiene
  listados fantasma...").

Ya pasó una vez: Coto devolvía **$572** para Budweiser 710ml cuando el
precio real en la página era **$3.100** — no era un bug de parseo, era
un producto duplicado/obsoleto en el índice de búsqueda de Coto (ver
`parece_obsoleto()` en `coto_client.py` y el README, sección "Coto
tiene listados fantasma"). Antes de tocar cualquiera de estas
funciones: leer el docstring del módulo entero (explica cada bug ya
encontrado y por qué el fix es como es) y, si el cambio no es un fix
puntual ya acordado, avisar antes de aplicarlo.

### Sanity check de precio vs. histórico (ya implementado)

`scripts/ingest_run.py`, función `detectar_sospechoso()`: compara cada
precio nuevo contra la última lectura previa de ese mismo SKU (mismo
`cadena`+`marca`+`descripcion`). Si cae más de 50% (`SOSPECHA_CAIDA`) o
sube más de 100% (`SOSPECHA_SUBA`), **no se descarta** el dato (podría
ser una promo real muy agresiva) pero se marca `"sospechoso": true` en
esa fecha del pivot y se loguea en `data/logs/ingest_warnings.log`. El
dashboard (`docs/index.html`) resalta esas celdas con fondo de alerta +
ícono ⚠. No hace falta agregarlo — ya está activo para las 6 cadenas.

### Otras convenciones del pipeline

- **Resiliente por SKU**: 1 producto que falla al parsearse se loguea
  y se descarta, nunca corta la corrida. Si **toda** una cadena falla,
  se loguea y se sigue con las demás.
- **Mejor faltante que mal**: ante datos dudosos (ListPrice roto en
  Cencosud, listados fantasma en Coto), el criterio siempre fue
  descartar el dato y dejar el hueco visible (`—` en el dashboard),
  nunca inventar o adivinar un valor.
- Packs/combos y productos sin stock se excluyen siempre (no se
  compara precio-por-pack con precio unitario).
- La clasificación CMQ/Competencia (`data/catalog.json`) es por
  `marca+descripcion`, sin cadena — la taxonomía de una marca no
  depende de dónde se vendió. El pivot de precios sí incluye `cadena`
  en su clave, porque el mismo SKU tiene una serie de precios distinta
  en cada supermercado.

## 6. Estado actual (resumen)

| Cadena | Motor | Estado |
|---|---|---|
| Carrefour | VTEX | ✅ Activo |
| Día | VTEX | ✅ Activo |
| Jumbo | VTEX + promos propietarias Cencosud | ✅ Activo |
| Disco | VTEX + promos propietarias Cencosud | ✅ Activo |
| Vea | VTEX + promos propietarias Cencosud | ✅ Activo |
| Coto | Constructor.io | ✅ Activo (con filtro de listados fantasma) |
| La Anónima | — | ⏸ Pendiente, anti-bot real confirmado |

Para el detalle de cada bug encontrado y cómo se resolvió (con
ejemplos reales de request/response), ver el **README.md** — tiene la
bitácora completa de la investigación de cada cadena.
