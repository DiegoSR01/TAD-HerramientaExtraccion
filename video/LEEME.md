# Video de demostración: arquitectura ejecutada

Video de ~4 minutos (1920x1080, 30 fps, H.264) **sin audio**, con subtítulos quemados, para que añadan su voz.

## Archivos

| Archivo | Descripción |
|---|---|
| `demo_arquitectura.mp4` | Video con subtítulos quemados (sin audio) |
| `demo_arquitectura_sin_subs.mp4` | Mismo video sin subtítulos (para editar con voz) |
| `subtitulos.srt` | Subtítulos de la narración, sincronizados con el video |
| `guion.md` | Guion por escena: tiempos, qué se ve, texto de narración y quién narra (Andrea Arroyo) |
| `build_video.py` | Script que genera todo lo anterior |
| `preview/` | PNG de revisión (un fotograma por escena; se regenera, no se versiona) |

## Regenerar

Desde la raíz del proyecto (requiere Pillow, pandas e `imageio_ffmpeg`, ya instalados):

```powershell
python video/build_video.py            # genera guion.md, .srt, los dos mp4 y preview/ (tarda unos minutos)
python video/build_video.py --previews # solo guion.md, .srt y PNG de revisión (segundos)
```

Los datos del video se leen del proyecto (no hay cifras escritas a mano): `datasets/books_toscrape.csv`, `smart_scraper/extractor.py` (`_acquire_selenium`), `scripts/build_dataset.py`, la tabla de clasificación de `docs/INFORME_TECNICO.md` y `tests/test_pipeline.py`.

## Cambiar nombres, textos o duraciones

Todo sale de la lista `ESCENAS` al inicio de `build_video.py` (texto de narración, voz, descripción). Con ella el script recalcula las duraciones y regenera `guion.md`, `subtitulos.srt` y el video, así que siempre quedan sincronizados.

- **Integrantes y narradora:** constantes `INTEGRANTES` y `NARRADORA` en `build_video.py` (Nelson Noriega, Andrea Arroyo y Diego Salazar; narra Andrea Arroyo).
- **Ritmo de la voz:** `PALABRAS_POR_SEGUNDO` (por defecto 2,3). Si al grabar la voz sale más lenta, bajen el valor (por ejemplo 2,0) y se alargarán todas las escenas.
- **Una escena concreta:** añadir `dur=<segundos>` a esa escena en `ESCENAS`.
- Mantener el total entre 3:00 y 5:00 (el script imprime la duración al ejecutarse).

## Agregar la voz

1. Graben siguiendo `guion.md` (cada escena indica quién lee). Conviene grabar cada escena por separado o seguir los tiempos del guion; cada escena deja ~0,5 s de silencio al inicio.
2. Una el audio con el video (ffmpeg incluido en `imageio_ffmpeg`, o uno propio):

```powershell
ffmpeg -i video/demo_arquitectura.mp4 -i voz.mp3 -c:v copy -c:a aac -shortest final.mp4
```

Si prefieren no tener los subtítulos quemados, usen `demo_arquitectura_sin_subs.mp4` como entrada. Para obtener la ruta del ffmpeg de Python:

```powershell
python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
```

3. Alternativa: importar `demo_arquitectura_sin_subs.mp4` (y la voz) en CapCut o Clipchamp, ajustar tiempos y, si quieren, importar `subtitulos.srt` como subtítulos editables.

## Limitaciones

- Las escenas son imágenes fijas con fundidos de 0,4 s (sin animaciones internas).
- Los subtítulos reparten el texto proporcionalmente al número de caracteres; si la voz real se desvía, ajusten `PALABRAS_POR_SEGUNDO` o `dur` y regeneren.
- Las cifras de pruebas (14) se cuentan desde `tests/test_pipeline.py`; la afirmación "todas pasan" se verificó con `pytest` al generar el video, pero no se vuelve a ejecutar en cada regeneración.

## Demostración en vivo (VS Code + GUI + Selenium)

`grabar_demo.py` graba la pantalla real (ffmpeg gdigrab) mientras automatiza la demo, unos 3:00 en total:

1. Abre VS Code y muestra `extractor.py` (`_acquire_selenium`), `app.py` (`run_job`) y `config.py` (`ScrapeConfig`).
2. Ejecuta `pytest -v` en una terminal, donde se ven las 14 pruebas pasando.
3. Abre la GUI Tkinter real, teclea la configuración de books.toscrape.com y pulsa **Inspeccionar** y luego **Extraer y guardar**. Selenium abre Chrome visible y recorre 3 páginas.
4. Abre en VS Code el CSV generado.

| Archivo | Contenido |
|---|---|
| `demo_en_vivo.mp4` | Grabación con subtítulos quemados |
| `demo_en_vivo_sin_subs.mp4` | Grabación limpia (para editar con voz) |
| `demo_en_vivo.srt` | Subtítulos sincronizados con los tiempos reales de cada paso |
| `guion_demo_en_vivo.md` | Narración por paso con sus tiempos (narra Andrea Arroyo) |

Antes de volver a grabar con `python video/grabar_demo.py`:

- Cierre las aplicaciones privadas y active *No molestar*: se graba la pantalla completa.
- El script minimiza todas las ventanas al inicio y las restaura al final.
- No use el teclado ni el mouse durante la grabación.
- `--ensayo` ejecuta los mismos pasos sin grabar.

Por la pausa visual que se añade solo en la grabación, cada Chrome se desplaza unos 4 s antes de cerrarse. Así se ven los libros, y los datos extraídos no cambian.
