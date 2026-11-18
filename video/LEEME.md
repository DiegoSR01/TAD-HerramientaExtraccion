# Video de demostración

El video que se entrega es la **demostración en vivo** (`demo_en_vivo.mp4`, 3:16, 1920x1080, 30 fps, sin audio). Es una grabación real de la pantalla con portada y cierre.

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
