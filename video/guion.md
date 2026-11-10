# Guion del video de demostración (arquitectura ejecutada)

*Generado por `video/build_video.py` a partir de la lista `ESCENAS`; no editar a mano: edite el script y vuelva a ejecutarlo.*

- Duración total: **3:58 (239 s)** · 513 palabras de narración · ritmo base 2.3 palabras/s.
- Cada escena deja ~0,5 s de silencio al inicio (fundido) y ~0,25 s al final; lean con calma y de forma natural, sin acelerar.
- Los subtítulos del video (`subtitulos.srt`) reproducen exactamente este texto.
- Reparto sugerido: Voz 1 y Voz 2 alternan escena por escena. Sustituyan `[Nombre 1]` y `[Nombre 2]` en la portada y el cierre (están en `build_video.py`).

## Escena 1 · Portada

- **Tiempo:** 0:00–0:12 (12.5 s, 26 palabras)
- **Lee:** Voz 1
- **Se ve:** Título del proyecto, integrantes (placeholder) y los siete módulos como fichas.

**Narración:** Hola, somos [Nombre 1] y [Nombre 2]. Presentamos la Herramienta de Extracción Web Inteligente del curso TAD y la arquitectura que ejecutamos de principio a fin.

## Escena 2 · Problema y objetivo

- **Tiempo:** 0:12–0:31 (19.0 s, 41 palabras)
- **Lee:** Voz 2
- **Se ve:** Dos tarjetas: el problema (sitios heterogéneos) y el objetivo (herramienta local, modular y responsable).

**Narración:** Extraer datos de la web no es solo descargar páginas. Hay HTML estático, JavaScript, APIs, paginación y controles de acceso. Nuestro objetivo: una herramienta local, configurable y modular, que inspeccione el sitio y entregue datos limpios, trazables y obtenidos con responsabilidad.

## Escena 3 · Arquitectura de siete módulos

- **Tiempo:** 0:31–0:51 (20.3 s, 44 palabras)
- **Lee:** Voz 1
- **Se ve:** Diagrama de cajas con flechas: Configuración → Inspección → Extracción (Requests, Selenium, Playwright, API) → Selección → Transformación → Almacenamiento → Monitoreo; app.py orquesta y gui.py es la interfaz.

**Narración:** La solución tiene siete módulos. Configuración define URL, límites y selectores. Inspección diagnostica el sitio. El motor de extracción usa Requests, Selenium, Playwright o una API autorizada. Siguen selección, transformación y calidad, almacenamiento y monitoreo. app.py los orquesta y la interfaz Tkinter los expone.

## Escena 4 · Flujo de ejecución

- **Tiempo:** 0:51–1:09 (17.7 s, 38 palabras)
- **Lee:** Voz 2
- **Se ve:** Lista de los pasos de run_job() y recuadros de 'se detiene si…' y 'siempre'.

**Narración:** Así fluye run_job. Valida la configuración e inspecciona la página; si hay 401, 403, 429 o CAPTCHA, se detiene. Si no, adquiere, transforma, guarda, compara con la ejecución anterior y escribe un informe JSON, incluso cuando hay errores.

## Escena 5 · Código real: Selenium

- **Tiempo:** 1:09–1:32 (22.5 s, 49 palabras)
- **Lee:** Voz 1
- **Se ve:** Fragmento real de _acquire_selenium con resaltado de sintaxis y siete pasos señalados.

**Narración:** Este es código real del método Selenium. Se configura Chrome headless, se abre la URL y WebDriverWait espera a que el documento cargue. Antes de interactuar se revisa CAPTCHA o login. Luego hay clics acotados en cargar más y desplazamientos limitados. Y en finally, driver.quit siempre cierra el navegador.

## Escena 6 · Selección CSS / JSON

- **Tiempo:** 1:32–1:51 (19.5 s, 42 palabras)
- **Lee:** Voz 2
- **Se ve:** HTML de una tarjeta de libro, reglas nombre=selector reales del dataset, ejemplo de ruta JSON y registro resultante.

**Narración:** La selección convierte HTML en campos. Un selector de elemento repetido y reglas nombre igual selector, como titulo igual h3 a dos puntos title, leen texto o atributos. El asterisco marca un campo requerido. En APIs se usan rutas JSON con puntos.

## Escena 7 · Transformación y linaje

- **Tiempo:** 1:51–2:08 (17.3 s, 37 palabras)
- **Lee:** Voz 1
- **Se ve:** Limpiezas aplicadas (antes → después) y una fila de linaje con sus campos.

**Narración:** La transformación recorta espacios, elimina duplicados y valida campos requeridos. Cada valor genera una fila de linaje con ejecución, URL de origen, método, fecha, estado de validación y transformaciones. Así cada dato se rastrea hasta su origen.

## Escena 8 · Almacenamiento

- **Tiempo:** 2:08–2:28 (19.9 s, 43 palabras)
- **Lee:** Voz 2
- **Se ve:** Tarjetas SQLite, CSV, Excel y JSON con tamaños reales de los archivos; extras PostgreSQL/MongoDB.

**Narración:** El almacenamiento exporta a CSV, Excel, JSON y SQLite; PostgreSQL y MongoDB son opcionales. En SQLite guardamos la tabla de libros y la de linaje. También se guarda el perfil del sitio y se compara cada corrida con la anterior para detectar cambios.

## Escena 9 · Demo: dataset real

- **Tiempo:** 2:28–2:45 (16.9 s, 36 palabras)
- **Lee:** Voz 1
- **Se ve:** Tabla con filas reales del CSV, estadísticas y barras con la distribución de ratings.

**Narración:** Para la demostración usamos books.toscrape.com, un sandbox hecho para practicar scraping. La herramienta recorrió cinco páginas y obtuvo 100 libros sin duplicados. Vemos filas reales, un precio medio de 34,56 libras y la distribución de valoraciones.

## Escena 10 · Clasificación de sitios

- **Tiempo:** 2:45–3:06 (21.2 s, 46 palabras)
- **Lee:** Voz 2
- **Se ve:** Tabla de los 7 sitios del informe con protección observada y viabilidad legal (verde / ámbar / rojo).

**Narración:** También clasificamos siete sitios por protección y viabilidad legal. Los dos sandboxes son viables. INEGI, Banco Mundial, data.gov y el DOF son viables con condiciones. datos.gob.mx devolvió 403 y no es viable sin autorización: se usaría su API oficial. Es una evaluación técnica, no asesoría legal.

## Escena 11 · Seguridad y uso responsable

- **Tiempo:** 3:06–3:24 (17.7 s, 38 palabras)
- **Lee:** Voz 1
- **Se ve:** Dos columnas: lo que detiene la ejecución (rojo) y los límites que se respetan (verde).

**Narración:** La herramienta es conservadora. Se detiene ante CAPTCHA, formularios de autenticación y respuestas 401, 403 o 429, y no intenta evadirlos. Solo sigue paginación del mismo host, limita páginas, registros y tamaño del DOM, y espera entre solicitudes.

## Escena 12 · Pruebas automatizadas

- **Tiempo:** 3:24–3:40 (16.4 s, 35 palabras)
- **Lee:** Voz 2
- **Se ve:** Contador de 14 pruebas y la lista de sitios simulados.

**Narración:** Las 14 pruebas automatizadas pasan. Usan un servidor local con sitios simulados: estático, dinámico, carga bajo demanda, API, paginación, tabla, autenticación y CAPTCHA. Selenium y Playwright se prueban con adaptadores simulados, sin tocar sitios públicos.

## Escena 13 · Conclusiones y cierre

- **Tiempo:** 3:40–3:58 (17.7 s, 38 palabras)
- **Lee:** Voz 1 y Voz 2
- **Se ve:** Cuatro conclusiones, agradecimiento e integrantes (placeholder).

**Narración:** En resumen: siete módulos que inspeccionan, extraen, limpian, almacenan y monitorean con trazabilidad, validados con un dataset real de 100 libros. El siguiente paso es probar sitios reales solo con autorización, priorizando APIs oficiales. Gracias por su atención.
