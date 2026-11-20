# Video de demostración

## Entregable principal: "Arquitectura ejecutada" (`demo_avance.mp4`, 3:20)

Grabación real (1920x1080, 30 fps, 3:30 a 4:45 aprox., sin audio) de la herramienta ejecutando la arquitectura con el **panel de progreso** de la GUI (barra, contador n/9, tiempo, 9 pasos, escenario/estrategia y registro).

| Archivo | Contenido |
|---|---|
| `demo_avance.mp4` | Video con subtítulos quemados |
| `demo_avance_sin_subs.mp4` | Sin subtítulos (para editar con la voz) |
| `demo_avance.srt` | Subtítulos sincronizados con los tiempos reales |
| `guion_demo_avance.md` | Narración (Andrea Arroyo) con tiempos y marcas reales de cada paso |
| `grabar_demo_avance.py` | Script que graba todo (reutiliza helpers de `grabar_demo.py`) |

Contenido: portada (8 s) -> diapositiva de arquitectura (7 módulos + flujo de 9 pasos, un solo motor, 22 s) -> GUI en vivo con cuatro escenarios, cada uno con **Inspeccionar** y luego **Extraer y guardar**: 1) HTML estático + paginación (books.toscrape.com, requests, 2 páginas), 2) JavaScript (quotes.toscrape.com/js, Selenium con Chrome visible), 3) API JSON (quotes.toscrape.com/api, autorización confirmada), 4) CAPTCHA (nopecha.com/demo/recaptcha): INCIDENCIA naranja y la herramienta se detiene sin evadirlo; más una re-ejecución del escenario 1 (detección de cambios) -> VS Code con `datasets/multisitio/dataset_multisitio.csv` y la vista previa de `docs/evidencias/MATRIZ_ESCENARIOS.md` (si existen) -> cierre.

**Disposición:** se graba el área de trabajo del monitor principal sobre un fondo oscuro propio (sin escritorio ni barra de tareas). La GUI ocupa ~66 % a la izquierda (panel de progreso visible) y Chrome de Selenium se coloca a la derecha; la franja inferior queda libre para los subtítulos. Un rótulo ámbar en el encabezado indica el escenario.

```powershell
python video/grabar_demo_avance.py                      # graba y genera mp4, .srt y guion (~3 min de captura)
python video/grabar_demo_avance.py --ensayo             # mismos pasos, sin grabar
python video/grabar_demo_avance.py --solo-subtitulos    # rehace mp4/srt/guion desde la ultima grabacion
python video/grabar_demo_avance.py --solo-diapositivas  # solo dibuja video/_avance_*.png
```

No toque teclado ni mouse durante la grabación; se minimizan todas las ventanas al inicio y se restauran al final. Los datos de la GUI van a `video/demo_output_avance/` (ignorado por git). Peticiones pocas y con pausa de 2 s, solo a sitios de práctica o demos públicas.

---

# Versión anterior: demostración en vivo (`demo_en_vivo.mp4`)

El video previo es la **demostración en vivo** (`demo_en_vivo.mp4`, 3:16, 1920x1080, 30 fps, sin audio). Es una grabación real de la pantalla con portada y cierre.

- **Escuela y materia:** Tecnológico de Toluca, Técnicas de Adquisición de Datos.
- **Integrantes:** Nelson Noriega, Andrea Arroyo y Diego Salazar.
- **Narra:** Andrea Arroyo.

## Archivos

| Archivo | Contenido |
|---|---|
| `demo_en_vivo.mp4` | Video con subtítulos quemados |
| `demo_en_vivo_sin_subs.mp4` | Mismo video sin subtítulos (para editar con voz) |
| `demo_en_vivo.srt` | Subtítulos sincronizados con los tiempos reales de cada paso |
| `guion_demo_en_vivo.md` | Narración por paso con sus tiempos |
| `grabar_demo.py` | Script que graba la demo y genera todo lo anterior |
| `build_video.py`, `guion.md`, `subtitulos.srt` | Video de apoyo con diapositivas de arquitectura (no se versiona el mp4; se regenera) |

## Contenido de la demostración

1. **Portada:** escuela, materia, título del proyecto e integrantes.
2. **VS Code:** recorre `extractor.py` (`_acquire_selenium`), `app.py` (`run_job`) y `config.py` (`ScrapeConfig`).
3. **Pruebas:** ejecuta `pytest -v` en una terminal, donde se ven las 14 pruebas pasando.
4. **GUI:** abre la GUI Tkinter real, teclea la configuración de books.toscrape.com y pulsa **Inspeccionar** y luego **Extraer y guardar**. Selenium abre Chrome visible y recorre 3 páginas.
5. **Resultado:** abre en VS Code el CSV generado.
6. **Cierre:** "¡Gracias!" con los integrantes.

## Volver a grabar

```powershell
python video/grabar_demo.py                   # graba y genera ambos mp4, .srt y guion
python video/grabar_demo.py --ensayo          # mismos pasos, sin grabar
python video/grabar_demo.py --solo-subtitulos # rehace portada, cierre, subtítulos y mp4 desde la última grabación
```

- **Pantalla completa:** se graba todo lo que se vea, así que cierre las aplicaciones privadas y active *No molestar*. El script minimiza todas las ventanas al inicio y las restaura al final.
- **No tocar la PC:** no use el teclado ni el mouse durante la grabación (unos 3 minutos).
- **Datos editables:** los datos de la portada están en las constantes `INTEGRANTES`, `INSTITUCION` y `MATERIA` de `grabar_demo.py`. La narración está en `NARRACION`.
- **Pausa visual:** solo en la grabación, cada Chrome se desplaza unos 4 s antes de cerrarse para que se vean los libros. Los datos extraídos no cambian.

## Agregar la voz

1. Andrea graba siguiendo `guion_demo_en_vivo.md`.
2. Unir el audio con el video (ffmpeg incluido en `imageio_ffmpeg`, o uno propio):

```powershell
ffmpeg -i video/demo_en_vivo.mp4 -i voz.mp3 -c:v copy -c:a aac -shortest final.mp4
```

Para obtener la ruta del ffmpeg de Python:

```powershell
python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

Alternativa: importar `demo_en_vivo_sin_subs.mp4` y la voz en CapCut o Clipchamp. Ahí se pueden ajustar los tiempos y, si quieren, importar `demo_en_vivo.srt` como subtítulos editables.

## Video de apoyo (arquitectura)

`python video/build_video.py` regenera `demo_arquitectura.mp4` (unos 4:00, diapositivas con el diagrama de módulos, el dataset y la clasificación de sitios). No se versiona.
