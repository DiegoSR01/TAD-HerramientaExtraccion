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

La viabilidad legal de los cinco destinos queda **pendiente de revisión humana**: verificar términos de uso, robots, permisos aplicables, finalidad, límites de servicio y privacidad antes de ejecutar extracción adicional. No se asigna una conclusión legal basándose solo en el acceso HTTP.

**Regla de clasificación:** solo continuar si el titular permite el acceso para el propósito previsto, el tratamiento de los datos es lícito, se respetan términos, robots y límites, y la autenticación usada pertenece a una cuenta autorizada. En caso de CAPTCHA, bloqueo o duda, detener la prueba y solicitar permiso al responsable.

## Datos y entregables

- `examples/sample_dataset.csv` y `examples/sample_lineage.csv`: dataset sintético de demostración.
- Cada fila de linaje registra ejecución, URL de origen, instante UTC, método, campo, valor, validación y transformaciones.
- `report-<id>.json`, `smart_scraper.log` y `profiles/<host>.json`: informe, log y perfil técnico sin encabezados de autenticación.
- SQLite conserva registros, linaje y último snapshot por host; CSV/Excel generan una hoja/archivo auxiliar para linaje.

## Limitaciones conocidas y siguientes pruebas autorizadas

- Las pistas de API y de comportamiento dinámico se obtienen del HTML y JavaScript visibles; no existe captura exhaustiva de tráfico de red del navegador.
- La detección de CAPTCHA, login, botón de carga e infinite scroll es heurística y puede producir falsos positivos/negativos.
- La autenticación de navegador requiere que el usuario gestione legítimamente la sesión; la aplicación no automatiza login ni guarda cookies.
- Para completar la evaluación real, el operador debe obtener autorización, registrar URLs y propósito, verificar robots/términos, fijar un horario y límites más conservadores y documentar resultados y datos personales minimizados.
