# Guion de la demostración en vivo

*Generado por `video/grabar_demo.py` con los tiempos reales de la grabación. Narra: **Andrea Arroyo**.*

- Duración: **3:00**
- Si la voz no cabe en un paso, recorten o alarguen la pausa en el editor; los tiempos son los de la pantalla.

## 00:02 – 00:13 · intro

Esta es la demostración en vivo. Abrimos el proyecto en Visual Studio Code: el paquete smart_scraper contiene los siete módulos de la arquitectura.

## 00:13 – 00:30 · extractor

En extractor.py está la función _acquire_selenium. Configura Chrome, navega a la URL, espera con WebDriverWait, revisa si hay CAPTCHA o login, hace clics y scroll acotados y siempre cierra el navegador con driver.quit.

## 00:30 – 00:42 · app

En app.py, la función run_job orquesta el flujo: inspecciona, extrae, selecciona, transforma, guarda y registra el informe de la ejecución.

## 00:42 – 00:54 · config

En config.py, ScrapeConfig valida los límites: máximo diez páginas, mil registros y una pausa mínima de un segundo entre solicitudes.

## 00:54 – 01:14 · pruebas

Ahora ejecutamos las pruebas automatizadas con pytest. Usan un servidor local con sitios simulados: HTML estático, JavaScript, API, paginación, autenticación y CAPTCHA. Las catorce pruebas pasan.

## 01:14 – 01:35 · gui

Abrimos la interfaz gráfica de la herramienta. Ingresamos la URL de books.toscrape.com, un sitio creado para practicar extracción, elegimos el método Selenium con el navegador visible y definimos los selectores CSS de cada campo.

## 01:35 – 01:49 · inspeccion

Primero pulsamos Inspeccionar. La herramienta diagnostica el sitio: título, señales de JavaScript, paginación y si existe CAPTCHA o autenticación.

## 01:49 – 02:44 · extraccion

Después pulsamos Extraer y guardar. Selenium abre Chrome, carga cada página, sigue el enlace siguiente y respeta la pausa entre solicitudes. Al terminar, el panel muestra el informe con el número de registros y las validaciones.

## 02:44 – 03:00 · resultado

Por último abrimos el CSV generado: cada libro con su título, precio, disponibilidad, rating y URL, listo para limpiar y analizar. Así se ejecuta la arquitectura de principio a fin.
