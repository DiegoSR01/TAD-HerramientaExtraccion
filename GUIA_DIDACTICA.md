# Guia didactica: Web Scraper Inteligente

Esta guia explica el proyecto para estudiar su funcionamiento y presentarlo en una demostracion. El README contiene el inicio rapido y la [guia de desarrollo y operacion](GUIA_DESARROLLO_Y_OPERACION.md) describe la instalacion completa.

## 1. Idea general

**Web Scraper Inteligente** es una aplicacion local hecha en Python que recibe una URL y una configuracion, inspecciona la respuesta, extrae informacion estructurada y guarda los resultados junto con un registro de la ejecucion.

Puede trabajar con:

- HTML estatico mediante Requests y BeautifulSoup.
- HTML renderizado mediante Selenium o Playwright.
- API JSON o una respuesta JSON con forma tipo GraphQL.
- Tablas HTML y campos definidos con selectores CSS.
- CSV, Excel, JSON, SQLite, PostgreSQL y MongoDB.

La herramienta no es un rastreador masivo: consulta una URL, aplica limites y se detiene ante restricciones.

### Resultado que entrega

Una ejecucion puede generar:

- Datos extraidos.
- Linaje de cada campo.
- Un informe JSON con advertencias y cambios.
- Un log de ejecucion.
- Un perfil tecnico por host.
- Comparaciones con ejecuciones anteriores.

Ejemplo de datos sintéticos suministrados: [examples/sample_dataset.csv](examples/sample_dataset.csv) y [examples/sample_lineage.csv](examples/sample_lineage.csv).

## 2. Conceptos necesarios

| Concepto | Significado en el proyecto |
|---|---|
| Inspeccion | Solicita y analiza la pagina para reconocer HTML, JavaScript, paginacion, API, autenticacion o CAPTCHA. |
| Selector CSS | Regla que identifica elementos HTML, por ejemplo `.price` o `article.product`. |
| Registro | Una unidad de datos extraida, como un producto o una fila. |
| Campo | Una propiedad dentro de cada registro, como `nombre` o `precio`. |
| Linaje | Informacion que indica de donde provino cada campo y que transformaciones recibio. |
| Perfil | Configuracion guardada por host para reutilizar selectores y opciones. |
| Snapshot | Estado de una ejecucion usado para comparar cambios en ejecuciones posteriores. |
| Restriccion | Situacion que impide continuar de forma segura, como HTTP 401, 403, 429 o CAPTCHA. |

### Sintaxis de campos

Cada linea tiene el formato `nombre=selector`:

```text
nombre*=h2.product-title
enlace=a.product-link::href
precio=.price
imagen=img::src
```

- `nombre*` indica que el campo es requerido.
- `::href`, `::src` u otro atributo lee el atributo indicado.
- Sin `::`, el valor se toma como texto visible.

Para una API se usa una ruta JSON separada por puntos:

```text
id=id
nombre=product.name
precio=product.price
```

## 3. Recorrido tecnico

El proyecto separa el proceso en siete responsabilidades.

```text
Usuario / GUI
      |
      v
Configuracion
      |
      v
Diagnostico e inspeccion
      |
      v
Extraccion (Requests, Selenium, Playwright o API)
      |
      v
Seleccion de HTML/JSON/tablas
      |
      v
Limpieza, validacion y linaje
      |
      v
Exportacion y monitoreo
```

### Modulos principales

| Modulo | Archivo | Funcion |
|---|---|---|
| Configuracion | [smart_scraper/config.py](smart_scraper/config.py) | Valida URL, limites, campos y credenciales; administra perfiles. |
| Inspeccion | [smart_scraper/inspector.py](smart_scraper/inspector.py) | Analiza la respuesta HTML y obtiene señales de comportamiento o restricciones. |
| Extraccion | [smart_scraper/extractor.py](smart_scraper/extractor.py) | Descarga o renderiza el contenido y obtiene registros. |
| Seleccion | [smart_scraper/selection.py](smart_scraper/selection.py) | Convierte HTML y JSON en diccionarios de datos. |
| Transformacion | [smart_scraper/transform.py](smart_scraper/transform.py) | Normaliza espacios, elimina duplicados y valida campos. |
| Almacenamiento | [smart_scraper/storage.py](smart_scraper/storage.py) | Guarda archivos, bases locales y conexiones opcionales. |
| Monitoreo | [smart_scraper/monitoring.py](smart_scraper/monitoring.py) | Produce el informe y el log de ejecucion. |
| Coordinacion | [smart_scraper/app.py](smart_scraper/app.py) | Une el flujo completo de extremo a extremo. |
| Interfaz | [smart_scraper/gui.py](smart_scraper/gui.py) | Implementa la ventana Tkinter y la ejecucion con un hilo secundario. |

## 4. Por que cada etapa existe

### Inspeccion

Antes de extraer, el inspector examina el estado HTTP, el titulo y el contenido visible. Busca pistas de JavaScript, API, paginacion, carga bajo demanda, formularios de autenticacion y CAPTCHA.

Estas señales son heurísticas: indican una posibilidad, no demuestran que exista una API o que un sitio permita el scraping.

### Extraccion

Elige un metodo segun el tipo de pagina:

| Metodo | Situacion adecuada | Tecnologias |
|---|---|---|
| `requests` | El HTML contiene los datos en la respuesta | Requests y BeautifulSoup |
| `selenium` | JavaScript o interaccion requieren Chrome | Selenium |
| `playwright` | Se requiere un navegador y Playwright esta instalado | Playwright |
| `api` | Existe un endpoint JSON autorizado | Requests y rutas JSON |

### Seleccion y limpieza

Los selectores producen una fila por elemento o una fila por objeto JSON. La etapa posterior elimina duplicados y normaliza texto. Los campos requeridos se marcan en el linaje si no tienen un valor valido.

### Persistencia y trazabilidad

El almacenamiento puede guardar los datos limpios y el linaje por separado o dentro de cada registro. Cada ejecucion recibe un identificador, una fecha UTC y una URL de origen.

Las ejecuciones posteriores comparan nombres de campos, endpoints detectados y cantidad de registros. Esta comparación no inspecta el trafico real del navegador ni el valor de todos los campos.

## 5. Preparacion en Windows

Abre PowerShell en la carpeta del proyecto.

### Instalacion recomendada

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all]"
python -m playwright install chromium
```

Si PowerShell no permite activar el entorno virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
.\.venv\Scripts\python.exe -m smart_scraper.gui
```

Instalacion mas ligera:

```powershell
python -m pip install -e .
```

Solo Excel:

```powershell
python -m pip install -e ".[excel]"
```

Solo pruebas:

```powershell
python -m pip install -e ".[test]"
```

## 6. Comandos principales

| Objetivo | Comando |
|---|---|
| Abrir la GUI como modulo | `python -m smart_scraper.gui` |
| Abrir la GUI con el paquete | `python -m smart_scraper` |
| Abrir la GUI mediante el entry point | `smart-scraper` |
| Ejecutar todas las pruebas | `python -m pytest -q` |
| Mostrar pruebas con nombres | `python -m pytest -v` |
| Ejecutar una prueba concreta | `python -m pytest -v tests/test_pipeline.py::test_inspection_recognizes_static_and_dynamic_sites` |
| Comprobar sintaxis | `python -m compileall -q smart_scraper tests` |

## 7. Uso por la interfaz

1. Iniciar la interfaz.
2. Escribir una URL `http://` o `https://`.
3. Seleccionar el metodo.
4. Pulsar **1. Inspeccionar**.
5. Revisar el diagnostico mostrado.
6. Configurar el selector de registros y los campos.
7. Ajustar limites y formato.
8. Pulsar **2. Extraer y guardar**.
9. Abrir los archivos o consultar el informe generado.
10. Cambiar la URL o cargar un perfil existente para repetir una configuracion.

### Ejemplo HTML

Configuracion:

```text
Selector de registros: article.product
```

Campos:

```text
nombre*=h2.product-title
enlace=a.product-link::href
precio=.price
```

Resultado conceptual:

| nombre | enlace | precio |
|---|---|---|
| Producto Alpha | `/alpha` | `199.00` |
| Producto Beta | `/beta` | `249.00` |

### Ejemplo API JSON

Supongamos una respuesta cuyo objeto principal contiene `items`:

```json
{
  "items": [
    {"id": 1, "product": {"name": "Alpha"}},
    {"id": 2, "product": {"name": "Beta"}}
  ]
}
```

Configuracion:

```text
Metodo: api
Ruta de lista: items
Campos:
id=id
nombre=product.name
```

Antes de usarla, la casilla **Confirmo autorizacion del endpoint API** debe activarse porque el endpoint esta autorizado para esa tarea.

## 8. Limites configurados

| Recurso | Limite |
|---|---|
| Tamano de respuesta HTML | 2 MB |
| Registros | 1.000 |
| Paginas | 10 |
| Scrolls | 5 |
| Clics de cargar mas | 5 |
| Timeout HTTP | 1 a 30 segundos |
| Pausa | Como minimo 1 segundo |

Los valores de demostracion pueden ser menores. Para validar selectores conviene extraer unas pocas filas y una pagina.

## 9. Archivos que aparecen despues de ejecutar

| Archivo o carpeta | Contenido |
|---|---|
| `records-<id>.csv` | Datos extraidos. |
| `lineage-<id>.csv` | Linaje por campo y registro. |
| `records-<id>.xlsx` | Hojas `records` y `lineage`. |
| `records-<id>.json` | Datos con linaje incluido. |
| `scraper.sqlite3` | Base SQLite con registros, linaje y snapshots. |
| `.scraper_history.sqlite3` | Historial para formatos distintos de SQLite. |
| `profiles/<host>.json` | Perfil tecnico reutilizable sin secretos. |
| `report-<id>.json` | Estado, diagnostico, conteos, cambios y errores. |
| `smart_scraper.log` | Registro de eventos del proyecto. |

La carpeta predeterminada es `output`, dentro del directorio desde el que se inicia la GUI. Puede cambiarse con **Carpeta...**.

## 10. Recorrido de demostracion recomendado

### Parte A: comprobar el proyecto sin consultar Internet

1. Abrir PowerShell en la carpeta del proyecto.
2. Activar el entorno virtual.
3. Ejecutar:

   ```powershell
   python -m pytest -v
   ```

4. Explicar que la suite levanta un servidor HTTP local, no una pagina publica.
5. Señalar los escenarios cubiertos:
   - HTML estatico.
   - JavaScript y pistas de API.
   - Tabla.
   - Paginacion.
   - API JSON y respuesta tipo GraphQL.
   - Boton de carga detectado.
   - Acceso autorizado.
   - HTTP 401/403.
   - CAPTCHA.
   - Linaje y exportaciones.

Este recorrido prueba el comportamiento sin abrir trafico externo innecesario.

### Parte B: explicar la interfaz

1. Ejecutar:

   ```powershell
   python -m smart_scraper.gui
   ```

2. Mostrar la URL, el metodo y el campo de diagnostico.
3. Elegir `requests` como ejemplo basico.
4. Introducir una URL previamente autorizada y con limites bajos.
5. Pulsar **Inspeccionar**.
6. Leer el JSON diagnostico:
   - estado HTTP;
   - titulo;
   - señales de JavaScript;
   - APIs visibles;
   - paginacion;
   - cargas bajo demanda;
   - autenticacion o CAPTCHA.
7. Configurar un selector de registros y campos reales comprobables.
8. Elegir `csv` o `json`.
9. Pulsar **Extraer y guardar**.
10. Abrir la carpeta configurada y mostrar:
   - el archivo de datos;
   - el archivo de linaje;
   - el reporte;
   - el perfil;
   - el log.

Si no existe una URL autorizada para la demostracion, usar los datos sinteticos o la suite automatizada.

### Parte C: explicar una ejecucion

Un ejemplo de presentacion:

> Primero, la interfaz valida la URL y la configuracion. Luego el inspector descarga una respuesta acotada y evalua señales del sitio. El adaptador correspondiente adquiere los datos. El selector convierte el HTML o JSON en registros. La etapa de transformacion limpia, deduplica y genera linaje. Finalmente, la capa de almacenamiento guarda los datos, crea el perfil y registra los cambios respecto a ejecuciones anteriores.

### Parte D: mostrar trazabilidad

1. Abrir el CSV de datos.
2. Abrir el CSV de linaje.
3. Explicar que el linaje contiene URL de origen, fecha UTC, metodo, campo, valor, estado de validacion y transformaciones.
4. Abrir el reporte JSON.
5. Comparar los archivos de una segunda ejecucion y explicar `added_fields`, `missing_fields`, `new_endpoints`, `removed_endpoints` y `record_count_delta`.

## 11. Uso responsable y seguridad

Antes de una demostracion:

- Revisar términos de uso y robots.txt.
- Comprobar permisos y finalidad autorizada.
- Usar una cuenta propia o credenciales autorizadas.
- Limitar registros, paginas y frecuencia.
- Mantener pausas de al menos un segundo.
- Minimizar datos personales.
- No publicar datasets, perfiles, logs o credenciales sin autorizacion.

La aplicacion:

- No resuelve CAPTCHA.
- No evade autenticacion.
- No intenta sortear controles.
- No rota proxies.
- No automatiza login.
- No guarda encabezados ni perfiles con secretos.
- Se detiene ante 401, 403, 429 y CAPTCHA detectado.
- Rechaza secretos usados en parametros sensibles de la URL.

## 12. Problemas frecuentes

| Problema | Accion |
|---|---|
| `No module named ...` | Activar el entorno e instalar con `python -m pip install -e ".[all]"`. |
| PowerShell bloquea la activacion | Ejecutar directamente `.venv\Scripts\python.exe`. |
| Tkinter no aparece | Usar una distribucion oficial de Python para Windows con Tcl/Tk. |
| Selenium no inicia | Actualizar Chrome y verificar Selenium Manager. |
| Playwright no inicia | Ejecutar `python -m playwright install chromium`. |
| Cero registros | Revisar el selector de registros y los campos. |
| Ruta JSON incorrecta | Comprobar `items`, `data.results` o el nombre real de la respuesta. |
| HTTP 401/403/429 | Detener la prueba y revisar autorizacion. |
| CAPTCHA | No continuar ni intentar resolverlo. |
| Excel no se guarda | Instalar `.[excel]`. |
| PostgreSQL no guarda | Instalar `.[postgres]` y definir `SCRAPER_POSTGRES_DSN`. |
| MongoDB no guarda | Instalar `.[mongodb]` y definir `SCRAPER_MONGODB_URI`. |

## 13. Rutas de lectura sugeridas

Para preparar una presentacion en el siguiente orden:

1. [README.md](README.md): resumen del proyecto.
2. Esta guia: conceptos y recorrido de demostracion.
3. [GUIA_DESARROLLO_Y_OPERACION.md](GUIA_DESARROLLO_Y_OPERACION.md): instalacion y operacion detallada.
4. [docs/INFORME_TECNICO.md](docs/INFORME_TECNICO.md): evidencia tecnica y limitaciones.
5. [tests/test_pipeline.py](tests/test_pipeline.py): casos de prueba implementados.
6. [smart_scraper/app.py](smart_scraper/app.py): coordinacion del flujo.
7. [smart_scraper/gui.py](smart_scraper/gui.py): comportamiento visible de la interfaz.
