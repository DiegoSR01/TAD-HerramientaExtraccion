"""Genera el video de demostración (sin audio, con subtítulos quemados), el .srt y guion.md.

Uso:  python video/build_video.py            (genera todo)
      python video/build_video.py --previews (solo PNG de revisión, sin codificar video)

Fuente única de verdad: la lista ``ESCENAS`` (texto de narración, voz, descripción de
lo que se ve). A partir de ella se calculan las duraciones y se regeneran
``guion.md``, ``subtitulos.srt`` y los dos videos, de modo que todo queda sincronizado.

Datos reales: el CSV del dataset (datasets/books_toscrape.csv), el código de
``_acquire_selenium`` (smart_scraper/extractor.py), las reglas de campos de
scripts/build_dataset.py, la tabla de clasificación de docs/INFORME_TECNICO.md y el
número de pruebas de tests/test_pipeline.py. No se inventan cifras.

Ajustar duraciones: cambie ``PALABRAS_POR_SEGUNDO`` (ritmo de la voz) o añada
``dur=<segundos>`` a una escena para fijarla; vuelva a ejecutar el script.
Requiere solo Pillow, pandas e imageio_ffmpeg (ya instalados en el proyecto).
"""
from __future__ import annotations

import re
import subprocess
import sys
import textwrap
from functools import lru_cache
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
VIDEO = RAIZ / "video"
PREVIEW = VIDEO / "preview"
W, H = 1920, 1080
FPS = 30
FADE_S = 0.4
PALABRAS_POR_SEGUNDO = 2.3   # ritmo de narración
HOLGURA_S = 1.2              # silencio inicial/final por escena
MAX_CHARS_LINEA = 42
INICIO_SUB, FIN_SUB = 0.45, 0.25  # los subtítulos empiezan tras el fundido y terminan antes del corte

# ------------------------------------------------------------------ paleta y fuentes
BG = (11, 22, 48)
PANEL = (21, 37, 74)
PANEL2 = (30, 50, 96)
CYAN = (56, 189, 248)
AMBAR = (251, 191, 36)
VERDE = (74, 222, 128)
ROJO = (248, 113, 113)
TXT = (226, 232, 240)
MUTED = (148, 163, 184)
FUENTES = Path("C:/Windows/Fonts")


@lru_cache(maxsize=None)
def fuente(nombre: str, tam: int) -> ImageFont.FreeTypeFont:
    archivos = {"n": "segoeui.ttf", "b": "segoeuib.ttf", "m": "consola.ttf", "mb": "consolab.ttf"}
    return ImageFont.truetype(str(FUENTES / archivos[nombre]), tam)


# ------------------------------------------------------------------ datos reales
def cargar_datos() -> dict:
    df = pd.read_csv(RAIZ / "datasets" / "books_toscrape.csv", encoding="utf-8-sig")
    informe = (RAIZ / "docs" / "INFORME_TECNICO.md").read_text(encoding="utf-8")
    seccion = informe.split("### Tabla de clasificación", 1)[1].split("###", 1)[0]
    sitios = []
    for linea in seccion.splitlines():
        if linea.startswith("|") and not linea.startswith("|---") and not linea.startswith("| Sitio"):
            c = [x.strip() for x in linea.strip().strip("|").split("|")]
            sitios.append({
                "sitio": c[0],
                "proteccion": re.split(r" \(| tras ", c[1])[0],
                "tecnica": re.split(r" \(| para ", c[5])[0],
                "legal": c[6],
            })
    # sitios simulados de las pruebas (primera tabla del informe)
    esc = informe.split("## Escenarios cubiertos", 1)[1].split("Los adaptadores", 1)[0]
    simulados = re.findall(r"^\| `(/[^`]+)` \| ([^|]+) \|", esc, flags=re.M)
    tests = (RAIZ / "tests" / "test_pipeline.py").read_text(encoding="utf-8")
    n_tests = len(re.findall(r"^\s*(?:async )?def test_", tests, flags=re.M))
    extractor = (RAIZ / "smart_scraper" / "extractor.py").read_text(encoding="utf-8").splitlines()
    inicio = next(i for i, l in enumerate(extractor) if l.startswith("def _acquire_selenium"))
    fin = next(i for i in range(inicio + 1, len(extractor)) if extractor[i].startswith("def "))
    build = (RAIZ / "scripts" / "build_dataset.py").read_text(encoding="utf-8")
    campos = re.search(r'FIELDS = """\n(.*?)"""', build, flags=re.S).group(1).strip().splitlines()
    sel = RAIZ / "datasets"
    tam = {e: (sel / f"books_toscrape.{e}").stat().st_size // 1024 for e in ("csv", "sqlite", "xlsx")}
    return {
        "df": df, "sitios": sitios, "simulados": simulados, "n_tests": n_tests,
        "selenium": extractor[inicio:fin], "campos": campos, "tam_kb": tam,
        "precio_medio": float(df["precio_gbp"].mean()),
    }


D = cargar_datos()
_df = D["df"]
_PM = f"{D['precio_medio']:.2f}".replace(".", ",")
_N = len(_df)
_N_TESTS = D["n_tests"]

# ------------------------------------------------------------------ ESCENAS (fuente única)
# render: nombre de la función de dibujo; voz: quién lee; ver: texto para guion.md.
ESCENAS = [
    dict(id=1, titulo="Portada", voz="Voz 1", render="s_portada",
         ver="Título del proyecto, integrantes (placeholder) y los siete módulos como fichas.",
         texto="Hola, somos [Nombre 1] y [Nombre 2]. Presentamos la Herramienta de Extracción Web Inteligente del curso TAD y la arquitectura que ejecutamos de principio a fin."),
    dict(id=2, titulo="Problema y objetivo", voz="Voz 2", render="s_problema",
         ver="Dos tarjetas: el problema (sitios heterogéneos) y el objetivo (herramienta local, modular y responsable).",
         texto="Extraer datos de la web no es solo descargar páginas. Hay HTML estático, JavaScript, APIs, paginación y controles de acceso. Nuestro objetivo: una herramienta local, configurable y modular, que inspeccione el sitio y entregue datos limpios, trazables y obtenidos con responsabilidad."),
    dict(id=3, titulo="Arquitectura de siete módulos", voz="Voz 1", render="s_arquitectura",
         ver="Diagrama de cajas con flechas: Configuración → Inspección → Extracción (Requests, Selenium, Playwright, API) → Selección → Transformación → Almacenamiento → Monitoreo; app.py orquesta y gui.py es la interfaz.",
         texto="La solución tiene siete módulos. Configuración define URL, límites y selectores. Inspección diagnostica el sitio. El motor de extracción usa Requests, Selenium, Playwright o una API autorizada. Siguen selección, transformación y calidad, almacenamiento y monitoreo. app.py los orquesta y la interfaz Tkinter los expone."),
    dict(id=4, titulo="Flujo de ejecución", voz="Voz 2", render="s_flujo",
         ver="Lista de los pasos de run_job() y recuadros de 'se detiene si…' y 'siempre'.",
         texto="Así fluye run_job. Valida la configuración e inspecciona la página; si hay 401, 403, 429 o CAPTCHA, se detiene. Si no, adquiere, transforma, guarda, compara con la ejecución anterior y escribe un informe JSON, incluso cuando hay errores."),
    dict(id=5, titulo="Código real: Selenium", voz="Voz 1", render="s_selenium",
         ver="Fragmento real de _acquire_selenium con resaltado de sintaxis y siete pasos señalados.",
         texto="Este es código real del método Selenium. Se configura Chrome headless, se abre la URL y WebDriverWait espera a que el documento cargue. Antes de interactuar se revisa CAPTCHA o login. Luego hay clics acotados en cargar más y desplazamientos limitados. Y en finally, driver.quit siempre cierra el navegador."),
    dict(id=6, titulo="Selección CSS / JSON", voz="Voz 2", render="s_seleccion",
         ver="HTML de una tarjeta de libro, reglas nombre=selector reales del dataset, ejemplo de ruta JSON y registro resultante.",
         texto="La selección convierte HTML en campos. Un selector de elemento repetido y reglas nombre igual selector, como titulo igual h3 a dos puntos title, leen texto o atributos. El asterisco marca un campo requerido. En APIs se usan rutas JSON con puntos."),
    dict(id=7, titulo="Transformación y linaje", voz="Voz 1", render="s_transformacion",
         ver="Limpiezas aplicadas (antes → después) y una fila de linaje con sus campos.",
         texto="La transformación recorta espacios, elimina duplicados y valida campos requeridos. Cada valor genera una fila de linaje con ejecución, URL de origen, método, fecha, estado de validación y transformaciones. Así cada dato se rastrea hasta su origen."),
    dict(id=8, titulo="Almacenamiento", voz="Voz 2", render="s_almacenamiento",
         ver="Tarjetas SQLite, CSV, Excel y JSON con tamaños reales de los archivos; extras PostgreSQL/MongoDB.",
         texto="El almacenamiento exporta a CSV, Excel, JSON y SQLite; PostgreSQL y MongoDB son opcionales. En SQLite guardamos la tabla de libros y la de linaje. También se guarda el perfil del sitio y se compara cada corrida con la anterior para detectar cambios."),
    dict(id=9, titulo="Demo: dataset real", voz="Voz 1", render="s_demo",
         ver="Tabla con filas reales del CSV, estadísticas y barras con la distribución de ratings.",
         texto=f"Para la demostración usamos books.toscrape.com, un sandbox hecho para practicar scraping. La herramienta recorrió cinco páginas y obtuvo {_N} libros sin duplicados. Vemos filas reales, un precio medio de {_PM} libras y la distribución de valoraciones."),
    dict(id=10, titulo="Clasificación de sitios", voz="Voz 2", render="s_sitios",
         ver="Tabla de los 7 sitios del informe con protección observada y viabilidad legal (verde / ámbar / rojo).",
         texto="También clasificamos siete sitios por protección y viabilidad legal. Los dos sandboxes son viables. INEGI, Banco Mundial, data.gov y el DOF son viables con condiciones. datos.gob.mx devolvió 403 y no es viable sin autorización: se usaría su API oficial. Es una evaluación técnica, no asesoría legal."),
    dict(id=11, titulo="Seguridad y uso responsable", voz="Voz 1", render="s_seguridad",
         ver="Dos columnas: lo que detiene la ejecución (rojo) y los límites que se respetan (verde).",
         texto="La herramienta es conservadora. Se detiene ante CAPTCHA, formularios de autenticación y respuestas 401, 403 o 429, y no intenta evadirlos. Solo sigue paginación del mismo host, limita páginas, registros y tamaño del DOM, y espera entre solicitudes."),
    dict(id=12, titulo="Pruebas automatizadas", voz="Voz 2", render="s_pruebas",
         ver=f"Contador de {_N_TESTS} pruebas y la lista de sitios simulados.",
         texto=f"Las {_N_TESTS} pruebas automatizadas pasan. Usan un servidor local con sitios simulados: estático, dinámico, carga bajo demanda, API, paginación, tabla, autenticación y CAPTCHA. Selenium y Playwright se prueban con adaptadores simulados, sin tocar sitios públicos."),
    dict(id=13, titulo="Conclusiones y cierre", voz="Voz 1 y Voz 2", render="s_cierre",
         ver="Cuatro conclusiones, agradecimiento e integrantes (placeholder).",
         texto=f"En resumen: siete módulos que inspeccionan, extraen, limpian, almacenan y monitorean con trazabilidad, validados con un dataset real de {_N} libros. El siguiente paso es probar sitios reales solo con autorización, priorizando APIs oficiales. Gracias por su atención."),
]
for e in ESCENAS:
    e["palabras"] = len(e["texto"].split())
    e.setdefault("dur", round(e["palabras"] / PALABRAS_POR_SEGUNDO + HOLGURA_S, 1))
_t = 0.0
for e in ESCENAS:
    e["ini"], e["fin"] = _t, _t + e["dur"]
    _t = e["fin"]
DURACION = _t


# ------------------------------------------------------------------ primitivas de dibujo
def lienzo(num: int, titulo: str, sub: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 8), fill=CYAN)
    d.text((70, 40), titulo, font=fuente("b", 62), fill=TXT)
    if sub:
        d.text((72, 118), sub, font=fuente("n", 28), fill=MUTED)
    d.text((W - 70, 52), f"Escena {num:02d}/{len(ESCENAS):02d}", font=fuente("n", 24), fill=MUTED, anchor="ra")
    return img, d


def caja(d, xy, fill=PANEL, borde=None, r=18, w=3):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=borde, width=w)


def ajustar(texto: str, f, ancho: int) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if f.getlength(prueba) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    return lineas + [actual]


def parrafo(d, x, y, texto, f, color=TXT, ancho=600, interlineado=1.3) -> int:
    for l in ajustar(texto, f, ancho):
        d.text((x, y), l, font=f, fill=color)
        y += int(f.size * interlineado)
    return y


def flecha(d, x1, y1, x2, y2, color=CYAN, w=5, punta=14):
    d.line((x1, y1, x2, y2), fill=color, width=w)
    if abs(x2 - x1) >= abs(y2 - y1):
        s = 1 if x2 > x1 else -1
        d.polygon([(x2, y2), (x2 - s * punta, y2 - punta * .7), (x2 - s * punta, y2 + punta * .7)], fill=color)
    else:
        s = 1 if y2 > y1 else -1
        d.polygon([(x2, y2), (x2 - punta * .7, y2 - s * punta), (x2 + punta * .7, y2 - s * punta)], fill=color)


def circulo_num(d, cx, cy, n, color=CYAN, r=26):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    d.text((cx, cy), str(n), font=fuente("b", int(r * 1.15)), fill=BG, anchor="mm")


def pastilla(d, x, y, texto, color, f=None, relleno=True):
    f = f or fuente("b", 26)
    w = int(f.getlength(texto)) + 36
    d.rounded_rectangle((x, y, x + w, y + 46), radius=23, fill=color if relleno else None, outline=color, width=3)
    d.text((x + w / 2, y + 23), texto, font=f, fill=BG if relleno else color, anchor="mm")
    return w


MODULOS = [
    ("Configuración", "config.py"), ("Inspección y diagnóstico", "inspector.py"),
    ("Motor de extracción", "extractor.py"), ("Selección de información", "selection.py"),
    ("Transformación y calidad", "transform.py"), ("Almacenamiento", "storage.py"), ("Monitoreo", "monitoring.py"),
]


# ------------------------------------------------------------------ escenas
def s_portada(n):
    img, d = lienzo(n, "")
    d.text((W / 2, 300), "Herramienta de Extracción Web", font=fuente("b", 100), fill=TXT, anchor="mm")
    d.text((W / 2, 420), "Inteligente – TAD", font=fuente("b", 100), fill=CYAN, anchor="mm")
    d.text((W / 2, 540), "Video de demostración: arquitectura ejecutada", font=fuente("n", 40), fill=MUTED, anchor="mm")
    d.text((W / 2, 640), "[Nombre 1]  ·  [Nombre 2]", font=fuente("b", 46), fill=AMBAR, anchor="mm")
    etiquetas = [f"{i} {m[0].split()[0]}" for i, m in enumerate(MODULOS, 1)]
    f = fuente("b", 26)
    ancho_total = sum(int(f.getlength(t)) + 36 + 20 for t in etiquetas) - 20
    x = (W - ancho_total) // 2
    for t in etiquetas:
        x += pastilla(d, x, 780, t, CYAN, relleno=False) + 20
    d.text((W / 2, 880), "Python · Requests · BeautifulSoup · Selenium · Playwright · API · Pandas", font=fuente("n", 28), fill=MUTED, anchor="mm")
    return img


def s_problema(n):
    img, d = lienzo(n, "Problema y objetivo", "Por qué una herramienta modular")
    caja(d, (70, 190, 930, 860), PANEL, ROJO)
    d.text((110, 220), "El problema", font=fuente("b", 46), fill=ROJO)
    y = 310
    for t_ in ["HTML estático, y también contenido que se carga con JavaScript",
               "Datos que viven en APIs, no en el HTML",
               "Paginación, botones «cargar más» y scroll infinito",
               "Controles de acceso: CAPTCHA, login, 403, 429",
               "Resultados sin trazabilidad ni calidad garantizada"]:
        d.ellipse((112, y + 14, 126, y + 28), fill=ROJO)
        y = parrafo(d, 150, y, t_, fuente("n", 34), ancho=740) + 20
    caja(d, (990, 190, 1850, 860), PANEL, VERDE)
    d.text((1030, 220), "El objetivo", font=fuente("b", 46), fill=VERDE)
    y = 310
    for t_ in ["Aplicación local, configurable y modular (7 módulos)",
               "Inspeccionar el sitio y elegir el método de adquisición",
               "Seleccionar, limpiar y validar los datos",
               "Guardar en CSV, Excel, JSON o SQLite con linaje por campo",
               "Respetar límites: detenerse ante restricciones, sin evadirlas"]:
        d.ellipse((1032, y + 14, 1046, y + 28), fill=VERDE)
        y = parrafo(d, 1070, y, t_, fuente("n", 34), ancho=740) + 20
    return img


def s_arquitectura(n):
    img, d = lienzo(n, "Arquitectura: siete módulos", "smart_scraper/ · cada módulo con una responsabilidad")
    bw, bh, gap, x0, y0 = 232, 190, 36, 40, 250
    centros = []
    for i, (nombre, arch) in enumerate(MODULOS):
        x = x0 + i * (bw + gap)
        destaca = i == 2
        caja(d, (x, y0, x + bw, y0 + bh), PANEL2 if destaca else PANEL, AMBAR if destaca else CYAN)
        circulo_num(d, x + 34, y0 + 36, i + 1, AMBAR if destaca else CYAN, 22)
        yy = y0 + 70
        for l in ajustar(nombre, fuente("b", 26), bw - 24):
            d.text((x + 12, yy), l, font=fuente("b", 26), fill=TXT)
            yy += 33
        d.text((x + 15, y0 + bh - 38), arch, font=fuente("m", 21), fill=MUTED)
        centros.append(x + bw // 2)
        if i < 6:
            flecha(d, x + bw + 3, y0 + bh // 2, x + bw + gap - 3, y0 + bh // 2, w=4, punta=11)
    for i, c in enumerate(centros):
        if i != 2:
            d.line((c, y0 + bh + 6, c, 650), fill=(70, 110, 170), width=2)
    yb = 650
    caja(d, (40, yb, 1880, yb + 90), PANEL2, CYAN, 14)
    d.text((W / 2, yb + 45), "app.py  ·  run_job()  orquesta los siete módulos", font=fuente("b", 36), fill=CYAN, anchor="mm")
    cx = centros[2]
    d.line((cx, y0 + bh, cx, y0 + bh + 30), fill=AMBAR, width=3)
    chips = ["Requests", "Selenium", "Playwright", "API"]
    anchos = [int(fuente("b", 25).getlength(c)) + 34 for c in chips]
    x = cx - (sum(anchos) + 12 * 3) // 2
    for c, a in zip(chips, anchos):
        d.rounded_rectangle((x, y0 + bh + 30, x + a, y0 + bh + 78), radius=14, fill=PANEL, outline=AMBAR, width=3)
        d.text((x + a / 2, y0 + bh + 54), c, font=fuente("b", 25), fill=AMBAR, anchor="mm")
        x += a + 12
    caja(d, (660, 790, 1260, 870), PANEL, VERDE, 14)
    d.text((960, 830), "gui.py  ·  Interfaz Tkinter", font=fuente("b", 32), fill=VERDE, anchor="mm")
    flecha(d, 960, 788, 960, yb + 94, VERDE, 4, 12)
    return img


def s_flujo(n):
    img, d = lienzo(n, "Flujo de ejecución", "app.run_job(config, salida, formato)")
    pasos = [("Validar configuración", "config.validate(): URL http/https, límites"),
             ("Inspeccionar la página", "diagnose_config(): señales JS, API, CAPTCHA, login"),
             ("Revisar restricciones", "page.report.blocked → AccessRestrictionError"),
             ("Adquirir y paginar", "scrape(): solo mismo host, max_pages, pausa"),
             ("Transformar y validar", "transform_records(): limpieza + linaje"),
             ("Guardar resultados y perfil", "save_results() + save_profile()"),
             ("Comparar y reportar", "compare_and_store_snapshot() + report-*.json")]
    y = 180
    for i, (a, b) in enumerate(pasos, 1):
        col = CYAN if i != 3 else ROJO
        caja(d, (70, y, 1120, y + 90), PANEL, col, 14)
        circulo_num(d, 120, y + 45, i, col, 26)
        d.text((170, y + 8), a, font=fuente("b", 33), fill=TXT)
        d.text((170, y + 52), b, font=fuente("m", 22), fill=MUTED)
        if i < 7:
            flecha(d, 120, y + 92, 120, y + 106, CYAN, 3, 8)
        y += 104
    caja(d, (1180, 190, 1850, 560), PANEL, ROJO)
    d.text((1215, 215), "Se detiene si…", font=fuente("b", 40), fill=ROJO)
    yy = 285
    for t_ in ["HTTP 401, 403 o 429", "CAPTCHA o challenge", "Formulario de autenticación", "La paginación apunta a otro host"]:
        d.ellipse((1217, yy + 12, 1231, yy + 26), fill=ROJO)
        d.text((1250, yy), t_, font=fuente("n", 32), fill=TXT)
        yy += 62
    caja(d, (1180, 600, 1850, 870), PANEL, VERDE)
    d.text((1215, 625), "Siempre, aun con error", font=fuente("b", 40), fill=VERDE)
    yy = 695
    for t_ in ["Registro en el log", "Informe JSON de la corrida", "RunFailure con el informe"]:
        d.ellipse((1217, yy + 12, 1231, yy + 26), fill=VERDE)
        d.text((1250, yy), t_, font=fuente("n", 32), fill=TXT)
        yy += 55
    return img


# --- resaltado de sintaxis simple
KW = {"for", "in", "try", "finally", "if", "not", "break", "lambda", "return", "import", "from", "as", "def", "else"}


def pintar_codigo(d, x, y, linea: str, f):
    for tok in re.findall(r'"[^"]*"|\w+|\s+|[^\w\s]', linea):
        if tok.startswith('"'):
            col = VERDE
        elif tok in KW:
            col = (244, 114, 182)
        elif tok in {"driver", "webdriver", "WebDriverWait", "options", "config", "buttons", "browser"}:
            col = CYAN
        elif tok.isdigit():
            col = AMBAR
        else:
            col = TXT
        d.text((x, y), tok, font=f, fill=col)
        x += f.getlength(tok)


GRUPOS_SELENIUM = [
    ("1 Configurar Chrome", CYAN, ["options = webdriver.ChromeOptions()", "if config.headless:", 'options.add_argument("--headless=new")', "driver = webdriver.Chrome(options=options)"]),
    ("2 Navegar", VERDE, ["try:", "driver.set_page_load_timeout(config.timeout_seconds)", "driver.get(config.url)"]),
    ("3 Espera explícita", AMBAR, ["WebDriverWait(driver, config.timeout_seconds).until(", 'lambda browser: browser.execute_script("return document.readyState") in {"interactive", "complete"}', ")"]),
    ("4 Seguridad", ROJO, ["_check_browser_page(config.url, driver.page_source)"]),
    ("5 Cargar más (acotado)", CYAN, ["for _ in range(config.load_more_clicks):", 'buttons = driver.find_elements("css selector", config.load_more_selector)', "if not buttons:", "break", "buttons[0].click()"]),
    ("6 Scroll (acotado)", VERDE, ["for _ in range(config.scroll_steps):", 'driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")', "html = driver.page_source", "return html"]),
    ("7 Cierre garantizado", ROJO, ["finally:", "driver.quit()"]),
]


def s_selenium(n):
    img, d = lienzo(n, "Código real: _acquire_selenium", "smart_scraper/extractor.py · extracto (se omiten comentarios y validaciones menores)")
    fuente_cod = D["selenium"]
    seleccion, pos = [], 0
    for _, col, claves in GRUPOS_SELENIUM:
        for clave in claves:
            j = next((k for k in range(pos, len(fuente_cod)) if fuente_cod[k].strip() == clave), None)
            if j is None:
                raise RuntimeError(f"No se encontró en extractor.py la línea: {clave}")
            pos = j + 1
            seleccion.append((fuente_cod[j][4:].rstrip(), col))
    f = fuente("m", 21)
    lh = 31
    top = 190
    caja(d, (40, top - 12, 1400, top + lh * len(seleccion) + 14), (8, 16, 36), (60, 90, 150), 14, 2)
    y = top
    for texto, col in seleccion:
        if f.getlength(texto) > 1300:
            raise RuntimeError("Línea de código demasiado ancha")
        d.rectangle((52, y + 2, 58, y + lh - 4), fill=col)
        pintar_codigo(d, 72, y, texto, f)
        y += lh
    y = 190
    for nombre, col, _ in GRUPOS_SELENIUM:
        caja(d, (1430, y, 1880, y + 62), PANEL, col, 12, 3)
        d.rectangle((1430, y + 10, 1438, y + 52), fill=col)
        d.text((1458, y + 31), nombre, font=fuente("b", 27), fill=TXT, anchor="lm")
        y += 78
    d.text((1430, y + 4), "Mismos pasos en Playwright\n(_acquire_playwright).", font=fuente("n", 22), fill=MUTED, spacing=6)
    return img


def s_seleccion(n):
    img, d = lienzo(n, "Selección de información", "selection.py · selectores CSS para HTML y rutas con puntos para JSON")
    fila = _df.iloc[0]
    caja(d, (60, 190, 940, 520), (8, 16, 36), CYAN, 14)
    d.text((90, 205), "HTML de una tarjeta (simplificado)", font=fuente("b", 26), fill=CYAN)
    html = ['<article class="product_pod">',
            '  <h3><a href="…_1000/index.html"',
            f'     title="{fila["titulo"]}">…</a></h3>',
            '  <p class="star-rating Three">…</p>',
            f'  <p class="price_color">£{fila["precio_gbp"]}</p>',
            '  <p class="instock availability">In stock</p>',
            '</article>']
    for i, l in enumerate(html):
        d.text((90, 255 + i * 35), l, font=fuente("m", 23), fill=TXT)
    caja(d, (990, 190, 1860, 520), (8, 16, 36), AMBAR, 14)
    d.text((1020, 205), "Reglas  nombre=selector  (build_dataset.py)", font=fuente("b", 26), fill=AMBAR)
    d.text((1020, 255), 'item_selector = "article.product_pod"', font=fuente("m", 23), fill=VERDE)
    for i, l in enumerate(D["campos"]):
        d.text((1020, 300 + i * 34), l, font=fuente("m", 25), fill=TXT)
    d.text((1020, 300 + 5 * 34 + 8), "*  campo requerido      ::title  atributo", font=fuente("n", 22), fill=MUTED)
    flecha(d, 500, 530, 500, 585, CYAN, 5, 14)
    flecha(d, 1425, 530, 1425, 585, AMBAR, 5, 14)
    caja(d, (60, 595, 940, 860), PANEL, VERDE)
    d.text((90, 610), "Registro seleccionado (fila 1 del dataset real)", font=fuente("b", 26), fill=VERDE)
    reg = [f'titulo  = "{fila["titulo"]}"', f'precio  = "£{fila["precio_gbp"]}"', 'rating  = "Three"  →  3',
           'disponibilidad = "In stock"', 'url     = …/a-light-in-the-attic_1000/…']
    for i, l in enumerate(reg):
        d.text((90, 662 + i * 38), l, font=fuente("m", 24), fill=TXT)
    caja(d, (990, 595, 1860, 860), PANEL, CYAN)
    d.text((1020, 610), "API autorizada: rutas JSON separadas por puntos", font=fuente("b", 26), fill=CYAN)
    api = ['json_records_path = "items"', 'name  = product.name', 'price = product.price', '', '→ {"name": …, "price": …}  por registro']
    for i, l in enumerate(api):
        d.text((1020, 662 + i * 38), l, font=fuente("m", 24), fill=TXT)
    return img


def s_transformacion(n):
    img, d = lienzo(n, "Transformación, calidad y linaje", "transform.py · transform_records()")
    x = 70
    for t_ in ["trim_whitespace", "collapse_whitespace", "deduplicate_record", "required_field_validation"]:
        x += pastilla(d, x, 190, t_, CYAN, fuente("m", 24), relleno=False) + 18
    caja(d, (60, 270, 940, 860), PANEL, AMBAR)
    d.text((90, 285), "Limpieza del dataset: antes → después", font=fuente("b", 30), fill=AMBAR)
    pares = [("precio  \"Â£51.77\"", "precio_gbp = 51.77"), ("rating  ['star-rating','Three']", "rating = 3"),
             ("disponibilidad  \"In stock\"", "en_stock = True"), ("href relativo", "url absoluta"),
             ("filas repetidas", "deduplicadas por url"), ("sin título/precio/url", "descartadas")]
    y = 350
    for a, b in pares:
        d.text((90, y), a, font=fuente("m", 26), fill=MUTED)
        d.text((90, y + 34), "→  " + b, font=fuente("mb", 26), fill=VERDE)
        y += 82
    fila = _df.iloc[0]
    caja(d, (990, 270, 1860, 860), (8, 16, 36), CYAN, 14)
    d.text((1020, 285), "Una fila de linaje por cada valor", font=fuente("b", 30), fill=CYAN)
    lin = ['{', '  "execution_id": "…",', '  "record_index": 0,', '  "source_url": "https://books.toscrape.com/",',
           '  "acquired_at": "2026-11-09…",', '  "method": "requests",', '  "field": "titulo",',
           f'  "value": "{fila["titulo"]}",', '  "validation_status": "valid",',
           '  "transformations": ["trim_whitespace",', '     "collapse_whitespace",', '     "deduplicate_record"]', '}']
    for i, l in enumerate(lin):
        pintar_codigo(d, 1020, 345 + i * 36, l, fuente("m", 23))
    return img


def s_almacenamiento(n):
    img, d = lienzo(n, "Almacenamiento", "storage.py · save_results() + historial de corridas")
    tam = D["tam_kb"]
    cartas = [("SQLite", f"books_toscrape.sqlite · {tam['sqlite']} KB", "tablas books (tipada) y lineage", CYAN),
              ("CSV", f"books_toscrape.csv · {tam['csv']} KB", "tabla books, UTF-8", VERDE),
              ("Excel", f"books_toscrape.xlsx · {tam['xlsx']} KB", "hojas books y lineage", AMBAR),
              ("JSON", "formato nativo de la herramienta", "registros y linaje", (192, 132, 252))]
    for i, (a, b, c, col) in enumerate(cartas):
        x = 60 + i * 450
        caja(d, (x, 200, x + 420, 520), PANEL, col)
        d.text((x + 28, 225), a, font=fuente("b", 52), fill=col)
        parrafo(d, x + 28, 310, b, fuente("m", 21), TXT, 370)
        parrafo(d, x + 28, 400, c, fuente("n", 28), MUTED, 370)
    caja(d, (60, 570, 1860, 700), PANEL, (70, 110, 170))
    d.text((90, 590), "Opcionales", font=fuente("b", 30), fill=TXT)
    d.text((90, 640), "PostgreSQL (SCRAPER_POSTGRES_DSN) y MongoDB (SCRAPER_MONGODB_URI): las cadenas de conexión nunca van en el código ni en perfiles.", font=fuente("n", 25), fill=MUTED)
    caja(d, (60, 740, 1860, 870), PANEL, (70, 110, 170))
    d.text((90, 758), "Junto a los datos, cada corrida deja", font=fuente("b", 30), fill=TXT)
    x = 90
    for t_ in ["profiles/ (perfil del sitio)", "report-<id>.json", "smart_scraper.log", "historial para comparar corridas"]:
        x += pastilla(d, x, 808, t_, CYAN, fuente("n", 24), relleno=False) + 16
    return img


def estrellas(d, x, y, v):
    for i in range(5):
        cx = x + i * 26 + 10
        d.ellipse((cx - 9, y - 9, cx + 9, y + 9), fill=AMBAR if i < v else None, outline=AMBAR, width=2)


def s_demo(n):
    img, d = lienzo(n, "Demo: dataset real de books.toscrape.com", f"datasets/books_toscrape.csv · {_N} filas · método {_df['metodo'].iloc[0]}")
    cols = [("id", 60), ("titulo", 140), ("precio £", 660), ("stock", 790), ("rating", 900)]
    caja(d, (60, 190, 1090, 810), PANEL, CYAN)
    for nom, x in cols:
        d.text((x + 15, 205), nom, font=fuente("b", 26), fill=CYAN)
    d.line((75, 250, 1075, 250), fill=CYAN, width=2)
    for i, r in enumerate(_df.head(8).itertuples()):
        y = 268 + i * 66
        if i % 2 == 0:
            d.rectangle((70, y - 8, 1080, y + 54), fill=PANEL2)
        titulo = str(r.titulo)
        corte = titulo
        while fuente("n", 27).getlength(corte) > 495:
            corte = corte[:-2]
        if corte != titulo:
            corte = corte.rstrip() + "…"
        d.text((75, y + 23), str(r.id), font=fuente("m", 25), fill=MUTED, anchor="lm")
        d.text((155, y + 23), corte, font=fuente("n", 27), fill=TXT, anchor="lm")
        d.text((675, y + 23), f"{r.precio_gbp:.2f}", font=fuente("m", 25), fill=TXT, anchor="lm")
        d.text((805, y + 23), "sí" if r.en_stock else "no", font=fuente("n", 26), fill=VERDE if r.en_stock else ROJO, anchor="lm")
        estrellas(d, 915, y + 23, int(r.rating))
    d.text((70, 822), "Primeras 8 filas reales del CSV", font=fuente("n", 22), fill=MUTED)
    stats = [("Filas", f"{_N}", CYAN), ("Precio medio", f"£{D['precio_medio']:.2f}", AMBAR),
             ("Rango", f"£{_df.precio_gbp.min():.2f}–{_df.precio_gbp.max():.2f}", VERDE), ("En stock", f"{int(_df.en_stock.sum())}", VERDE)]
    for i, (a, b, col) in enumerate(stats):
        x, y = 1130 + (i % 2) * 380, 190 + (i // 2) * 135
        caja(d, (x, y, x + 355, y + 115), PANEL, col)
        d.text((x + 20, y + 12), a, font=fuente("n", 24), fill=MUTED)
        d.text((x + 20, y + 48), b, font=fuente("b", 38), fill=col)
    caja(d, (1130, 470, 1860, 810), PANEL, CYAN)
    d.text((1160, 485), "Distribución de rating", font=fuente("b", 28), fill=TXT)
    cuentas = _df.rating.value_counts().to_dict()
    mx = max(cuentas.values())
    for i, v in enumerate(range(5, 0, -1)):
        y = 545 + i * 50
        c = int(cuentas.get(v, 0))
        largo = max(6, int(440 * c / mx))
        d.text((1160, y + 4), f"{v}", font=fuente("b", 26), fill=AMBAR)
        d.rounded_rectangle((1200, y, 1200 + largo, y + 36), radius=8, fill=CYAN)
        d.text((1200 + largo + 12, y + 3), str(c), font=fuente("b", 26), fill=TXT)
    return img


COLOR_LEGAL = {"Viable": VERDE, "Viable con condiciones": AMBAR, "No viable sin autorización": ROJO}


def s_sitios(n):
    img, d = lienzo(n, "Clasificación de siete sitios", "docs/INFORME_TECNICO.md · protección observada y viabilidad legal (preliminar)")
    for nom, x in (("Sitio", 78), ("Protección observada", 540), ("Viabilidad técnica", 1110), ("Viabilidad legal", 1430)):
        d.text((x, 190), nom, font=fuente("b", 28), fill=CYAN)
    d.line((60, 235, 1860, 235), fill=CYAN, width=2)
    for i, s in enumerate(D["sitios"]):
        y = 252 + i * 84
        caja(d, (60, y, 1860, y + 72), PANEL, None, 12)
        d.text((78, y + 36), s["sitio"], font=fuente("b", 28), fill=TXT, anchor="lm")
        for txt, x, wmax in ((s["proteccion"], 540, 560), (s["tecnica"], 1110, 300)):
            corte = txt
            while fuente("n", 27).getlength(corte) > wmax - 15:
                corte = corte[:-2]
            d.text((x, y + 36), corte + ("…" if corte != txt else ""), font=fuente("n", 27), fill=TXT, anchor="lm")
        pastilla(d, 1430, y + 13, s["legal"], COLOR_LEGAL.get(s["legal"], MUTED), fuente("b", 25))
    d.text((70, 870), "Evaluación técnica preliminar; no constituye asesoría legal. En sitios reales se prefiere la API o descarga oficial.", font=fuente("n", 24), fill=MUTED)
    return img


def s_seguridad(n):
    img, d = lienzo(n, "Seguridad y uso responsable", "La herramienta se detiene; nunca evade ni resuelve controles de acceso")
    caja(d, (60, 190, 940, 860), PANEL, ROJO)
    d.text((95, 215), "Se detiene (AccessRestrictionError)", font=fuente("b", 36), fill=ROJO)
    items = [("CAPTCHA / challenge", "«no se intentará resolver»"), ("Formulario de autenticación", "se detuvo el navegador"),
             ("HTTP 401, 403 o 429", "sin reintentos ni evasión"), ("Enlace a otro host", "la paginación solo sigue el mismo host")]
    for i, (a, b) in enumerate(items):
        y = 295 + i * 135
        caja(d, (95, y, 905, y + 112), PANEL2, None, 12)
        d.text((125, y + 14), a, font=fuente("b", 33), fill=TXT)
        d.text((125, y + 62), b, font=fuente("n", 26), fill=MUTED)
    caja(d, (990, 190, 1860, 860), PANEL, VERDE)
    d.text((1025, 215), "Límites que se respetan", font=fuente("b", 36), fill=VERDE)
    items = [("max_pages ≤ 10 · max_records", "alcance acotado por corrida"), ("delay_seconds entre páginas", "pausa cortés al servidor"),
             ("MAX_HTML_BYTES", "tope de tamaño del HTML/DOM"), ("API solo con autorización", "confirmación explícita del usuario")]
    for i, (a, b) in enumerate(items):
        y = 295 + i * 135
        caja(d, (1025, y, 1825, y + 112), PANEL2, None, 12)
        d.text((1055, y + 14), a, font=fuente("b", 31), fill=TXT)
        d.text((1055, y + 62), b, font=fuente("n", 26), fill=MUTED)
    return img


def s_pruebas(n):
    img, d = lienzo(n, "Pruebas automatizadas", "tests/test_pipeline.py · servidor HTTP local efímero con sitios simulados")
    caja(d, (60, 190, 700, 860), PANEL, VERDE)
    d.text((380, 420), f"{_N_TESTS}", font=fuente("b", 260), fill=VERDE, anchor="mm")
    d.text((380, 600), "pruebas, todas pasan", font=fuente("b", 38), fill=TXT, anchor="mm")
    d.text((380, 665), "pytest", font=fuente("m", 34), fill=MUTED, anchor="mm")
    d.text((380, 780), "Sin contactar sitios públicos", font=fuente("n", 28), fill=MUTED, anchor="mm")
    caja(d, (740, 190, 1860, 860), PANEL, CYAN)
    d.text((775, 212), "Sitios simulados y qué comprueban", font=fuente("b", 32), fill=CYAN)
    for i, (ruta, esc) in enumerate(D["simulados"][:10]):
        y = 275 + i * 57
        d.text((775, y), ruta, font=fuente("mb", 25), fill=AMBAR)
        d.text((1075, y - 1), esc.strip(), font=fuente("n", 27), fill=TXT)
    return img


def s_cierre(n):
    img, d = lienzo(n, "Conclusiones", "")
    pts = [("Arquitectura modular de siete módulos", "inspección, extracción, selección, calidad, almacenamiento y monitoreo", CYAN),
           ("Cuatro vías de adquisición", "Requests, Selenium, Playwright y API autorizada", AMBAR),
           ("Validada con datos reales", f"{_N} libros de books.toscrape.com en SQLite, CSV y Excel, con linaje", VERDE),
           ("Uso responsable por diseño", "se detiene ante restricciones; APIs oficiales y permiso antes de sitios reales", ROJO)]
    for i, (a, b, col) in enumerate(pts):
        y = 190 + i * 150
        caja(d, (70, y, 1850, y + 126), PANEL, col)
        circulo_num(d, 130, y + 63, i + 1, col, 30)
        d.text((190, y + 18), a, font=fuente("b", 40), fill=TXT)
        d.text((190, y + 74), b, font=fuente("n", 28), fill=MUTED)
    d.text((W / 2, 810), "Gracias por su atención", font=fuente("b", 52), fill=CYAN, anchor="mm")
    d.text((W / 2, 862), "[Nombre 1]  ·  [Nombre 2]", font=fuente("n", 30), fill=AMBAR, anchor="mm")
    return img


# ------------------------------------------------------------------ subtítulos
def bloques_subtitulo(texto: str) -> list[str]:
    lineas = textwrap.wrap(texto, MAX_CHARS_LINEA, break_long_words=False)
    return ["\n".join(lineas[i:i + 2]) for i in range(0, len(lineas), 2)]


def planificar_subtitulos() -> list[tuple[float, float, str]]:
    salida = []
    for e in ESCENAS:
        bl = bloques_subtitulo(e["texto"])
        ini, fin = e["ini"] + INICIO_SUB, e["fin"] - FIN_SUB
        total = sum(len(b.replace("\n", " ")) for b in bl)
        t = ini
        for b in bl:
            dur = (fin - ini) * len(b.replace("\n", " ")) / total
            salida.append((t, t + dur, b))
            t += dur
    return salida


def fmt_srt(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def mmss(s: float) -> str:
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def escribir_srt(subs):
    texto = "".join(f"{i}\n{fmt_srt(a)} --> {fmt_srt(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(subs, 1))
    (VIDEO / "subtitulos.srt").write_text(texto, encoding="utf-8")


def escribir_guion():
    pal = sum(e["palabras"] for e in ESCENAS)
    L = ["# Guion del video de demostración (arquitectura ejecutada)", "",
         "*Generado por `video/build_video.py` a partir de la lista `ESCENAS`; no editar a mano: edite el script y vuelva a ejecutarlo.*", "",
         f"- Duración total: **{mmss(DURACION)} ({DURACION:.0f} s)** · {pal} palabras de narración · ritmo base {PALABRAS_POR_SEGUNDO} palabras/s.",
         "- Cada escena deja ~0,5 s de silencio al inicio (fundido) y ~0,25 s al final; lean con calma y de forma natural, sin acelerar.",
         "- Los subtítulos del video (`subtitulos.srt`) reproducen exactamente este texto.",
         "- Reparto sugerido: Voz 1 y Voz 2 alternan escena por escena. Sustituyan `[Nombre 1]` y `[Nombre 2]` en la portada y el cierre (están en `build_video.py`).", ""]
    for e in ESCENAS:
        L += [f"## Escena {e['id']} · {e['titulo']}", "",
              f"- **Tiempo:** {mmss(e['ini'])}–{mmss(e['fin'])} ({e['dur']:.1f} s, {e['palabras']} palabras)",
              f"- **Lee:** {e['voz']}", f"- **Se ve:** {e['ver']}", "", f"**Narración:** {e['texto']}", ""]
    (VIDEO / "guion.md").write_text("\n".join(L), encoding="utf-8")


# ------------------------------------------------------------------ composición
def con_subtitulo(base: Image.Image, texto: str) -> Image.Image:
    img = base.convert("RGBA")
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    d.rectangle((0, 905, W, H), fill=(0, 0, 0, 190))
    f = fuente("n", 46)
    lineas = texto.split("\n")
    y = 905 + (H - 905 - len(lineas) * 62) // 2
    for l in lineas:
        d.text((W / 2, y + 31), l, font=f, fill=(255, 255, 255, 255), anchor="mm")
        y += 62
    return Image.alpha_composite(img, capa).convert("RGB")


def construir_escenas():
    return [globals()[e["render"]](e["id"]) for e in ESCENAS]


def generar_previews(bases, subs):
    PREVIEW.mkdir(exist_ok=True)
    for e, base in zip(ESCENAS, bases):
        medio = e["ini"] + e["dur"] / 2
        txt = next((t for a, b, t in subs if a <= medio < b), None) or next(t for a, b, t in subs if a >= e["ini"])
        con_subtitulo(base, txt).save(PREVIEW / f"escena_{e['id']:02d}.png")


def codificar(bases, subs):
    """Envía fotogramas crudos a dos ffmpeg (con y sin subtítulos) por tubería."""
    ffmpeg = __import__("imageio_ffmpeg").get_ffmpeg_exe()
    destinos = {"demo_arquitectura.mp4": True, "demo_arquitectura_sin_subs.mp4": False}
    procs = {}
    for nombre in destinos:
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-tune", "stillimage",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(VIDEO / nombre)]
        procs[nombre] = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    bytes_base = [b.tobytes() for b in bases]
    cache_sub: dict = {}

    def escribir(datos_sin, datos_con=None):
        for nombre, p in procs.items():
            p.stdin.write(datos_con if (destinos[nombre] and datos_con is not None) else datos_sin)

    n_fade = int(FADE_S * FPS)
    for idx, e in enumerate(ESCENAS):
        f_ini, f_fin = round(e["ini"] * FPS), round(e["fin"] * FPS)
        if idx > 0:  # fundido entre escenas (sin subtítulo en esos instantes)
            for k in range(n_fade):
                escribir(Image.blend(bases[idx - 1], bases[idx], (k + 1) / (n_fade + 1)).tobytes())
            f_ini += n_fade
        for f in range(f_ini, f_fin):
            t = f / FPS
            txt = next((s for a, b, s in subs if a <= t < b), None)
            if txt is None:
                escribir(bytes_base[idx])
            else:
                if (idx, txt) not in cache_sub:
                    cache_sub[(idx, txt)] = con_subtitulo(bases[idx], txt).tobytes()
                escribir(bytes_base[idx], cache_sub[(idx, txt)])
    for p in procs.values():
        p.stdin.close()
    for nombre, p in procs.items():
        if p.wait() != 0:
            raise RuntimeError(f"ffmpeg falló al generar {nombre}")


def main():
    VIDEO.mkdir(exist_ok=True)
    subs = planificar_subtitulos()
    escribir_guion()
    escribir_srt(subs)
    print(f"Duración total: {DURACION:.1f} s ({mmss(DURACION)}) · {sum(e['palabras'] for e in ESCENAS)} palabras · {len(subs)} bloques de subtítulo")
    for e in ESCENAS:
        print(f"  Escena {e['id']:2d} {mmss(e['ini'])}-{mmss(e['fin'])} ({e['dur']:.1f}s) {e['titulo']}")
    bases = construir_escenas()
    generar_previews(bases, subs)
    if "--previews" in sys.argv:
        return
    codificar(bases, subs)
    print("Listo:", VIDEO / "demo_arquitectura.mp4")


if __name__ == "__main__":
    main()
