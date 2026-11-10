# Informe técnico y evidencias de prueba

## Alcance y resultado

Entrega inicial de un scraper configurable de ejecución local: diagnóstico heurístico, cuatro vías de adquisición, selección CSS/JSON, transformación y trazabilidad, persistencia/exportación y GUI. El sistema se detiene ante CAPTCHA/challenge, autenticación no satisfecha y HTTP 429; no incorpora mecanismos de evasión.

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

Los adaptadores Requests/BeautifulSoup y API se prueban contra el servidor local; Selenium y Playwright se prueban con adaptadores de navegador simulados para no requerir instalar navegadores ni abrir tráfico adicional. Por lo tanto, los tests **no certifican compatibilidad con cinco sitios públicos reales ni sustituyen pruebas autorizadas de navegador**. El fixture de paginación valida el recorrido; los límites de scroll se configuran y verifican en el adaptador de navegador, no se usa un sitio remoto para generar scroll infinito.

## Cuatro métodos y criterios

1. Requests + BeautifulSoup: contenido HTML recibido en una solicitud acotada.
2. Selenium: renderizado DOM con Chrome; scroll opcional y acotado.
3. Playwright: renderizado DOM; dependencia opcional.
4. API autorizada: JSON explícito con confirmación de autorización.

Las rutas CSS de campos se aplican al HTML renderizado o descargado. Las rutas JSON usan segmentos con punto. La ruta de paginación debe ser CSS y sus enlaces se limitan al mismo host.

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

- **Dataset procesado real** (`datasets/`): 100 libros extraídos de `books.toscrape.com` (sandbox de práctica) el 2026-11-09 con la propia herramienta (`scripts/build_dataset.py`), 5 páginas, pausa de 1,5 s. Se hicieron dos corridas, una con Requests y otra con Selenium headless sobre Chrome, y ambas obtuvieron 100 registros. Tras la limpieza (precio a `float`, rating de 1 a 5, stock a booleano, URL absoluta, deduplicación) se publica en `books_toscrape.sqlite` (tablas `books` y `lineage`), `books_toscrape.csv` y `books_toscrape.xlsx`. El diccionario de datos y las estadísticas están en `datasets/README.md`.
- `examples/sample_dataset.csv` y `examples/sample_lineage.csv`: dataset sintético de demostración.
- Cada fila de linaje registra ejecución, URL de origen, instante UTC, método, campo, valor, validación y transformaciones.
- `report-<id>.json`, `smart_scraper.log` y `profiles/<host>.json`: informe, log y perfil técnico sin encabezados de autenticación.
- SQLite conserva registros, linaje y último snapshot por host; CSV/Excel generan una hoja/archivo auxiliar para linaje.

## Limitaciones conocidas y siguientes pruebas autorizadas

- Las pistas de API y de comportamiento dinámico se obtienen del HTML y JavaScript visibles; no existe captura exhaustiva de tráfico de red del navegador.
- La detección de CAPTCHA, login, botón de carga e infinite scroll es heurística y puede producir falsos positivos/negativos.
- La autenticación de navegador requiere que el usuario gestione legítimamente la sesión; la aplicación no automatiza login ni guarda cookies.
- Para completar la evaluación real, el operador debe obtener autorización, registrar URLs y propósito, verificar robots/términos, fijar un horario y límites más conservadores y documentar resultados y datos personales minimizados.
