# Guion de la demostración (arquitectura en ejecución)

*Generado por `video/grabar_demo_avance.py` con los tiempos reales de la grabación. Narra: **Andrea Arroyo**.*

- Técnicas de Adquisición de Datos · Tecnológico de Toluca
- Integrantes: Nelson Noriega, Andrea Arroyo, Diego Salazar
- Duración: **3:20** (portada 8 s + arquitectura 22 s + demostración en vivo + cierre 6 s)
- Si la voz no cabe en un tramo, recorten o alarguen la pausa en el editor; los tiempos son los de la pantalla.

## 00:00 – 00:08 · portada

Hola, somos Nelson Noriega, Andrea Arroyo y Diego Salazar, del Tecnológico de Toluca. Esta es la demostración de la arquitectura ejecutándose, para Técnicas de Adquisición de Datos.

## 00:08 – 00:34 · arquitectura

La arquitectura tiene siete módulos: configuración, inspección, adquisición, selección, transformación, almacenamiento y monitoreo. app.py los orquesta en un flujo de nueve pasos y la interfaz Tkinter muestra el avance en vivo. Lo importante: es un solo motor. Cada sitio nuevo es solo otra configuración.

## 00:34 – 00:40 · e1_config

Escenario uno: HTML estático con paginación. En la capa de presentación, gui.py, capturamos la URL, el método requests y los selectores CSS. Todo se convierte en un ScrapeConfig.

## 00:40 – 00:50 · e1_inspeccion

Al pulsar Inspeccionar, app.py recorre los pasos uno a tres. Config valida la URL, inspector.py hace una sola solicitud GET y estrategia.py clasifica el escenario y recomienda el método.

## 00:50 – 01:00 · e1_extraccion

Con Extraer y guardar continúa el flujo. El motor de extracción obtiene cada página y respeta la pausa de dos segundos; selection aplica los selectores, transform limpia y valida, storage guarda el CSV y monitoring escribe el informe. La barra avanza paso a paso.

## 01:00 – 01:05 · e2_config

Escenario dos: un sitio con JavaScript. Es el mismo motor; solo cambia la configuración: método selenium con Chrome visible, a la derecha, y selectores del contenido ya renderizado.

## 01:05 – 01:14 · e2_inspeccion

El inspector detecta que el HTML inicial casi no trae las citas y que hay señales de JavaScript. La estrategia recomendada cambia a selenium.

## 01:14 – 01:38 · e2_extraccion

Selenium abre Chrome, espera a que el navegador renderice las citas, lee el DOM y sigue a la siguiente página. Después se repiten los mismos pasos de selección, limpieza, almacenamiento e informe.

## 01:38 – 01:44 · e3_config

Escenario tres: una API JSON. Indicamos el método api y la ruta de la lista de registros, y confirmamos que el endpoint está autorizado; sin esa casilla el motor no lo consulta.

## 01:44 – 01:52 · e3_inspeccion

La inspección reconoce una respuesta JSON y la estrategia recomienda api.

## 01:52 – 02:00 · e3_extraccion

Sin navegador: una solicitud GET al endpoint, selection recorre la ruta quotes, y transform y storage completan los nueve pasos del mismo flujo.

## 02:00 – 02:05 · e4_config

Escenario cuatro: una página protegida con reCAPTCHA. Aquí mostramos el comportamiento responsable de la herramienta.

## 02:05 – 02:16 · e4_inspeccion

El inspector detecta el CAPTCHA. El paso tres se marca como incidencia y el cuadro de escenario cambia a naranja.

## 02:16 – 02:26 · e4_extraccion

Al intentar extraer, el motor se detiene: no resuelve ni evade el CAPTCHA. Los pasos siguientes quedan sin ejecutar y el informe explica el motivo.

## 02:26 – 02:46 · e5_rerun

Por último repetimos el escenario uno. Monitoring compara con la ejecución anterior para detectar cambios, y el registro lo informa.

## 02:46 – 03:00 · resultado_csv

Todos los escenarios se consolidaron en un dataset multisitio con linaje: escenario, URL de origen, método y ejecución de cada valor.

## 03:00 – 03:14 · resultado_matriz

La matriz de escenarios resume sitio, mecanismo detectado, estrategia, resultado y viabilidad. Un único motor, muchos escenarios.

## 03:14 – 03:20 · cierre

Gracias por su atención.

## Marcas del progreso real de la GUI (referencia)

| Tiempo en el video | Marca (escenario_paso_estado) |
|---|---|
| 00:42 | `e1_p1_running` |
| 00:42 | `e1_p1_done` |
| 00:42 | `e1_p2_running` |
| 00:43 | `e1_p2_done` |
| 00:43 | `e1_p3_done` |
| 00:50 | `e1_p1_running` |
| 00:50 | `e1_p1_done` |
| 00:50 | `e1_p2_done` |
| 00:50 | `e1_p3_done` |
| 00:50 | `e1_p4_done` |
| 00:50 | `e1_p5_done` |
| 00:50 | `e1_p6_running` |
| 00:50 | `e1_p6_running` |
| 00:53 | `e1_p6_running` |
| 00:53 | `e1_p6_done` |
| 00:53 | `e1_p7_running` |
| 00:53 | `e1_p7_done` |
| 00:53 | `e1_p8_running` |
| 00:53 | `e1_p8_done` |
| 00:53 | `e1_p9_running` |
| 00:53 | `e1_p9_done` |
| 01:06 | `e2_p1_running` |
| 01:06 | `e2_p1_done` |
| 01:07 | `e2_p2_running` |
| 01:07 | `e2_p2_done` |
| 01:07 | `e2_p3_done` |
| 01:15 | `e2_p1_running` |
| 01:15 | `e2_p1_done` |
| 01:15 | `e2_p2_done` |
| 01:15 | `e2_p3_done` |
| 01:15 | `e2_p4_done` |
| 01:15 | `e2_p5_done` |
| 01:15 | `e2_p6_running` |
| 01:23 | `e2_p6_running` |
| 01:33 | `e2_p6_running` |
| 01:33 | `e2_p6_done` |
| 01:33 | `e2_p7_running` |
| 01:33 | `e2_p7_done` |
| 01:33 | `e2_p8_running` |
| 01:33 | `e2_p8_done` |
| 01:33 | `e2_p9_running` |
| 01:33 | `e2_p9_done` |
| 01:45 | `e3_p1_running` |
| 01:45 | `e3_p1_done` |
| 01:45 | `e3_p2_running` |
| 01:46 | `e3_p2_done` |
| 01:46 | `e3_p3_done` |
| 01:52 | `e3_p1_running` |
| 01:52 | `e3_p1_done` |
| 01:52 | `e3_p2_done` |
| 01:52 | `e3_p3_done` |
| 01:52 | `e3_p4_done` |
| 01:52 | `e3_p5_done` |
| 01:52 | `e3_p6_running` |
| 01:52 | `e3_p6_running` |
| 01:52 | `e3_p6_done` |
| 01:52 | `e3_p7_running` |
| 01:52 | `e3_p7_done` |
| 01:52 | `e3_p8_running` |
| 01:52 | `e3_p8_done` |
| 01:52 | `e3_p9_running` |
| 01:52 | `e3_p9_done` |
| 02:06 | `e4_p1_running` |
| 02:06 | `e4_p1_done` |
| 02:06 | `e4_p2_running` |
| 02:06 | `e4_p2_done` |
| 02:06 | `e4_p3_blocked` |
| 02:16 | `e4_p1_running` |
| 02:16 | `e4_p1_done` |
| 02:16 | `e4_p2_done` |
| 02:16 | `e4_p3_blocked` |
| 02:16 | `e4_p9_running` |
| 02:16 | `e4_p9_error` |
| 02:28 | `e5_p1_running` |
| 02:28 | `e5_p1_done` |
| 02:28 | `e5_p2_running` |
| 02:29 | `e5_p2_done` |
| 02:29 | `e5_p3_done` |
| 02:29 | `e5_p4_done` |
| 02:29 | `e5_p5_done` |
| 02:29 | `e5_p6_running` |
| 02:29 | `e5_p6_running` |
| 02:31 | `e5_p6_running` |
| 02:31 | `e5_p6_done` |
| 02:31 | `e5_p7_running` |
| 02:31 | `e5_p7_done` |
| 02:31 | `e5_p8_running` |
| 02:31 | `e5_p8_done` |
| 02:31 | `e5_p9_running` |
| 02:31 | `e5_p9_done` |
