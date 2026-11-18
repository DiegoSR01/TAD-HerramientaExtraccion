# Guion de la demostración en vivo

*Generado por `video/grabar_demo.py` con los tiempos reales de la grabación. Narra: **Andrea Arroyo**.*

- Técnicas de Adquisición de Datos · Tecnológico de Toluca
- Integrantes: Nelson Noriega, Andrea Arroyo, Diego Salazar
- Duración: **3:16** (portada 10 s + demostración + cierre 6 s)
- Si la voz no cabe en un paso, recorten o alarguen la pausa en el editor; los tiempos son los de la pantalla.

## 00:00 – 00:12 · portada

Hola, somos Nelson Noriega, Andrea Arroyo y Diego Salazar, del Tecnológico de Toluca. Presentamos la demostración en vivo de nuestra herramienta para la materia Técnicas de Adquisición de Datos.

## 00:12 – 00:23 · intro

Esta es la demostración en vivo. Abrimos el proyecto en Visual Studio Code: el paquete smart_scraper contiene los siete módulos de la arquitectura.

## 00:23 – 00:40 · extractor

En extractor.py está la función _acquire_selenium. Configura Chrome, navega a la URL, espera con WebDriverWait, revisa si hay CAPTCHA o login, hace clics y scroll acotados y siempre cierra el navegador con driver.quit.

## 00:40 – 00:52 · app

En app.py, la función run_job orquesta el flujo: inspecciona, extrae, selecciona, transforma, guarda y registra el informe de la ejecución.

## 00:52 – 01:04 · config

En config.py, ScrapeConfig valida los límites: máximo diez páginas, mil registros y una pausa mínima de un segundo entre solicitudes.

## 01:04 – 01:24 · pruebas

Ahora ejecutamos las pruebas automatizadas con pytest. Usan un servidor local con sitios simulados: HTML estático, JavaScript, API, paginación, autenticación y CAPTCHA. Las catorce pruebas pasan.

## 01:24 – 01:45 · gui

Abrimos la interfaz gráfica de la herramienta. Ingresamos la URL de books.toscrape.com, un sitio creado para practicar extracción, elegimos el método Selenium con el navegador visible y definimos los selectores CSS de cada campo.

## 01:45 – 01:59 · inspeccion

Primero pulsamos Inspeccionar. La herramienta diagnostica el sitio: título, señales de JavaScript, paginación y si existe CAPTCHA o autenticación.

## 01:59 – 02:54 · extraccion

Después pulsamos Extraer y guardar. Selenium abre Chrome, carga cada página, sigue el enlace siguiente y respeta la pausa entre solicitudes. Al terminar, el panel muestra el informe con el número de registros y las validaciones.

## 02:54 – 03:10 · resultado

Por último abrimos el CSV generado: cada libro con su título, precio, disponibilidad, rating y URL, listo para limpiar y analizar. Así se ejecuta la arquitectura de principio a fin.

## 03:10 – 03:16 · cierre

Gracias por su atención.
