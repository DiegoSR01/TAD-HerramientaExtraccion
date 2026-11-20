# Informe técnico y evidencias de prueba

## Alcance y resultado

Scraper configurable de ejecución local: diagnóstico heurístico, clasificación del escenario con recomendación de estrategia, cuatro vías de adquisición, selección CSS/JSON, transformación y trazabilidad, persistencia/exportación, detección de cambios entre ejecuciones y una interfaz gráfica con panel de progreso. El sistema se detiene ante CAPTCHA/challenge, autenticación no satisfecha, HTTP 403/429 y rutas que `robots.txt` no permite; no incorpora mecanismos de evasión.

Resumen de la evidencia al 20 de noviembre de 2026:

- **32 pruebas automatizadas** aprobadas (`python -m pytest -q`): 14 de integración con sitios simulados y 18 del panel de progreso, el clasificador de escenarios y la detección de cambios.
- **Evidencia multisitio real:** 10 escenarios declarativos ejecutados con un único motor sobre **5 sitios** y **9 mecanismos distintos**: 7 extracciones completadas (**186 registros**) y 3 incidencias o restricciones identificadas con informe (login detectado, `robots.txt` de Google que no permite la ruta, CAPTCHA de nopecha.com).
- Dataset consolidado en SQLite, CSV y Excel (`datasets/multisitio/`), además del dataset de 100 libros (`datasets/`).

## Escenarios cubiertos por pruebas automatizadas

`tests/test_pipeline.py` levanta un servidor local efímero y reproduce estos escenarios:

| Sitio simulado | Escenario | Evidencia/capacidad |
|---|---|---|
| `/static` | HTML estático | Detección del título, selector CSS y extracción de registros |
| `/dynamic` | JavaScript y carga | Pistas `fetch`/API e `IntersectionObserver` detectadas |
| `/loadmore` | Carga bajo demanda | Botón de carga y evento detectados |
| `/api/products` | API REST/JSON | Método API con autorización explícita y ruta `items` |
| `/graphql` | Respuesta JSON tipo GraphQL | Fixture preparado para respuestas JSON de API |
| `/pagination` | Paginación | Seguimiento CSS de `next`, dos páginas y pausa mínima |
| `/table` | Tabla | Selección de columnas y filas |
| `/auth` | Autenticación | HTTP 401 y formulario de contraseña detectados; se detiene |
| `/authorized` | Acceso autenticado permitido | Encabezado Bearer local válido; sin automatizar el login |
| `/captcha` | CAPTCHA | Bloqueo reportado; no se intenta resolver |

Los adaptadores Requests/BeautifulSoup y API se prueban contra el servidor local; Selenium y Playwright se prueban con adaptadores de navegador simulados para no requerir instalar navegadores ni abrir tráfico adicional. Por eso estas pruebas **no sustituyen** la ejecución real con navegador, que se documenta aparte en la sección «Evidencia multisitio» (Selenium real sobre sitios de práctica). El fixture de paginación valida el recorrido y los límites de scroll se verifican en el adaptador de navegador.

Además, `tests/test_progreso_y_cambios.py` (con `tests/conftest.py`) cubre:

- el orden y los estados de los 9 pasos del progreso (`run_job(..., progress=cb)` y `diagnose_config(config, progress=)`), incluida la detención con estado `blocked`;
- el clasificador `classify_scenario` para HTML estático, paginación, tablas, JavaScript, scroll infinito, carga bajo demanda, API JSON, autenticación y CAPTCHA;
- la detección de cambios ampliada (selectores, columnas nuevas, estructura JSON, variación de registros) y la migración de una base SQLite antigua.

Resultado: **32 pruebas aprobadas** (14 + 18).

## Cuatro métodos y criterios

1. Requests + BeautifulSoup: contenido HTML recibido en una solicitud acotada.
2. Selenium: renderizado DOM con Chrome; scroll opcional y acotado.
3. Playwright: renderizado DOM; dependencia opcional.
4. API autorizada: JSON explícito con confirmación de autorización.

Las rutas CSS de campos se aplican al HTML renderizado o descargado. Las rutas JSON usan segmentos con punto. La ruta de paginación debe ser CSS y sus enlaces se limitan al mismo host.

## Interfaz con panel de progreso

La GUI (`smart_scraper/gui.py`) muestra el flujo esperado del reto como un **stepper de 9 pasos** que se actualiza en vivo mientras la tarea corre en un hilo de trabajo:

1. Ingreso de URL y validación
2. Diagnóstico automatizado
3. Presentación de resultados
4. Selección de datos
5. Configuración de extracción
6. Ejecución del motor
7. Limpieza y validación
8. Almacenamiento
9. Reporte final

Cada paso pasa por los estados pendiente, en ejecución, completado, error o bloqueado. Junto al stepper hay una barra de progreso con contador `n / 9`, el tiempo transcurrido, un **cuadro «Escenario detectado / Estrategia»** (se pinta en naranja como **INCIDENCIA** cuando el acceso se detiene) y un registro con marcas de tiempo. La orquestación notifica el avance mediante un callback opcional: `run_job(config, ..., progress=cb)` y `diagnose_config(config, progress=cb)`; sin callback el comportamiento es el de antes, de modo que las pruebas y el uso programático no dependen de la interfaz.

## Clasificador de escenarios y selección de estrategia

El módulo `smart_scraper/estrategia.py` convierte el `InspectionReport` del inspector en un `Scenario` (etiqueta, estrategia, motivo, señales y bandera `blocked`) mediante `classify_scenario`. La prioridad de evaluación y la estrategia recomendada son:

| Escenario detectado | Estrategia recomendada |
|---|---|
| CAPTCHA o bloqueo (HTTP 403/429) | `detener` (incidencia; no se resuelve ni se evade) |
| Requiere autenticación | `detener`, salvo permisos legítimos |
| API JSON | `api` (con autorización confirmada) |
| Scroll infinito | `selenium` con desplazamientos acotados |
| Carga bajo demanda (botón) | `selenium` con clics acotados |
| JavaScript/SPA | `selenium` (o `playwright`) |
| Paginación | `requests` con selector de siguiente y límite de páginas |
| Tablas | `requests` |
| HTML estático | `requests` |

Las señales secundarias (paginación, tablas, endpoints API candidatos, etc.) se listan en `signals`, de modo que un sitio con JavaScript y paginación se informa como tal. La clasificación es heurística: apoya la decisión del operador, no sustituye la revisión legal.

## Detección de cambios entre ejecuciones

`compare_and_store_snapshot` (`smart_scraper/storage.py`) guarda por host el último snapshot y lo compara con la ejecución actual. Además de campos añadidos/faltantes, endpoints nuevos/eliminados y variación de registros, ahora registra:

- `selector_changes`: selectores CSS/rutas de campo (y `_item_selector`) que cambiaron, con valor anterior y posterior;
- `new_columns`: columnas que aparecen respecto a la ejecución previa;
- `json_structure_added` / `json_structure_removed`: rutas de claves del JSON que aparecieron o desaparecieron (`json_structure_signature` calcula rutas como `items[].id`);
- `record_count_previous`, `record_count_delta` y `record_count_percent`: volumen anterior, diferencia absoluta y porcentaje;
- `changes_detected`: bandera global; el log indica «línea base creada», «cambios detectados» o «sin cambios».

La tabla `run_snapshots` se **migra automáticamente** (`ALTER TABLE` para `selectors` y `json_structure`) si proviene de una versión anterior, sin perder datos. No se comparan los valores de cada campo entre ejecuciones ni se inspecciona el tráfico de red.

## Evidencia multisitio: matriz de escenarios

`scripts/evidencia_extraccion.py` ejecuta **10 escenarios declarativos** (cada uno es solo una configuración `ScrapeConfig`; no hay un scraper por sitio) a través del mismo motor `smart_scraper.app.run_job`. Controles de cortesía: consulta previa de `robots.txt` (si no permite la ruta, el escenario se omite y se registra), User-Agent identificado, pausa de 2 s, máximo 3 páginas por escenario y una sola corrida (~30 peticiones públicas). Se usan sandboxes de práctica (`quotes.toscrape.com`, `books.toscrape.com`, `scrapethissite.com`) y demos públicas de CAPTCHA.

- Sitios distintos: **5** (books.toscrape.com, google.com, nopecha.com, quotes.toscrape.com, scrapethissite.com).
- Escenarios: **10**; mecanismos de adquisición/escenario distintos: **9**; métodos del motor usados: **3** (`requests`, `selenium`, `api`).
- Extracciones completadas: **7** (**186 registros**); incidencias o restricciones con informe: **3**.

| Escenario | Sitio | Estrategia elegida | Resultado | Registros | Viabilidad legal/técnica |
|---|---|---|---|---|---|
| HTML estático | quotes.toscrape.com | requests + selectores CSS [requests] | Completado | 10 | Viable |
| Sitio con JavaScript | quotes.toscrape.com/js/ | selenium headless (DOM renderizado) [selenium] | Completado | 10 | Viable con navegador |
| Información vía API | quotes.toscrape.com/api/quotes | api (GET JSON, ruta `quotes`, autorización confirmada) [api] | Completado | 10 | Viable (API pública autorizada) |
| Paginación | books.toscrape.com | requests + selector de paginación `li.next a` (3 páginas) [requests] | Completado | 60 | Viable |
| Scroll infinito | quotes.toscrape.com/scroll | selenium headless + 2 desplazamientos acotados [selenium] | Completado | 30 | Viable con navegador |
| Tablas HTML | scrapethissite.com/pages/forms/ | requests + filas `tr.team` y paginación `a[aria-label=Next]` (2 páginas) [requests] | Completado | 50 | Viable |
| Contenido bajo demanda (AJAX) | scrapethissite.com/pages/ajax-javascript/ | selenium + clic acotado en `a.year-link` (carga bajo demanda) [selenium] | Completado | 16 | Viable con navegador |
| Autenticación autorizada | quotes.toscrape.com/login | selenium: detectar login y detenerse (no se automatiza el acceso) [selenium] | Detenido (incidencia) | 0 | Requiere autorización |
| CAPTCHA → incidencia | google.com/recaptcha/api2/demo | requests: detectar CAPTCHA, detener y reportar (no se resuelve) [requests] | Omitido (robots.txt) | 0 | No viable – robots.txt |
| CAPTCHA → incidencia (diagnóstico y reporte) | nopecha.com/demo/recaptcha | requests: detectar CAPTCHA, detener y reportar (no se resuelve) [requests] | Detenido (incidencia) | 0 | No viable – CAPTCHA |

La matriz completa (mecanismo detectado, esquema de protección y observaciones) está en `docs/evidencias/MATRIZ_ESCENARIOS.md`; el resultado crudo, en `docs/evidencias/extraccion_2026-11-20.json`.

### Correspondencia con los 9 criterios de aceptación del reto

| Criterio de aceptación | Escenario que lo evidencia | Resultado |
|---|---|---|
| HTML estático | 01 `quotes.toscrape.com` (requests) | Completado, 10 registros |
| Sitio con JavaScript | 02 `quotes.toscrape.com/js/` (selenium) | Completado, 10 registros |
| Información vía API | 03 `quotes.toscrape.com/api/quotes` (api) | Completado, 10 registros |
| Paginación | 04 `books.toscrape.com` (requests, 3 páginas) | Completado, 60 registros |
| Scroll infinito | 05 `quotes.toscrape.com/scroll` (selenium, 2 scrolls) | Completado, 30 registros |
| Contenido bajo demanda | 07 `scrapethissite.com/pages/ajax-javascript/` (selenium, clic acotado) | Completado, 16 registros |
| Tablas | 06 `scrapethissite.com/pages/forms/` (requests, 2 páginas) | Completado, 50 registros |
| Autenticación | 08 `quotes.toscrape.com/login` | Incidencia: se detecta el login y se detiene; no se envían credenciales |
| CAPTCHA → incidencia | 09 `google.com/recaptcha/api2/demo` y 10 `nopecha.com/demo/recaptcha` | 09 omitido por `robots.txt`; 10 detenido con informe: CAPTCHA detectado, no se resuelve |

### Observaciones y límites de esta evidencia

- Los sitios son sandboxes creados para practicar scraping; el resultado demuestra el motor, no la viabilidad legal de portales reales (para eso, véase la clasificación de esquemas más abajo).
- La autenticación se evidencia como detección y detención, no como acceso: la herramienta no automatiza login ni guarda cookies.
- La demo de reCAPTCHA de Google no se solicita porque su `robots.txt` no permite la ruta; el CAPTCHA se evidencia con la demo de nopecha.com (`robots.txt` permite la ruta; una sola solicitud de diagnóstico, sin intentar resolverlo).
- Las señales «JS/dinámico» del diagnóstico son heurísticas y pueden dar falsos positivos (p. ej. por cargar jQuery); por eso la matriz separa el mecanismo detectado de la estrategia efectivamente usada.

## Prueba de URLs proporcionadas

El 9 de noviembre de 2026 se realizó una solicitud GET de inspección por URL, con una pausa de dos segundos entre destinos, sin seguir paginación ni abrir navegadores. Se limitaron las respuestas al tope del inspector. La muestra son título/encabezados del HTML recibido, no un dataset del portal.

| URL | Resultado técnico observado | Evaluación |
|---|---|---|
| `https://www.inegi.org.mx/datosabiertos/` | HTTP 200; título “Datos abiertos”; 3.562 bytes; el HTML no expuso una lista de registros genérica | Respuesta inspeccionable; hace falta perfil/selectores y revisar las condiciones del portal |
| `https://www.datos.gob.mx/` | HTTP 403; título “Access Denied”; 374 bytes | Bloqueado; no se reintentó ni se intentó evadir la restricción |
| `https://data.worldbank.org/` | HTTP 200; título “World Bank Open Data \| Data”; 212.221 bytes; encabezados visibles en la muestra | HTML inspeccionable, con señales heurísticas de JavaScript; no se inspeccionó tráfico de red |
| `https://data.gov/` | HTTP 200; título “Data.gov Home - Data.gov”; 121.849 bytes; encabezados visibles en la muestra | HTML inspeccionable; requiere perfil/selectores y revisar las condiciones del portal |
| `https://www.dof.gob.mx/` | No se obtuvo respuesta HTTP: error TLS de certificado por discrepancia de hostname | No se desactivó la validación TLS ni se probó otra variante del dominio |

Son observaciones técnicas puntuales que pueden cambiar por disponibilidad, ubicación o políticas del sitio; no equivalen a certificación de scraping. Un 403 indica restricción de acceso, no demuestra por sí solo que el portal requiera autenticación. La aplicación ahora reporta esa diferencia y se mantiene detenida ante HTTP 403.

La viabilidad legal de los destinos se evalúa en la sección siguiente, combinando robots.txt, términos/licencia publicados y alternativas oficiales; no se asigna una conclusión basándose solo en el acceso HTTP. Es una evaluación técnica preliminar y **no constituye asesoría legal**: antes de una extracción real, el responsable del proyecto debe confirmar términos vigentes, finalidad y tratamiento de datos.

**Regla de clasificación:** solo continuar si el titular permite el acceso para el propósito previsto, el tratamiento de los datos es lícito, se respetan términos, robots y límites, y la autenticación usada pertenece a una cuenta autorizada. En caso de CAPTCHA, bloqueo o duda, detener la prueba y solicitar permiso al responsable.

## Clasificación de esquemas de protección y viabilidad legal

### Metodología

El 9 de noviembre de 2026 se ejecutó `scripts/evidencia_sitios.py` sobre siete sitios (los cinco del apartado anterior y los sandboxes `books.toscrape.com` y `quotes.toscrape.com`). Por sitio: una petición GET a la página y una a `/robots.txt`, pausa de 2 s, timeout de 15 s, User-Agent `TAD-SmartScraper/0.1 (proyecto academico)`, TLS verificado y sin reintentos. Se registraron status, cabeceras relevantes (server, cf-ray, x-cache, akamai, nombres de cookies), presencia de CSP, tamaño, título, señales de JS/SPA, marcadores de CAPTCHA/challenge y reglas de robots.txt; el análisis del HTML reutiliza `smart_scraper.inspector.diagnose`. Los términos/licencias se consultaron en las páginas oficiales (una lectura por página) o, cuando no fue posible, en fuentes secundarias, indicándolo.

### Criterios de clasificación

- **Esquema de protección:** Ninguna (200 sin cabeceras ni cookies de WAF/CDN con efecto de filtrado ni challenge); Renderizado JS (HTML con marcadores de SPA); WAF-CDN con 403 (respuesta de bloqueo servida por CDN/WAF); Error TLS; CAPTCHA; Rate-limit (429). Un CDN que sirve 200 (CloudFront, Cloudflare con `__cf_bm`) se registra como observación, no como bloqueo.
- **Viabilidad técnica:** si la página fue obtenible y utilizable sin evadir controles.
- **Viabilidad legal:** *Viable* (licencia/permiso explícito para el propósito, sin restricciones relevantes); *Viable con condiciones* (permitido con atribución, respeto de robots, uso no comercial, límites de volumen o verificación por conjunto de datos); *No viable sin autorización* (acceso denegado o no verificable; se requiere permiso del titular o canal oficial).

### Tabla de clasificación

| Sitio | Esquema de protección observado | robots.txt | Licencia/Términos | Alternativa oficial | Viabilidad técnica | Viabilidad legal | Justificación breve |
|---|---|---|---|---|---|---|---|
| inegi.org.mx/datosabiertos | Ninguna (IIS; cookie de balanceador F5 `BIGipServer…`, sin challenge) | HTTP 200; `Disallow` solo de rutas de catálogo (`/catalog/*/download/*`, `/catalog/*/variable/*`, etc.); sin Crawl-delay | Términos de libre uso del INEGI (uso, adaptación y explotación comercial con cita de la fuente y sin alterar metadatos) | Descargas/servicios de datos del propio INEGI; API no verificada en esta evidencia | Alta (HTTP 200, HTML ligero) | Viable con condiciones | Licencia abierta; condiciones: citar "Fuente: INEGI", no sugerir aval, respetar los Disallow y límites de ritmo |
| datos.gob.mx | WAF-CDN con 403 (Akamai; "Access Denied" también en robots.txt) | No obtenido (403) | Libre Uso MX (adaptación de CC BY 4.0) según fuente secundaria; texto oficial no verificado | API CKAN del portal (ruta citada por catálogo de terceros; no probada) | Nula para scraping HTML con este cliente | No viable sin autorización | El control de acceso deniega la petición y no hay política robots verificable; no se evade. Usar la API/descargas oficiales o solicitar acceso |
| data.worldbank.org | Renderizado JS (React/webpack) tras Cloudflare (cookie `__cf_bm`, 200) | HTTP 200; `Allow: /`; sin Crawl-delay | Datasets: CC BY 4.0 por defecto (confirmado); otros materiales del sitio: solo uso no comercial y límites de API | API oficial de indicadores del Banco Mundial (api.worldbank.org; no probada aquí) | Media (HTML inspeccionable; los datos viven en la API) | Viable con condiciones | Atribuir y declarar cambios; preferir API con volumen razonable; revisar términos por dataset; no usar materiales no-dataset de forma comercial |
| data.gov | Ninguna con CDN (CloudFront, 200; sin challenge) | HTTP 200; `Allow: /`; sitemap; sin Crawl-delay | Datos federales sin restricción de copyright doméstico; datos no federales con términos propios (ver "Access & Use" del dataset); atribución solicitada, no obligatoria | Catálogo catalog.data.gov (API CKAN no confirmada: las rutas `/api/3/...` probadas devolvieron 404) | Alta (HTML estático/mixto) | Viable con condiciones | Verificar la licencia dataset por dataset; preferir las descargas/API del catálogo |
| dof.gob.mx | Error TLS (certificado no válido para `www.dof.gob.mx`) | No obtenido (error TLS) | Aviso legal (sidof.segob.gob.mx): reproducción sin fin de lucro con cita; comercial requiere consentimiento de Segob; prohibido alterar el texto; no regula acceso automatizado | Servicios del DOF en línea/SIDOF (no evaluados) | Nula (no se desactivó la verificación TLS) | Viable con condiciones | Uso no lucrativo con cita e integridad del texto; robots y acceso real no verificados; el host `dof.gob.mx` sin `www` apareció con certificado válido en una consulta externa, pero no se probó con el script |
| books.toscrape.com | Ninguna | HTTP 404 (sin política declarada) | Sandbox de práctica (título "Sandbox"); texto de términos no consultado | No aplica | Alta (HTML estático, paginación) | Viable | Sitio creado para práctica de scraping |
| quotes.toscrape.com | Ninguna | HTTP 404 (sin política declarada) | Sandbox de práctica; texto de términos no consultado | No aplica | Alta (HTML estático, paginación) | Viable | Sitio creado para práctica de scraping |

### Conclusión

Con la evidencia recogida, los dos sandboxes son viables; INEGI, Banco Mundial, data.gov y el DOF son viables con condiciones (atribución, respeto de robots y límites de ritmo, verificación de licencia por conjunto de datos, uso no comercial en el caso del DOF y de materiales no-dataset del Banco Mundial); y datos.gob.mx no es viable por scraping sin autorización, por lo que debe accederse por su API o descargas oficiales. En todos los casos reales se recomienda usar la API/descarga oficial antes que extraer HTML. Esta clasificación es técnica y preliminar, **no es asesoría legal**, y los términos pueden cambiar.

### Evidencia

- `scripts/evidencia_sitios.py`: script reproducible.
- `docs/evidencias/sitios_2026-11-09.json`: resultados crudos por sitio.
- `docs/evidencias/robots/<host>.txt`: resumen de robots.txt por sitio.
- No verificado: texto oficial vigente de Libre Uso MX y de la API CKAN de datos.gob.mx; API CKAN de catalog.data.gov; términos de toscrape; robots y términos del host real del DOF; existencia/uso de las APIs de INEGI y Banco Mundial (solo se citan, no se probaron).

## Datos y entregables

- **Dataset de libros** (`datasets/`): 100 libros extraídos de `books.toscrape.com` (sandbox de práctica) el 2026-11-09 con la propia herramienta (`scripts/build_dataset.py`), 5 páginas, pausa de 1,5 s. Se hicieron dos corridas, una con Requests y otra con Selenium headless sobre Chrome, y ambas obtuvieron 100 registros. Tras la limpieza (precio a `float`, rating de 1 a 5, stock a booleano, URL absoluta, deduplicación) se publica en `books_toscrape.sqlite` (tablas `books` y `lineage`), `books_toscrape.csv` y `books_toscrape.xlsx`. El diccionario de datos y las estadísticas están en `datasets/README.md`.
- **Dataset consolidado multisitio** (`datasets/multisitio/`, generado el 2026-11-20): `dataset_multisitio.sqlite` (tabla `registros` en formato largo con 817 filas, `linaje`, `ejecuciones` con una fila por escenario y una tabla ancha tipada `esc_<escenario>` por cada extracción exitosa), `dataset_multisitio.xlsx` (hoja `resumen`, una hoja por escenario y hoja `linaje`) y `dataset_multisitio.csv`; `runs/<escenario>/` conserva el informe, los registros y el perfil crudos de cada ejecución. Se regenera con `python scripts/evidencia_extraccion.py` (requiere Chrome, ~2 min).
- `examples/sample_dataset.csv` y `examples/sample_lineage.csv`: dataset sintético de demostración.
- Cada fila de linaje registra ejecución, URL de origen, instante UTC, método, campo, valor, validación y transformaciones.
- `report-<id>.json`, `smart_scraper.log` y `profiles/<host>.json`: informe, log y perfil técnico sin encabezados de autenticación.
- SQLite conserva registros, linaje y último snapshot por host; CSV/Excel generan una hoja/archivo auxiliar para linaje.
- **Video de demostración:** `video/demo_avance.mp4` muestra la GUI con el panel de progreso recorriendo distintos escenarios; `video/demo_en_vivo.mp4` se conserva como versión previa.

## Cumplimiento de entregables

| Entregable | Evidencia | Estado |
|---|---|---|
| Código Selenium documentado | `smart_scraper/extractor.py` (`_acquire_selenium`: esperas explícitas, clics y scrolls acotados, detección de CAPTCHA/login), docstrings en español | Cumplido |
| Dataset SQLite / CSV / Excel | `datasets/books_toscrape.*` (100 libros) y `datasets/multisitio/dataset_multisitio.*` (186 registros, 7 escenarios) | Cumplido |
| Informe técnico | `docs/INFORME_TECNICO.md` y `docs/INFORME_TECNICO.docx` | Cumplido |
| Evidencia de clasificación de sitios y viabilidad legal | Sección «Clasificación de esquemas de protección y viabilidad legal», `docs/evidencias/sitios_2026-11-09.json` y matriz `docs/evidencias/MATRIZ_ESCENARIOS.md` | Cumplido (preliminar; no es asesoría legal) |
| Pruebas automatizadas | `tests/` (32 pruebas aprobadas) | Cumplido |
| Video de 3 a 5 minutos | `video/demo_avance.mp4` (nuevo) y `video/demo_en_vivo.mp4` (previo, 3:16) | Verificar la duración del video nuevo al cerrarlo |

## Limitaciones conocidas y siguientes pruebas autorizadas

- Las pistas de API y de comportamiento dinámico se obtienen del HTML y JavaScript visibles; no existe captura exhaustiva de tráfico de red del navegador.
- La detección de CAPTCHA, login, botón de carga e infinite scroll es heurística y puede producir falsos positivos/negativos.
- La autenticación de navegador requiere que el usuario gestione legítimamente la sesión; la aplicación no automatiza login ni guarda cookies.
- Para completar la evaluación real, el operador debe obtener autorización, registrar URLs y propósito, verificar robots/términos, fijar un horario y límites más conservadores y documentar resultados y datos personales minimizados.
