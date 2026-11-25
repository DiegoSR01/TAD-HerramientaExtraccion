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
2. **Selección automática:** deja vacíos el selector de registros y los campos. Al pulsar **Inspeccionar** la herramienta detecta el grupo de elementos repetidos (tarjetas, filas de tabla, artículos), un campo por cada texto y atributo útil (`href`, `src`, `title`, `alt`, `datetime`) y el enlace de siguiente página, y los escribe en el formulario para que los revises o edites. Si los ejecutas vacíos, se detectan sobre la primera página obtenida (con Selenium/Playwright, ya renderizada) y quedan en el perfil y en `auto_selection` del informe. Si prefieres hacerlo a mano: campos con el formato `nombre=selector`; `nombre*` marca un campo requerido, `nombre=selector::href` lee un atributo y `:scope` es el propio registro.
3. Para API JSON elige `api`, confirma que tienes autorización y define opcionalmente una ruta como `items` o `data.results`. Los campos usan rutas separadas por puntos (`product.name`).
4. Ajusta el límite, la pausa y, si aplica, la paginación, los desplazamientos o clics limitados en un botón de carga que hayas identificado. Elige el formato y pulsa **Extraer y guardar**.

Mientras corre, un **panel de progreso** muestra el flujo de 9 pasos (ingreso de URL, diagnóstico, presentación de resultados, selección de datos, configuración, ejecución del motor, limpieza y validación, almacenamiento y reporte final), una barra con tiempo transcurrido, el **escenario detectado y la estrategia recomendada** (requests, selenium, api o detener; en naranja como INCIDENCIA cuando se bloquea) y un log con marcas de tiempo.

El programa exporta datos, linaje por campo, perfiles del sitio sin encabezados secretos, logs y un informe JSON. Las ejecuciones sucesivas comparan campos y columnas nuevas, selectores, estructura JSON, endpoints detectables y volumen de registros (diferencia y porcentaje). Los perfiles se guardan en la carpeta `profiles` dentro del destino.

### Formatos

CSV, Excel (`.xlsx`), JSON y SQLite están disponibles localmente. PostgreSQL requiere `pip install ".[postgres]"` y `SCRAPER_POSTGRES_DSN`; MongoDB requiere `pip install ".[mongodb]"` y `SCRAPER_MONGODB_URI`. No guardes esas cadenas en el código ni en perfiles.

## Arquitectura: siete módulos y un módulo de apoyo

| Módulo | Archivo | Responsabilidad |
|---|---|---|
| 1. Configuración | `smart_scraper/config.py` | URL, límites, selectores, campos y perfiles |
| 2. Inspección y diagnóstico | `smart_scraper/inspector.py` | DOM/HTML, JavaScript, API hints, carga y restricciones |
| 3. Motor de extracción | `smart_scraper/extractor.py` | Requests, Selenium, Playwright y endpoint API autorizado |
| 4. Selección de información | `smart_scraper/selection.py` | Selectores CSS, rutas JSON y tablas |
| 5. Transformación y calidad | `smart_scraper/transform.py` | Limpieza, deduplicación, validación y linaje |
| 6. Almacenamiento | `smart_scraper/storage.py` | CSV, Excel, JSON, SQLite y conectores opcionales |
| 7. Monitoreo | `smart_scraper/monitoring.py` | Logs y reportes de ejecución |

| Apoyo | `smart_scraper/estrategia.py` | Clasifica el escenario detectado (`classify_scenario`) y recomienda requests, selenium, api o detener |
| Apoyo | `smart_scraper/autoselect.py` | Selección automática de registros, campos y paginación (`detectar_estructura`) |
| Apoyo | `smart_scraper/intervencion.py` | Pausa ante CAPTCHA con intervención humana (`esperar_intervencion_humana`) y canal hilo↔GUI |

`smart_scraper/app.py` coordina los módulos (`run_job(..., progress=cb)` y `diagnose_config(config, progress=)` informan el avance) y `smart_scraper/gui.py` implementa la interfaz Tkinter con el panel de progreso.

## Seguridad, límites y uso responsable

- Solo inspecciona la URL ingresada; no rastrea dominios ni ejecuta pruebas masivas. La configuración limita la respuesta a 2 MB, a 1.000 registros, 10 páginas y cinco scrolls, con pausa mínima de un segundo.
- Respuestas 401/403/429 y formularios de autenticación detienen la ejecución. No resuelve CAPTCHA, evade autenticación, rota proxies ni intenta sortear controles.
- CAPTCHA: con **Requests/API** (o sin interfaz) la ejecución se detiene. Con **Selenium/Playwright** desde la GUI, la extracción se **pausa**: el navegador sigue abierto (si estaba en headless se relanza visible copiando las cookies), aparece un aviso con **Continuar / Omitir esta página / Cancelar extracción** y una persona resuelve el CAPTCHA a mano. *Continuar* revisa la página y vuelve a avisar si el CAPTCHA sigue; *Omitir* (o agotar la espera, 300 s por defecto, configurable en «Espera CAPTCHA») registra la URL en `skipped_urls`; *Cancelar* guarda lo extraído con estado `cancelled`. Cada evento queda en `smart_scraper.log` y en `captcha_events` del informe. La detección está centralizada en `inspector.detectar_captcha`.
- Prueba manual: `python scripts/sitio_captcha_local.py` y en la GUI método `selenium`, URL `http://127.0.0.1:8765/`, 3 páginas; los selectores (`article.item`, `titulo=h2`, `a.next`) se detectan solos.
- Las credenciales se ingresan en memoria mediante encabezados autorizados y no se escriben en el perfil. En sitios con login, usa únicamente un mecanismo y una cuenta autorizados.
- Antes de ejecutar, verifica términos de uso, `robots.txt`, privacidad, derechos sobre los datos, permisos del endpoint y límites del servicio. Una respuesta pública no equivale a autorización.
- El diagnóstico es heurístico: detecta pistas de APIs embebidas en HTML, pero no captura exhaustivamente el tráfico XHR/Fetch del navegador ni deduce por sí solo si un uso es legal.

## Pruebas

```powershell
python -m pytest -q
```

La suite tiene **65 pruebas** (14 de integración con un servidor HTTP local de sitios simulados, 18 del panel de progreso, el clasificador de escenarios y la detección de cambios, 24 de la pausa por CAPTCHA con intervención humana y 9 de la selección automática); no envían solicitudes a páginas públicas. El informe en [docs/INFORME_TECNICO.md](docs/INFORME_TECNICO.md) distingue esa evidencia de la evaluación legal y de la evidencia multisitio real.

## Evidencia multisitio

`python scripts/evidencia_extraccion.py` ejecuta **10 escenarios declarativos con un único motor** (`run_job`) sobre **5 sitios** y **9 mecanismos** (HTML estático, JavaScript, API, paginación, scroll infinito, bajo demanda, tablas, autenticación y CAPTCHA): 7 extracciones completadas (**186 registros**) y 3 incidencias detectadas sin evadirlas (login, ruta no permitida por `robots.txt`, CAPTCHA). Requiere Chrome y hace unas 30 peticiones públicas con pausa de 2 s.

- Matriz de escenarios: [docs/evidencias/MATRIZ_ESCENARIOS.md](docs/evidencias/MATRIZ_ESCENARIOS.md) (datos crudos: `docs/evidencias/extraccion_2026-11-20.json`).
- Dataset consolidado (SQLite, CSV y Excel): [datasets/multisitio/](datasets/multisitio/README.md).
- Video: `video/demo_avance.mp4` (GUI con panel de progreso en distintos escenarios); `video/demo_en_vivo.mp4` es la versión anterior.

## Dataset de ejemplo

El dataset procesado real (100 libros de books.toscrape.com en SQLite, CSV y Excel, con linaje) está en [datasets/](datasets/README.md); se regenera con `python scripts/build_dataset.py`.

[examples/sample_dataset.csv](examples/sample_dataset.csv) y [examples/sample_lineage.csv](examples/sample_lineage.csv) contienen datos sintéticos ilustrativos, no datos adquiridos de un sitio público.
