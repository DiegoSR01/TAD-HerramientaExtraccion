# Dataset multisitio (Reto final)

Evidencia de **diagnóstico y extracción** sobre 5 sitios y 10 escenarios con **un único motor**
(`smart_scraper.app.run_job` + `ScrapeConfig`). Cada escenario es una configuración declarativa en
`scripts/evidencia_extraccion.py`; no hay un scraper por sitio.

## Regenerar
```
python scripts/evidencia_extraccion.py
```
Requiere Chrome (Selenium Manager descarga el driver). Una sola corrida, pausa de 2 s, máx. 3 páginas por
escenario, ~30 peticiones públicas en total, consulta previa de `robots.txt` (si no permite la ruta, el
escenario se omite y se registra). Duración aprox. 2 min.

## Archivos
| Archivo | Contenido |
|---|---|
| `dataset_multisitio.sqlite` | `registros` (formato largo: escenario, registro_id, url_origen, metodo, execution_id, campo, valor), `linaje` (linaje de la herramienta por valor), `ejecuciones` (una fila por escenario con estado, método, diagnóstico y viabilidad) y una tabla ancha tipada `esc_<escenario>` por cada extracción exitosa |
| `dataset_multisitio.xlsx` | Hoja `resumen` (ejecuciones), una hoja por escenario exitoso y hoja `linaje` |
| `dataset_multisitio.csv` | Formato largo unificado (UTF-8 con BOM), mismas columnas que `registros` |
| `runs/<escenario>/` | Salida cruda de `run_job`: `report-<execution_id>.json`, `records-*.xlsx` (hojas `records` y `lineage`) y perfil. Los escenarios con incidencia (autenticación, CAPTCHA) solo tienen el informe. Se eliminan logs e historial local |

La evidencia consolidada está en `docs/evidencias/extraccion_<fecha>.json` y `docs/evidencias/MATRIZ_ESCENARIOS.md`.

## Limpieza aplicada
Espacios recortados/colapsados, filas vacías y duplicados eliminados, comillas tipográficas de las citas
retiradas, `rating` (clase CSS) convertido a 1-5, disponibilidad a booleano, y columnas numéricas
(precio, año, victorias, goles, nominaciones, premios) convertidas a número. Solo se toma la primera etiqueta
(`etiqueta`) de cada cita.

## Escenarios
| Id | Mecanismo | Método |
|---|---|---|
| 01_html_estatico | HTML estático | requests |
| 02_javascript | Renderizado por JavaScript | selenium |
| 03_api_json | API JSON pública | api |
| 04_paginacion | Paginación (3 páginas) | requests |
| 05_scroll_infinito | Scroll infinito | selenium |
| 06_tablas | Tabla HTML paginada | requests |
| 07_bajo_demanda | Contenido AJAX tras clic | selenium |
| 08_autenticacion | Login: se detecta y se detiene (incidencia) | selenium |
| 09_captcha | Demo de Google: `robots.txt` no permite la ruta, se omite | requests |
| 10_captcha_incidencia | CAPTCHA detectado: se detiene con informe (incidencia) | requests |

Los sitios son sandboxes públicos de práctica (`*.toscrape.com`, `scrapethissite.com`) y demos públicas de CAPTCHA;
las señales «JS/dinámico» del diagnóstico son heurísticas y pueden dar falsos positivos (p. ej. por cargar jQuery).
