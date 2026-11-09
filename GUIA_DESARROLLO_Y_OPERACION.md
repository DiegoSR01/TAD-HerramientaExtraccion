# Guía de desarrollo y operación

Guía práctica de instalación, uso, arquitectura, pruebas y mantenimiento de **Web Scraper Inteligente**, entregado como proyecto de TAD. La aplicación permite inspeccionar una URL, configurar una extracción acotada, procesar los datos y guardar resultados con información de linaje.

Repositorio: [DiegoSR01/TAD-HerramientaExtraccion](https://github.com/DiegoSR01/TAD-HerramientaExtraccion)

## 1. Requisitos

- Windows 10/11 y Python 3.10 o posterior.
- Git para clonar el repositorio.
- Tkinter, incluido normalmente en las distribuciones oficiales de Python para Windows.
- Chrome y Selenium Manager para el método Selenium. Selenium Manager administra el driver cuando la instalación lo permite.
- Los navegadores de Playwright solo son necesarios para ese método.
- Acceso a los sitios y endpoints que se pretenda consultar. Antes de extraer datos, revisa los términos, permisos, robots, privacidad y límites aplicables.

## 2. Clonar e instalar en Windows

Abre PowerShell y ejecuta:

```powershell
git clone https://github.com/DiegoSR01/TAD-HerramientaExtraccion.git
Set-Location TAD-HerramientaExtraccion
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Si PowerShell impide activar el entorno, no es obligatorio activarlo: utiliza directamente `.\.venv\Scripts\python.exe` en los comandos `python` de esta guía.

Para Excel instala el extra correspondiente:

```powershell
python -m pip install -e ".[excel]"
```

Para instalar todas las dependencias opcionales y de pruebas:

```powershell
python -m pip install -e ".[all]"
python -m playwright install chromium
```

Playwright y PostgreSQL/MongoDB son opcionales. Para usar PostgreSQL o MongoDB no es necesario instalar Playwright, aunque `.[all]` instala ambos drivers de base de datos. Otra opción para instalar las dependencias base es `python -m pip install -r requirements.txt`.

## 3. Iniciar la aplicación

Con el entorno virtual activo, inicia la interfaz:

```powershell
python -m smart_scraper.gui
```

También se puede usar:

```powershell
python -m smart_scraper
```

La ventana permite inspeccionar, configurar y ejecutar tareas. El directorio inicial de resultados es `output` dentro de la carpeta actual; puede cambiarse desde el botón **Carpeta…**.

## 4. Flujo de uso

### 4.1 Inspeccionar

1. Escribe una URL que comience con `http://` o `https://`.
2. Deja `requests` seleccionado para una inspección normal; pulsa **1. Inspeccionar**.
3. Revisa el resumen que muestra el estado HTTP, el título, las señales de JavaScript, formularios, posibles APIs, paginación, carga bajo demanda y restricciones.

El diagnóstico usa HTML y pistas estáticas. No captura de manera exhaustiva la red del navegador ni puede decidir si el uso es legal. Sus resultados son indicios, no garantías.

### 4.2 Configurar campos HTML

En **Selector de registros (CSS)** indica el selector común de cada registro, por ejemplo `article.product`. Define un campo por línea en el área de campos:

```text
nombre=h2.product-title
enlace=a.product-link::href
precio=.price
```

El formato es `nombre=selector`. El sufijo `*` marca que el valor se considera requerido:

```text
nombre*=h2.product-title
```

Algunos selectores CSS útiles:

- `.tarjeta`: elementos con clase `tarjeta`.
- `article.product`: artículos con clase `product`.
- `a.resultado::href`: atributo `href` del primer enlace seleccionado dentro de cada registro.
- `img::src`: atributo `src` de una imagen.

Los selectores de campo se evalúan dentro de cada registro si se indicó un selector de registros; si este se deja vacío, se evalúan sobre el documento completo. Si no se indican campos, la aplicación intenta extraer la primera tabla HTML; si no hay tabla, usa el título y los encabezados `h1`/`h2` como muestra básica. Para resultados reutilizables se recomienda definir explícitamente los campos.

### 4.3 Elegir el método

| Método | Cuándo usarlo | Consideraciones |
|---|---|---|
| `requests` | El HTML de respuesta contiene los datos | Usa Requests y BeautifulSoup; no ejecuta JavaScript |
| `selenium` | El contenido requiere renderizado con navegador | Requiere Chrome; scroll y clics opcionales están acotados |
| `playwright` | Se prefiere navegador Playwright | Requiere instalar el extra y Chromium |
| `api` | Se cuenta con un endpoint JSON cuyo uso está autorizado | Marca la casilla de autorización y define campos JSON |

Para API se puede indicar una ruta de lista, por ejemplo `items` o `data.results`. En cada campo, usa una ruta JSON separada por puntos, como `product.name`. La aplicación solo admite el endpoint que se proporciona; no descubre exhaustivamente ni monitorea el tráfico de red de una aplicación.

### 4.4 Paginación y contenido bajo demanda

- **Selector de siguiente página (CSS):** selector del enlace/botón que contiene el `href` de la página siguiente. El scraper sigue solamente enlaces del mismo host, respeta el máximo de páginas y la pausa mínima de un segundo.
- **Selector botón cargar más:** selector CSS del botón que ya identificaste. Los clics solo se habilitan con Selenium o Playwright, y el límite configurable es de cero a cinco.
- **Scrolls:** número de desplazamientos del navegador, de cero a cinco.
- **Pausa:** intervalo entre páginas, desde un segundo. No es una herramienta para aumentar la velocidad; usa pausas mayores cuando el sitio lo requiera.

Un selector incorrecto puede dar cero resultados, hacer que se repita contenido o no detectar el botón. Revisa el resultado y el informe antes de reutilizar un perfil.

### 4.5 Autorización y credenciales

Para un endpoint API, activa **Confirmo autorización del endpoint API** solo cuando hayas comprobado que su uso está permitido. La aplicación no automatiza inicios de sesión ni evade controles.

Si recibiste autorización para usar encabezados, ingrésalos como un objeto JSON de cadenas en el campo correspondiente; el campo oculta visualmente el texto. Ejemplo ilustrativo:

```json
{"Authorization": "Bearer TOKEN_AUTORIZADO"}
```

No uses ese ejemplo literalmente. No pongas tokens en la URL, perfiles, archivos versionados o reportes. Los perfiles no guardan encabezados y al cargarlos debes confirmar de nuevo el permiso para el método API.

### 4.6 Límites de extracción

La configuración impone estos máximos por tarea:

- Respuesta HTML de hasta 2 MB.
- 1.000 registros.
- 10 páginas.
- 5 desplazamientos.
- 5 clics de botón de carga.
- Timeout HTTP entre 1 y 30 segundos.
- Pausa de al menos 1 segundo.

Usa límites pequeños y una sola ejecución manual al validar selectores. No lances rastreos masivos ni ejecuciones repetitivas sobre servicios públicos.

## 5. Resultados y archivos generados

Al completar una ejecución, la carpeta elegida puede contener:

| Archivo | Contenido |
|---|---|
| `records-<id>.csv` | Filas limpias, con codificación compatible con Excel |
| `lineage-<id>.csv` | Linaje por registro/campo |
| `records-<id>.xlsx` | Hojas `records` y `lineage`; requiere `openpyxl` |
| `records-<id>.json` | Datos y linaje incluido en cada registro |
| `scraper.sqlite3` | Tablas SQLite `records`, `lineage` y snapshots |
| `.scraper_history.sqlite3` | Snapshots de comparación si el destino no es SQLite |
| `profiles/<host>.json` | Perfil técnico sin encabezados ni confirmación de autorización |
| `report-<id>.json` | Estado, diagnóstico, conteos, cambios, advertencias y rutas |
| `smart_scraper.log` | Eventos de ejecución y errores |

En SQLite, cada fila contiene la URL fuente, método, fecha/hora de adquisición e identificador de ejecución. El linaje registra cada campo, valor, estado de validación y transformaciones. En CSV/Excel el linaje se guarda en archivo u hoja separada; en JSON acompaña cada fila.

Los perfiles y snapshots son locales al directorio de salida. Para reutilizar perfiles, conserva esa carpeta; el botón **Cargar perfil del sitio** busca el perfil según el host de la URL actual.

### PostgreSQL y MongoDB (opcional)

Instala el driver elegido y configura la cadena de conexión fuera del código:

```powershell
python -m pip install -e ".[postgres]"
$env:SCRAPER_POSTGRES_DSN = "cadena-de-conexion-autorizada"
```

```powershell
python -m pip install -e ".[mongodb]"
$env:SCRAPER_MONGODB_URI = "cadena-de-conexion-autorizada"
```

Las variables del ejemplo solo existen en esa sesión de PowerShell. No las guardes en Git ni compartas sus valores. El esquema y permisos del servidor de base de datos son responsabilidad del operador.

## 6. Arquitectura implementada

La lógica se separa en siete módulos para que los métodos de adquisición, la selección y la persistencia puedan evolucionar sin concentrar todo en la interfaz:

| Módulo | Archivo | Qué hace |
|---|---|---|
| 1. Configuración | `smart_scraper/config.py` | Tipos, URL, límites, campos, validación y perfiles por host |
| 2. Inspección y diagnóstico | `smart_scraper/inspector.py` | Descarga acotada, estado HTTP, HTML, señales de JS y restricciones |
| 3. Motor de extracción | `smart_scraper/extractor.py` | Adaptadores Requests, Selenium, Playwright y endpoint JSON autorizado |
| 4. Selección de información | `smart_scraper/selection.py` | Selectores CSS, rutas JSON y tablas HTML |
| 5. Transformación y calidad | `smart_scraper/transform.py` | Limpieza de espacios, validación requerida, deduplicación y linaje |
| 6. Almacenamiento | `smart_scraper/storage.py` | Exportaciones a archivo, SQLite y conectores opcionales |
| 7. Monitoreo | `smart_scraper/monitoring.py` | Reporte JSON y log |

`smart_scraper/app.py` coordina la tarea de extremo a extremo y `smart_scraper/gui.py` implementa la interfaz Tkinter. `smart_scraper/__main__.py` permite iniciar la GUI como módulo.

La comparación entre ejecuciones detecta cambios en nombres de campos, endpoints visibles en el HTML y volumen de registros. No compara los valores de todos los campos entre snapshots ni inspecciona el tráfico real de red. La primera ejecución para un host establece una línea base.

## 7. Cómo se desarrolló

El desarrollo siguió las cinco fases solicitadas:

1. **Diagnóstico e inspección:** se creó un inspector HTTP con límite de tamaño, timeout, análisis heurístico del HTML, señales de JavaScript/API, paginación y controles de acceso.
2. **Extracción multitecnología:** se añadieron adaptadores separados para Requests, Selenium, Playwright opcional y JSON API con confirmación de autorización.
3. **Selección y procesamiento:** se implementaron reglas configurables CSS/JSON, extracción de tablas, normalización, deduplicación, validación de campos requeridos y linaje.
4. **Almacenamiento e interfaz:** se conectaron exportaciones CSV/Excel/JSON/SQLite, conectores opcionales PostgreSQL/MongoDB, perfiles, snapshots, reporte y la GUI.
5. **Pruebas, documentación y optimización:** se agregaron pruebas con un servidor local simulado, documentación técnica, dataset de ejemplo sintético, límites de carga y detección de restricciones.

El trabajo se organizó para probar cada capa por separado y luego integrar el flujo con pruebas locales. Los detalles de cobertura, las observaciones técnicas de las cinco URLs suministradas y sus limitaciones se encuentran en [docs/INFORME_TECNICO.md](docs/INFORME_TECNICO.md).

## 8. Ejecutar pruebas y desarrollar

Instala las dependencias de desarrollo:

```powershell
python -m pip install -e ".[test]"
```

Ejecuta la suite:

```powershell
python -m pytest -q
```

Las pruebas levantan un servidor HTTP local, cubriendo HTML estático/dinámico, API JSON/GraphQL, tabla, paginación, botón de carga, autenticación autorizada de prueba, 401/403, CAPTCHA, linaje y exportaciones. Selenium y Playwright se prueban con adaptadores simulados; no es una prueba de navegador real. La última validación del proyecto completó **14 pruebas**, además de compilación de módulos e importación de la GUI.

Para comprobar sintaxis manualmente:

```powershell
python -m compileall -q smart_scraper tests
```

La compilación genera carpetas `__pycache__`, ignoradas por Git.

## 9. Pruebas puntuales de las URLs entregadas

Se hizo una inspección individual de bajo impacto (sin paginación, sin scroll y con pausa entre destinos). En esa ejecución:

- INEGI respondió HTTP 200, pero no se configuró un extractor de registros específico.
- `datos.gob.mx` respondió HTTP 403; se detuvo, sin reintentos ni evasión.
- World Bank y Data.gov respondieron HTTP 200; la muestra visible no equivale a un dataset validado.
- La URL de DOF produjo un error TLS por discrepancia del hostname; no se desactivó la validación del certificado.

Estos resultados son observaciones puntuales, pueden cambiar y no certifican viabilidad legal. Antes de nuevas consultas, revisa términos, robots, permisos, privacidad y límites aplicables. La herramienta se detiene ante CAPTCHA/challenge, HTTP 401/403/429; no sortea bloqueos.

## 10. Solución de problemas

| Síntoma | Qué revisar |
|---|---|
| `No module named ...` | Confirma el entorno activo y ejecuta `python -m pip install -e .` o instala el extra requerido |
| Tkinter no está disponible | Usa una distribución de Python para Windows que incluya Tcl/Tk |
| Selenium no inicia Chrome | Instala/actualiza Chrome, verifica acceso de Selenium Manager al driver y prueba primero un sitio autorizado simple |
| Playwright no encuentra Chromium | Ejecuta `python -m playwright install chromium` en el mismo entorno |
| Cero filas exportadas | Revisa el selector de registros, los selectores de campos y el HTML entregado en el diagnóstico |
| Error de ruta JSON | Confirma que la ruta de registros apunta a una lista/objeto y que las rutas de campo concuerdan con la respuesta |
| HTTP 401, 403, 429 o CAPTCHA | Detén la ejecución; consulta al responsable del servicio y usa únicamente acceso aprobado |
| Error TLS/certificado | Verifica el dominio y su certificado con el responsable; nunca desactives la validación para forzar la solicitud |
| Falla de PostgreSQL/MongoDB | Comprueba el extra instalado, la variable de entorno, la conectividad y los permisos de la base |
| El perfil API no ejecuta | Vuelve a confirmar en la interfaz la autorización del endpoint |

El informe y el log de cada ejecución están en la carpeta de resultados y contienen el error correspondiente cuando una tarea falla.

## 11. Límites y trabajo futuro

- Las detecciones de JavaScript, CAPTCHA, interacción, login, APIs y carga son heurísticas.
- No existe captura exhaustiva de XHR/Fetch/red, inferencia automática confiable de selectores ni resolución de CAPTCHA.
- La GUI no automatiza login/cookies. La autorización se limita a encabezados que el operador ya esté autorizado a utilizar.
- La compatibilidad con una URL no significa que el sitio permita extraer datos.
- No se ha certificado extracción real con Selenium o Playwright sobre los cinco sitios externos.
- Los archivos de ejemplo son datos sintéticos, no resultados extraídos de los sitios nombrados.
- No se incluye un archivo de licencia de software; no asumas permisos de redistribución o uso distintos de los que autorice el titular del repositorio.

## 12. Publicación

El código y esta guía se mantienen en la rama `main` del repositorio enlazado al inicio. Para obtener la versión más reciente:

```powershell
git pull origin main
```

Antes de crear cambios, ejecuta las pruebas; no incluyas entornos virtuales, credenciales, bases locales, logs o resultados de sitios que no tengas autorización para publicar.
