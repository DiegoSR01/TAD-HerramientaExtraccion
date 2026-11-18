# Dataset procesado: books.toscrape.com

## Fuente y método
- **Fuente:** https://books.toscrape.com/ (sandbox público creado para practicar scraping).
- **Fecha de extracción:** 2026-11-09.
- **Herramienta:** `smart_scraper` (`ScrapeConfig` + `run_job` de `smart_scraper/app.py`); no hay scraper aparte.
- **Configuración:** elementos `article.product_pod`; paginación `li.next a`; 5 páginas máx.; pausa 1,5 s; timeout 20 s.
- **Métodos:** `requests` (origen del dataset final) y `selenium` headless (corrida de demostración; Chrome funcionó y devolvió los mismos 100 registros crudos).
- **Filas finales:** 100 libros (5 páginas x 20), sin duplicados.

## Archivos
| Archivo | Contenido |
|---|---|
| `books_toscrape.sqlite` | Tabla `books` (tipada, con restricciones) y tabla `lineage` (linaje de la herramienta) |
| `books_toscrape.csv` | Tabla `books` (UTF-8 con BOM) |
| `books_toscrape.xlsx` | Hoja `books` y hoja `lineage` |
| `run_output/requests/`, `run_output/selenium/` | Registros crudos (xlsx), `report-*.json`, perfil, historial de cada corrida; el log `smart_scraper.log` (con ambas ejecuciones) quedó en `run_output/requests/` |

## Diccionario de datos (`books`)
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | entero | Identificador secuencial (clave primaria) |
| `titulo` | texto | Título completo del libro (atributo `title` del enlace) |
| `precio_gbp` | decimal | Precio en libras esterlinas, sin símbolo |
| `en_stock` | booleano (0/1 en SQLite) | `True` si la disponibilidad indica "In stock" |
| `rating` | entero 1-5 | Valoración, derivada de la clase `star-rating` (One..Five) |
| `url` | texto | URL absoluta de la ficha del libro (única) |
| `fecha_extraccion` | texto (ISO) | 2026-11-09 |
| `metodo` | texto | Método de adquisición del dataset (`requests`) |
| `fuente` | texto | URL raíz de origen |

## Pasos de limpieza
1. La herramienta normaliza espacios y deduplica registros idénticos (`transform_records`).
2. `precio`: se eliminan `£` y caracteres no numéricos (p. ej. `Â`) y se convierte a `float`.
3. `rating`: la clase CSS (`['star-rating', 'Three']`) se mapea a entero 1-5.
4. `disponibilidad`: texto a booleano `en_stock`.
5. `url`: los `href` relativos se convierten en absolutos (la base cambia entre la página 1 y las siguientes).
6. Se descartan filas sin título/precio/url y se deduplica por `url`; se añaden `id`, fecha, método y fuente.

## Estadísticas rápidas
- Precio medio: 34,56 GBP (mediana 34,78; mín. 10,16; máx. 58,11).
- Rating medio: 2,93.
- Distribución de rating: 1 estrella = 22, 2 = 19, 3 = 22, 4 = 18, 5 = 19.
- En stock: 100 de 100.

## Cómo regenerarlo
```bash
pip install -r requirements.txt
python scripts/build_dataset.py              # requests + selenium (requiere Chrome)
python scripts/build_dataset.py --no-selenium
```
Hace como máximo 5 peticiones de listado por método a books.toscrape.com y sobrescribe los archivos finales.
Nota: `.gitignore` excluye `*.log` y `*.sqlite3`, por lo que el log y el historial de `run_output/` no se versionan (el `.sqlite` final sí).
