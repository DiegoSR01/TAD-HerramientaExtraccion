# Web Scraper Inteligente

Aplicación local, configurable y modular para inspeccionar una URL, definir selectores, adquirir contenido, limpiarlo y exportarlo. Usa Python, Requests, BeautifulSoup, Pandas y Selenium; Playwright, Excel, PostgreSQL y MongoDB se pueden habilitar como extras.

Para instrucciones detalladas de instalación, operación, arquitectura y desarrollo, consulta la [Guía de desarrollo y operación](GUIA_DESARROLLO_Y_OPERACION.md).

## Inicio rápido en Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[all]"
python -m smart_scraper.gui
```

Chrome y Selenium Manager deben estar disponibles para Selenium. Para Playwright:

```powershell
python -m playwright install chromium
```

También se puede instalar con `pip install -r requirements.txt` y abrir la interfaz con `python -m smart_scraper.gui`.

## Uso

1. Ingresa una URL `http`/`https` y pulsa **Inspeccionar**. El diagnóstico busca señales HTML/JavaScript, endpoints visibles en el HTML, paginación, carga bajo demanda, formularios, autenticación y CAPTCHA.
2. Indica un selector CSS de elementos repetidos y campos con el formato `nombre=selector`. `nombre*` marca un campo requerido y `nombre=selector::href` lee un atributo.
3. Para API JSON elige `api`, confirma que tienes autorización y define opcionalmente una ruta como `items` o `data.results`. Los campos usan rutas separadas por puntos (`product.name`).
4. Ajusta el límite, la pausa y, si aplica, la paginación, los desplazamientos o clics limitados en un botón de carga que hayas identificado. Elige el formato y pulsa **Extraer y guardar**.

El programa exporta datos, linaje por campo, perfiles del sitio sin encabezados secretos, logs y un informe JSON. Las ejecuciones sucesivas comparan campos, endpoints detectables y volumen de registros. Los perfiles se guardan en la carpeta `profiles` dentro del destino.

### Formatos

CSV, Excel (`.xlsx`), JSON y SQLite están disponibles localmente. PostgreSQL requiere `pip install ".[postgres]"` y `SCRAPER_POSTGRES_DSN`; MongoDB requiere `pip install ".[mongodb]"` y `SCRAPER_MONGODB_URI`. No guardes esas cadenas en el código ni en perfiles.

## Arquitectura: siete módulos

| Módulo | Archivo | Responsabilidad |
|---|---|---|
| 1. Configuración | `smart_scraper/config.py` | URL, límites, selectores, campos y perfiles |
| 2. Inspección y diagnóstico | `smart_scraper/inspector.py` | DOM/HTML, JavaScript, API hints, carga y restricciones |
| 3. Motor de extracción | `smart_scraper/extractor.py` | Requests, Selenium, Playwright y endpoint API autorizado |
| 4. Selección de información | `smart_scraper/selection.py` | Selectores CSS, rutas JSON y tablas |
| 5. Transformación y calidad | `smart_scraper/transform.py` | Limpieza, deduplicación, validación y linaje |
| 6. Almacenamiento | `smart_scraper/storage.py` | CSV, Excel, JSON, SQLite y conectores opcionales |
| 7. Monitoreo | `smart_scraper/monitoring.py` | Logs y reportes de ejecución |

`smart_scraper/app.py` coordina los módulos y `smart_scraper/gui.py` implementa la interfaz Tkinter.

## Seguridad, límites y uso responsable

- Solo inspecciona la URL ingresada; no rastrea dominios ni ejecuta pruebas masivas. La configuración limita la respuesta a 2 MB, a 1.000 registros, 10 páginas y cinco scrolls, con pausa mínima de un segundo.
- CAPTCHAs, challenges, respuestas 401/403 y 429 detienen la ejecución. No resuelve CAPTCHA, evade autenticación, rota proxies ni intenta sortear controles.
- Las credenciales se ingresan en memoria mediante encabezados autorizados y no se escriben en el perfil. En sitios con login, usa únicamente un mecanismo y una cuenta autorizados.
- Antes de ejecutar, verifica términos de uso, `robots.txt`, privacidad, derechos sobre los datos, permisos del endpoint y límites del servicio. Una respuesta pública no equivale a autorización.
- El diagnóstico es heurístico: detecta pistas de APIs embebidas en HTML, pero no captura exhaustivamente el tráfico XHR/Fetch del navegador ni deduce por sí solo si un uso es legal.

## Pruebas

```powershell
pytest
```

Las pruebas usan un servidor HTTP local con sitios simulados; no envían solicitudes a páginas públicas. El informe en [docs/INFORME_TECNICO.md](docs/INFORME_TECNICO.md) distingue esa evidencia de una evaluación legal o de pruebas en cinco dominios externos.

## Dataset de ejemplo

El dataset procesado real (100 libros de books.toscrape.com en SQLite, CSV y Excel, con linaje) está en [datasets/](datasets/README.md); se regenera con `python scripts/build_dataset.py`.

[examples/sample_dataset.csv](examples/sample_dataset.csv) y [examples/sample_lineage.csv](examples/sample_lineage.csv) contienen datos sintéticos ilustrativos, no datos adquiridos de un sitio público.
