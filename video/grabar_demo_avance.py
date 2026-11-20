"""Graba la demostración "Arquitectura ejecutada" (versión de avance): un motor, varios escenarios.

Uso:
    python video/grabar_demo_avance.py                    # graba todo y genera el video subtitulado
    python video/grabar_demo_avance.py --ensayo           # ejecuta los mismos pasos SIN grabar
    python video/grabar_demo_avance.py --solo-subtitulos  # rehace .srt y mp4 desde la última grabación
    python video/grabar_demo_avance.py --solo-diapositivas  # solo dibuja las diapositivas (video/_avance_*.png)

Qué hace, en orden:
    1. Portada y diapositiva de arquitectura (7 módulos + flujo de 9 pasos), generadas con Pillow.
    2. Abre la GUI Tkinter real, que muestra el panel de progreso (barra, 9 pasos, escenario/estrategia,
       registro con hora). La GUI queda a la izquierda y Chrome (Selenium, visible) a la derecha,
       de modo que el progreso se ve mientras el navegador trabaja.
    3. Escenarios, todos con los botones "1. Inspeccionar" y "2. Extraer y guardar":
         1) HTML estático + paginación (books.toscrape.com, Requests, 2 páginas)
         2) JavaScript (quotes.toscrape.com/js, Selenium con Chrome visible, 2 páginas)
         3) API JSON (quotes.toscrape.com/api, método api, autorización confirmada)
         4) CAPTCHA (demo pública de reCAPTCHA en nopecha.com, permitida por robots.txt): la herramienta marca INCIDENCIA y se detiene
         5) Re-ejecución del escenario 1 para mostrar la detección de cambios
    4. Abre en VS Code el dataset consolidado y la matriz de escenarios (si existen).
    5. Cierre. Se crean .srt con la narración sincronizada con los tiempos reales, el guion y los mp4.

Durante la grabación no se debe usar el teclado ni el mouse. Se graba el área de trabajo del
monitor principal (sin barra de tareas); la GUI y Chrome se colocan sobre un fondo oscuro propio.
Todas las ventanas se minimizan al inicio y se restauran al final.

Salidas (carpeta ``video/``):
    demo_avance.mp4            video final con subtítulos quemados
    demo_avance_sin_subs.mp4   grabación limpia (para editar con la voz)
    demo_avance.srt            subtítulos
    guion_demo_avance.md       guion con los tiempos reales
    demo_output_avance/        datos generados por la GUI durante la demo (ignorado por git)
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# Coordenadas físicas reales (sin escalado de Windows) en este proceso y en el hijo --gui.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # pragma: no cover
    pass

RAIZ = Path(__file__).resolve().parent.parent
VIDEO = RAIZ / "video"
sys.path.insert(0, str(VIDEO))
import grabar_demo as base  # noqa: E402  (reutiliza ventanas Win32, ffmpeg, code, _ts, _bloques)

SALIDA_GUI = VIDEO / "demo_output_avance"
GRABACION = VIDEO / "_avance_raw.mkv"
TIEMPOS = VIDEO / "_avance_tiempos.json"
EVENTOS = VIDEO / "_avance_eventos.txt"
SEÑAL_IR = VIDEO / "_avance_ir.txt"
SEÑAL_CERRAR = VIDEO / "_avance_cerrar.txt"
FINAL = VIDEO / "demo_avance.mp4"
FINAL_SIN_SUBS = VIDEO / "demo_avance_sin_subs.mp4"
SRT = VIDEO / "demo_avance.srt"
GUION = VIDEO / "guion_demo_avance.md"
PNG_PORTADA = VIDEO / "_avance_portada.png"
PNG_ARQ = VIDEO / "_avance_arquitectura.png"
PNG_CIERRE = VIDEO / "_avance_cierre.png"

NARRADORA = base.NARRADORA
INTEGRANTES = base.INTEGRANTES
INSTITUCION = base.INSTITUCION
MATERIA = base.MATERIA
DUR_PORTADA, DUR_ARQ, DUR_CIERRE = 8.0, 22.0, 6.0  # segundos
FONDO = (11, 22, 48)  # color de fondo del video y de la ventana de fondo de la GUI
FONDO_HEX = "#0b1630"
RERUN = True  # repetir el escenario 1 para mostrar la detección de cambios

MATRIZ = RAIZ / "docs/evidencias/MATRIZ_ESCENARIOS.md"
DATASET = RAIZ / "datasets/multisitio/dataset_multisitio.csv"

# Escenarios que la GUI "teclea". method/json/api/headless se aplican a los controles reales.
ESCENARIOS = [
    dict(n=1, badge="ESCENARIO 1 · HTML estático + paginación", url="https://books.toscrape.com/",
         method="requests", headless=True, item="article.product_pod", json="",
         campos="titulo*=h3 a::title\nprecio*=p.price_color\ndisponibilidad=p.instock.availability\n"
                "rating=p.star-rating::class\nurl*=h3 a::href",
         pag="li.next a", paginas="2", registros="40", pausa="2", api=False, lectura=7, lectura_ext=7),
    dict(n=2, badge="ESCENARIO 2 · JavaScript (Selenium)", url="https://quotes.toscrape.com/js/",
         method="selenium", headless=False, item="div.quote", json="",
         campos="texto*=span.text\nautor*=small.author",
         pag="li.next a", paginas="2", registros="20", pausa="2", api=False, lectura=7, lectura_ext=5),
    dict(n=3, badge="ESCENARIO 3 · API JSON", url="https://quotes.toscrape.com/api/quotes?page=1",
         method="api", headless=True, item="", json="quotes",
         campos="texto*=text\nautor*=author.name",
         pag="", paginas="1", registros="10", pausa="2", api=True, lectura=6, lectura_ext=7),
    dict(n=4, badge="ESCENARIO 4 · CAPTCHA (incidencia)", url="https://nopecha.com/demo/recaptcha",
         method="requests", headless=True, item="form", json="",
         campos="formulario*=form",
         pag="", paginas="1", registros="10", pausa="2", api=False, lectura=9, lectura_ext=9),
]

# Narración: cada clave es una marca de la grabación; los subtítulos se reparten en su duración REAL.
NARRACION = {
    "portada": "Hola, somos Nelson Noriega, Andrea Arroyo y Diego Salazar, del Tecnológico de Toluca. "
               "Esta es la demostración de la arquitectura ejecutándose, para Técnicas de Adquisición de Datos.",
    "arquitectura": "La arquitectura tiene siete módulos: configuración, inspección, adquisición, selección, "
                    "transformación, almacenamiento y monitoreo. app.py los orquesta en un flujo de nueve pasos "
                    "y la interfaz Tkinter muestra el avance en vivo. Lo importante: es un solo motor. "
                    "Cada sitio nuevo es solo otra configuración.",
    "e1_config": "Escenario uno: HTML estático con paginación. En la capa de presentación, gui.py, capturamos la URL, "
                 "el método requests y los selectores CSS. Todo se convierte en un ScrapeConfig.",
    "e1_inspeccion": "Al pulsar Inspeccionar, app.py recorre los pasos uno a tres. Config valida la URL, "
                     "inspector.py hace una sola solicitud GET y estrategia.py clasifica el escenario "
                     "y recomienda el método.",
    "e1_extraccion": "Con Extraer y guardar continúa el flujo. El motor de extracción obtiene cada página y respeta "
                     "la pausa de dos segundos; selection aplica los selectores, transform limpia y valida, "
                     "storage guarda el CSV y monitoring escribe el informe. La barra avanza paso a paso.",
    "e2_config": "Escenario dos: un sitio con JavaScript. Es el mismo motor; solo cambia la configuración: "
                 "método selenium con Chrome visible, a la derecha, y selectores del contenido ya renderizado.",
    "e2_inspeccion": "El inspector detecta que el HTML inicial casi no trae las citas y que hay señales de "
                     "JavaScript. La estrategia recomendada cambia a selenium.",
    "e2_extraccion": "Selenium abre Chrome, espera a que el navegador renderice las citas, lee el DOM y sigue a la "
                     "siguiente página. Después se repiten los mismos pasos de selección, limpieza, "
                     "almacenamiento e informe.",
    "e3_config": "Escenario tres: una API JSON. Indicamos el método api y la ruta de la lista de registros, "
                 "y confirmamos que el endpoint está autorizado; sin esa casilla el motor no lo consulta.",
    "e3_inspeccion": "La inspección reconoce una respuesta JSON y la estrategia recomienda api.",
    "e3_extraccion": "Sin navegador: una solicitud GET al endpoint, selection recorre la ruta quotes, y transform "
                     "y storage completan los nueve pasos del mismo flujo.",
    "e4_config": "Escenario cuatro: una página protegida con reCAPTCHA. Aquí mostramos el comportamiento "
                 "responsable de la herramienta.",
    "e4_inspeccion": "El inspector detecta el CAPTCHA. El paso tres se marca como incidencia y el cuadro de "
                     "escenario cambia a naranja.",
    "e4_extraccion": "Al intentar extraer, el motor se detiene: no resuelve ni evade el CAPTCHA. Los pasos "
                     "siguientes quedan sin ejecutar y el informe explica el motivo.",
    "e5_rerun": "Por último repetimos el escenario uno. Monitoring compara con la ejecución anterior para "
                "detectar cambios, y el registro lo informa.",
    "resultado_csv": "Todos los escenarios se consolidaron en un dataset multisitio con linaje: escenario, "
                     "URL de origen, método y ejecución de cada valor.",
    "resultado_matriz": "La matriz de escenarios resume sitio, mecanismo detectado, estrategia, resultado y "
                        "viabilidad. Un único motor, muchos escenarios.",
    "cierre": "Gracias por su atención.",
}


# ----------------------------------------------------------------- disposición de pantalla
user32 = ctypes.windll.user32


def disposicion() -> dict:
    """Área de trabajo del monitor principal y reparto: GUI a la izquierda, Chrome a la derecha."""
    r = wt.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    x0, y0 = r.left, r.top
    W, H = (r.right - r.left) // 2 * 2, (r.bottom - r.top) // 2 * 2
    franja = 110  # banda oscura inferior para los subtítulos
    alto = H - franja
    gui_w = max(1100, int(W * 0.66))
    return dict(x0=x0, y0=y0, W=W, H=H, alto=alto, gui_w=gui_w,
                chrome=(x0 + gui_w, y0, W - gui_w, alto))


def vigilar_chrome(activo, previas: set[int], rect: tuple[int, int, int, int]) -> None:
    """Coloca cada ventana nueva de Chrome (la de Selenium) en ``rect`` sin robar el foco.

    Ignora las ventanas de Chrome que ya existían (del usuario) para no tocarlas.
    """
    x, y, w, h = rect
    flags = 0x0010 | 0x0040  # SWP_NOACTIVATE | SWP_SHOWWINDOW
    while activo():
        for hwnd, _ in base._ventanas():
            if hwnd in previas or not base._es_chrome(hwnd):
                continue
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
                user32.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
            if (r.left, r.top, r.right - r.left, r.bottom - r.top) != (x, y, w, h):
                user32.SetWindowPos(hwnd, 0, x, y, w, h, flags)
        time.sleep(0.25)


# ----------------------------------------------------------------- grabadora
class Grabadora:
    """Controla ffmpeg (gdigrab del área de trabajo) y anota el instante de cada marca."""

    def __init__(self, activa: bool, lay: dict):
        self.activa, self.lay = activa, lay
        self.proc: subprocess.Popen | None = None
        self.t0 = 0.0
        self.pasos: list[dict] = []

    def iniciar(self) -> None:
        if self.activa:
            L = self.lay
            self.proc = subprocess.Popen(
                [base.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab",
                 "-framerate", "15", "-draw_mouse", "1",
                 "-offset_x", str(L["x0"]), "-offset_y", str(L["y0"]),
                 "-video_size", f"{L['W']}x{L['H']}", "-i", "desktop",
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
                 str(GRABACION)],
                stdin=subprocess.PIPE,
            )
        self.t0 = time.time()
        time.sleep(1.5)  # ffmpeg tarda un momento en empezar a capturar

    def paso(self, clave: str, epoch: float | None = None) -> None:
        t = (epoch if epoch is not None else time.time()) - self.t0
        self.pasos.append({"clave": clave, "inicio": round(t, 2)})
        print(f"  [{t:6.1f}s] {clave}")

    def detener(self) -> None:
        total = time.time() - self.t0
        if self.proc:
            self.proc.communicate(b"q", timeout=60)
        TIEMPOS.write_text(json.dumps({"total": round(total, 2), "pasos": self.pasos}, indent=2),
                           encoding="utf-8")


# ----------------------------------------------------------------- GUI automatizada (proceso hijo)
def demo_gui() -> None:
    """Abre la GUI real, la maneja programáticamente y reporta marcas con su hora."""
    sys.path.insert(0, str(RAIZ))
    import tkinter as tk
    from smart_scraper.gui import ScraperWindow

    # Solo para la grabación: antes de cerrar cada Chrome, desplazar la página unos segundos para
    # que se vea el contenido. No altera el HTML ya leído ni los datos; smart_scraper no se modifica.
    from selenium.webdriver.chrome.webdriver import WebDriver
    quit_original = WebDriver.quit

    def quit_con_pausa(self):
        try:
            for _ in range(5):
                self.execute_script("window.scrollBy(0, 300)")
                time.sleep(0.5)
        except Exception:
            pass
        quit_original(self)

    WebDriver.quit = quit_con_pausa

    lay = disposicion()
    root = tk.Tk()
    # Fondo oscuro del tamaño del área de trabajo (oculta escritorio y deja franja para subtítulos).
    fondo = tk.Toplevel(root, bg=FONDO_HEX)
    fondo.overrideredirect(True)
    fondo.geometry(f"{lay['W']}x{lay['H']}+{lay['x0']}+{lay['y0']}")
    win = ScraperWindow(root)
    win.output_directory = SALIDA_GUI
    win.output_label.configure(text="video/demo_output_avance")
    root.geometry(f"{lay['gui_w']}x{lay['alto']}+{lay['x0']}+{lay['y0']}")
    badge = tk.Label(root, text="", bg="#fbbf24", fg="#14213d", font=("Segoe UI", 13, "bold"),
                     padx=12, pady=5)
    badge.place(relx=1.0, x=-16, y=18, anchor="ne")

    def marcar(clave: str) -> None:
        with EVENTOS.open("a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f}|{clave}\n")

    actual = {"n": 0}
    original = win._on_progress

    def con_marca(step, total, title, detail, status):
        original(step, total, title, detail, status)
        marcar(f"e{actual['n']}_p{step}_{status}")

    win._on_progress = con_marca

    cola: list[tuple] = []

    def add(fn, ms: int = 0) -> None:
        cola.append(("f", fn, ms))

    def teclear(widget, texto: str, ms: int = 28) -> None:
        for ch in texto:
            add(lambda c=ch: widget.insert("end", c), ms)

    def limpiar() -> None:
        for e in (win.url, win.item_selector, win.json_path, win.pagination_selector,
                  win.load_more_selector):
            e.delete(0, "end")
        win.fields.delete("1.0", "end")
        win.method.set("requests")
        win.headless.set(True)
        win.authorized_api.set(False)
        win.scroll_steps.set("0")
        win.load_more_clicks.set("0")

    def aplicar_rapido(e: dict) -> None:
        limpiar()
        win.url.insert(0, e["url"])
        win.method.set(e["method"])
        win.headless.set(e["headless"])
        win.item_selector.insert(0, e["item"])
        win.json_path.insert(0, e["json"])
        win.fields.insert("1.0", e["campos"])
        win.pagination_selector.insert(0, e["pag"])
        win.max_pages.set(e["paginas"])
        win.max_records.set(e["registros"])
        win.delay.set(e["pausa"])
        win.authorized_api.set(e["api"])

    def esperar_fin(extra_ms: int) -> None:
        cola.append(("w", extra_ms))

    def escenario(e: dict) -> None:
        n = e["n"]
        add(lambda: (actual.__setitem__("n", n), badge.configure(text=e["badge"]), marcar(f"e{n}_config")), 800)
        add(limpiar, 300)
        teclear(win.url, e["url"], 24)
        add(lambda: win.method.set(e["method"]), 600)
        add(lambda: win.headless.set(e["headless"]), 500)
        if e["item"]:
            teclear(win.item_selector, e["item"])
        if e["json"]:
            teclear(win.json_path, e["json"])
        for ch in e["campos"]:
            add(lambda c=ch: win.fields.insert("end", c), 12)
        if e["pag"]:
            teclear(win.pagination_selector, e["pag"])
        add(lambda: (win.max_pages.set(e["paginas"]), win.max_records.set(e["registros"]),
                     win.delay.set(e["pausa"])), 700)
        if e["api"]:
            add(lambda: win.authorized_api.set(True), 900)
        add(lambda: marcar(f"e{n}_inspeccion"), 1200)
        add(lambda: win.inspect_button.invoke(), 600)
        esperar_fin(e["lectura"] * 1000)
        add(lambda: marcar(f"e{n}_extraccion"), 300)
        add(lambda: win.run_button.invoke(), 600)
        esperar_fin(e["lectura_ext"] * 1000)

    for e in ESCENARIOS:
        escenario(e)
    if RERUN:
        e1 = ESCENARIOS[0]
        add(lambda: (actual.__setitem__("n", 5), badge.configure(text="ESCENARIO 5 · Re-ejecución: cambios"),
                     marcar("e5_rerun"), aplicar_rapido(e1)), 2500)
        add(lambda: win.run_button.invoke(), 600)
        esperar_fin(8000)

    def correr(i: int = 0) -> None:
        if i >= len(cola):
            marcar("fin")
            esperar_cierre()
            return
        item = cola[i]
        if item[0] == "f":
            item[1]()
            root.after(item[2], correr, i + 1)
        else:
            esperar(item[1], i, time.time() + 150)

    def esperar(extra: int, i: int, limite: float) -> None:
        ocupado = win.run_button.instate(["disabled"])
        if ocupado and time.time() < limite:
            root.after(300, esperar, extra, i, limite)
        else:
            root.after(extra, correr, i + 1)

    def esperar_cierre() -> None:
        """Mantiene la GUI visible hasta que el grabador abre VS Code encima (transición sin escritorio)."""
        if SEÑAL_CERRAR.exists() or time.time() > t_inicio + 600:
            root.destroy()
        else:
            root.after(300, esperar_cierre)

    def comenzar() -> None:
        if SEÑAL_IR.exists():
            correr()
        else:
            root.after(200, comenzar)

    t_inicio = time.time()
    root.update()
    root.lift()
    root.focus_force()
    marcar("listo")
    root.after(300, comenzar)
    root.mainloop()


# ----------------------------------------------------------------- guion de la demo (proceso principal)
def _powershell_teclas(teclas: str) -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    f"[System.Windows.Forms.SendKeys]::SendWait('{teclas}')"], capture_output=True)


def traer_al_frente(fragmento: str, espera: float = 8.0) -> None:
    """Pone al frente la ventana cuyo título contiene ``fragmento`` sin simular teclas."""
    flags = 0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
    limite = time.time() + espera
    while time.time() < limite:
        for hwnd, titulo in base._ventanas():
            if fragmento.lower() in titulo.lower():
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)  # HWND_TOPMOST
                user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags)  # HWND_NOTOPMOST
                return
        time.sleep(0.3)


def ejecutar_demo(grabar: bool) -> None:
    """Ejecuta (y opcionalmente graba) la demostración completa."""
    if SALIDA_GUI.exists():
        shutil.rmtree(SALIDA_GUI, ignore_errors=True)  # línea base limpia para la detección de cambios
    SALIDA_GUI.mkdir(parents=True)
    for f in (EVENTOS, SEÑAL_IR, SEÑAL_CERRAR):
        f.unlink(missing_ok=True)
    lay = disposicion()
    g = Grabadora(grabar, lay)

    print("Minimizando ventanas y abriendo la GUI…")
    base.minimizar_todo()
    time.sleep(1.5)
    previas = {h for h, _ in base._ventanas() if base._es_chrome(h)}
    # La grabación empieza ANTES de abrir la GUI y la señal de inicio ya existe: el hijo arranca
    # los escenarios en cuanto está listo (sin depender de sondeos entre procesos).
    g.iniciar()
    SEÑAL_IR.write_text("go", encoding="utf-8")
    gui = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--gui"], cwd=RAIZ)
    limite = time.time() + 40
    while time.time() < limite and gui.poll() is None:
        if EVENTOS.exists() and "listo" in EVENTOS.read_text(encoding="utf-8"):
            break
        time.sleep(0.3)
    # Sin el truco de la tecla ALT de base.enfocar: en Tk deja la ventana en "modo menú"
    # y congela los temporizadores (la GUI no avanzaba). Se trae al frente con SetWindowPos.
    traer_al_frente("Web Scraper Inteligente")
    time.sleep(0.8)
    activo = lambda: gui.poll() is None  # noqa: E731
    threading.Thread(target=vigilar_chrome, args=(activo, previas, lay["chrome"]), daemon=True).start()

    vistos, fin_gui = 0, False
    limite_gui = time.time() + 480  # salvaguarda: nunca dejar la grabación colgada
    while gui.poll() is None and not fin_gui:
        if time.time() > limite_gui:
            print("  (aviso) la GUI excedió 8 min; se cierra")
            gui.kill()
            break
        if EVENTOS.exists():
            lineas = EVENTOS.read_text(encoding="utf-8").splitlines()
            for ln in lineas[vistos:]:
                ep, _, clave = ln.partition("|")
                if clave == "fin":
                    fin_gui = True
                elif clave != "listo":
                    g.paso(clave, float(ep))
            vistos = len(lineas)
        time.sleep(0.3)

    # Resultado: VS Code se abre ENCIMA de la GUI y recién entonces se cierra la GUI.
    if DATASET.exists():
        base.code("-n", str(RAIZ), "-g", f"{DATASET}:1")
        time.sleep(6)
        base.enfocar("Visual Studio Code")
        g.paso("resultado_csv")
        SEÑAL_CERRAR.write_text("x", encoding="utf-8")
        time.sleep(10)
    else:
        SEÑAL_CERRAR.write_text("x", encoding="utf-8")
    if MATRIZ.exists():
        base.code("-r", "-g", f"{MATRIZ}:1")
        time.sleep(2.5)
        base.enfocar("Visual Studio Code")
        _powershell_teclas("^+v")  # Ctrl+Shift+V: vista previa de Markdown
        g.paso("resultado_matriz")
        time.sleep(14)
    g.detener()
    gui.poll() is None and gui.kill()
    for f in (EVENTOS, SEÑAL_IR, SEÑAL_CERRAR):
        f.unlink(missing_ok=True)
    base.minimizar_todo(deshacer=True)
    print("Demostración terminada.")


# ----------------------------------------------------------------- diapositivas
def _fuente(negrita: bool, tam: int, mono: bool = False):
    from PIL import ImageFont
    nombre = ("consolab.ttf" if negrita else "consola.ttf") if mono else (
        "segoeuib.ttf" if negrita else "segoeui.ttf")
    return ImageFont.truetype("C:/Windows/Fonts/" + nombre, tam)


def _envolver(d, texto: str, fuente, ancho: int) -> list[str]:
    lineas, actual = [], ""
    for p in texto.split():
        prueba = f"{actual} {p}".strip()
        if d.textlength(prueba, font=fuente) > ancho and actual:
            lineas.append(actual)
            actual = p
        else:
            actual = prueba
    if actual:
        lineas.append(actual)
    return lineas


def diapositivas() -> None:
    """Dibuja con Pillow la portada, la arquitectura (7 módulos + 9 pasos) y el cierre (1920x1080)."""
    from PIL import Image, ImageDraw

    W, H = 1920, 1080
    PANEL, CYAN, AMBAR, TXT, MUTED = (21, 37, 74), (56, 189, 248), (251, 191, 36), (226, 232, 240), (148, 163, 184)

    def lienzo():
        img = Image.new("RGB", (W, H), FONDO)
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, W, 10), fill=CYAN)
        d.rectangle((0, H - 10, W, H), fill=CYAN)
        return img, d

    def integrantes(d, y, tam):
        d.text((W / 2, y), "   ·   ".join(INTEGRANTES), font=_fuente(True, tam), fill=AMBAR, anchor="mm")

    # --- Portada
    img, d = lienzo()
    d.text((W / 2, 110), INSTITUCION.upper(), font=_fuente(True, 44), fill=MUTED, anchor="mm")
    d.rounded_rectangle((W / 2 - 520, 165, W / 2 + 520, 245), radius=40, fill=PANEL, outline=CYAN, width=3)
    d.text((W / 2, 205), MATERIA, font=_fuente(True, 46), fill=CYAN, anchor="mm")
    d.text((W / 2, 365), "Herramienta de Extracción Web", font=_fuente(True, 96), fill=TXT, anchor="mm")
    d.text((W / 2, 480), "Inteligente", font=_fuente(True, 96), fill=CYAN, anchor="mm")
    d.text((W / 2, 580), "Demostración: la arquitectura en ejecución, con progreso en vivo",
           font=_fuente(False, 40), fill=MUTED, anchor="mm")
    d.line((W / 2 - 300, 650, W / 2 + 300, 650), fill=PANEL, width=3)
    d.text((W / 2, 700), "Integrantes", font=_fuente(False, 34), fill=MUTED, anchor="mm")
    integrantes(d, 765, 52)
    img.save(PNG_PORTADA)

    # --- Arquitectura
    try:
        sys.path.insert(0, str(RAIZ))
        from smart_scraper.app import STEP_TITLES
    except Exception:  # pragma: no cover
        STEP_TITLES = ["Ingreso de URL y validación", "Diagnóstico automatizado", "Presentación de resultados",
                       "Selección de datos", "Configuración de extracción", "Ejecución del motor",
                       "Limpieza y validación", "Almacenamiento", "Reporte final"]
    img, d = lienzo()
    d.text((W / 2, 62), "Un solo motor para todos los sitios", font=_fuente(True, 60), fill=TXT, anchor="mm")
    d.text((W / 2, 122), "Siete módulos y un flujo de nueve pasos: cada escenario es solo otra configuración",
           font=_fuente(False, 28), fill=MUTED, anchor="mm")
    x0, x1 = 100, W - 100
    # Capas superiores
    d.rounded_rectangle((x0, 165, x1, 225), radius=14, fill=PANEL, outline=CYAN, width=3)
    d.text((W / 2, 195), "gui.py  ·  Interfaz Tkinter: captura la configuración y muestra el progreso en vivo",
           font=_fuente(True, 28), fill=CYAN, anchor="mm")
    d.rounded_rectangle((x0, 240, x1, 300), radius=14, fill=PANEL, outline=AMBAR, width=3)
    d.text((W / 2, 270), "app.py  ·  run_job: orquesta los 9 pasos y emite el progreso a la interfaz",
           font=_fuente(True, 28), fill=AMBAR, anchor="mm")
    # Siete módulos
    modulos = [
        ("config.py", "Configuración", "URL, método, selectores y límites", (96, 165, 250)),
        ("inspector.py", "Inspección", "GET único; señales de JS, CAPTCHA, login", (52, 211, 153)),
        ("extractor.py", "Adquisición", "Requests, Selenium, Playwright o API", (251, 146, 60)),
        ("selection.py", "Selección", "Selectores CSS y rutas JSON", (167, 139, 250)),
        ("transform.py", "Transformación", "Limpieza, duplicados y validación", (244, 114, 182)),
        ("storage.py", "Almacenamiento", "CSV, Excel, JSON, SQLite y más", (45, 212, 191)),
        ("monitoring.py", "Monitoreo", "Registro e informe por ejecución", (250, 204, 21)),
    ]
    gap = 18
    cw = (x1 - x0 - 6 * gap) // 7
    top, ch = 330, 250
    for i, (arch, nombre, rol, col) in enumerate(modulos):
        cx = x0 + i * (cw + gap)
        d.rounded_rectangle((cx, top, cx + cw, top + ch), radius=16, fill=PANEL, outline=col, width=4)
        d.rectangle((cx + 4, top + 4, cx + cw - 4, top + 14), fill=col)
        d.text((cx + cw / 2, top + 52), f"{i + 1}", font=_fuente(True, 40), fill=col, anchor="mm")
        d.text((cx + cw / 2, top + 98), nombre, font=_fuente(True, 25), fill=TXT, anchor="mm")
        d.text((cx + cw / 2, top + 132), arch, font=_fuente(True, 20, mono=True), fill=col, anchor="mm")
        for k, linea in enumerate(_envolver(d, rol, _fuente(False, 21), cw - 24)):
            d.text((cx + cw / 2, top + 170 + k * 28), linea, font=_fuente(False, 21), fill=MUTED, anchor="mm")
    d.rounded_rectangle((x0, top + ch + 16, x1, top + ch + 66), radius=12, outline=(52, 211, 153), width=2)
    d.text((W / 2, top + ch + 41),
           "estrategia.py  ·  clasifica el escenario y recomienda el método: requests · selenium · playwright · api · detener",
           font=_fuente(False, 26), fill=(52, 211, 153), anchor="mm")
    # Flujo de 9 pasos
    d.text((x0, 690), "Flujo de 9 pasos (el panel de progreso de la GUI)", font=_fuente(True, 30), fill=TXT, anchor="lm")
    quien = [0, 1, 1, 3, 0, 2, 4, 5, 6]  # índice del módulo protagonista de cada paso
    etiqueta = ["config", "inspector", "estrategia", "selection", "config", "extractor", "transform",
                "storage", "monitoring"]
    g9 = 12
    w9 = (x1 - x0 - 8 * g9) // 9
    for i, titulo in enumerate(STEP_TITLES):
        px = x0 + i * (w9 + g9)
        col = (52, 211, 153) if i == 2 else modulos[quien[i]][3]
        d.rounded_rectangle((px, 725, px + w9, 925), radius=12, fill=PANEL, outline=col, width=3)
        d.ellipse((px + w9 / 2 - 20, 735, px + w9 / 2 + 20, 775), fill=col)
        d.text((px + w9 / 2, 755), str(i + 1), font=_fuente(True, 24), fill=FONDO, anchor="mm")
        for k, linea in enumerate(_envolver(d, titulo, _fuente(True, 20), w9 - 16)[:3]):
            d.text((px + w9 / 2, 800 + k * 26), linea, font=_fuente(True, 20), fill=TXT, anchor="mm")
        d.text((px + w9 / 2, 902), etiqueta[i], font=_fuente(False, 19, mono=True), fill=col, anchor="mm")
        if i < 8:
            d.text((px + w9 + g9 / 2, 825), "›", font=_fuente(True, 28), fill=MUTED, anchor="mm")
    d.text((W / 2, 995),
           "Escenarios en vivo:  HTML estático  ·  JavaScript  ·  API JSON  ·  CAPTCHA (incidencia)  ·  re-ejecución",
           font=_fuente(True, 30), fill=AMBAR, anchor="mm")
    img.save(PNG_ARQ)

    # --- Cierre
    img, d = lienzo()
    d.text((W / 2, 380), "¡Gracias!", font=_fuente(True, 170), fill=CYAN, anchor="mm")
    d.text((W / 2, 530), "Gracias por su atención", font=_fuente(False, 50), fill=TXT, anchor="mm")
    integrantes(d, 680, 48)
    d.text((W / 2, 770), f"{MATERIA}  ·  {INSTITUCION}", font=_fuente(False, 38), fill=MUTED, anchor="mm")
    img.save(PNG_CIERRE)
    print("Diapositivas:", PNG_PORTADA, PNG_ARQ, PNG_CIERRE, sep="\n  ")


# ----------------------------------------------------------------- subtítulos y video final
def _duracion_video(ruta: Path) -> float:
    """Duración en segundos de un video según ffmpeg (0.0 si no se puede leer)."""
    import re
    r = subprocess.run([base.ffmpeg(), "-hide_banner", "-i", str(ruta)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def generar_subtitulos() -> None:
    """Antepone portada y arquitectura, añade el cierre, crea .srt y guion y quema los subtítulos."""
    datos = json.loads(TIEMPOS.read_text(encoding="utf-8"))
    desfase = DUR_PORTADA + DUR_ARQ
    total_grab = datos["total"]
    # gdigrab puede descartar cuadros: la grabación dura algo menos que el reloj de pared.
    # Se reescalan las marcas a la duración REAL del archivo para que los subtítulos no se desfasen.
    real = _duracion_video(GRABACION)
    factor = real / total_grab if real and total_grab else 1.0
    total_grab = real or total_grab
    pasos = [{"clave": "portada", "inicio": 0.0}, {"clave": "arquitectura", "inicio": DUR_PORTADA}]
    marcas = [p for p in datos["pasos"] if p["clave"] in NARRACION]
    pasos += [{"clave": p["clave"], "inicio": p["inicio"] * factor + desfase} for p in marcas]
    pasos.append({"clave": "cierre", "inicio": desfase + total_grab})
    total = desfase + total_grab + DUR_CIERRE

    srt, guion, n = [], [], 1
    guion += ["# Guion de la demostración (arquitectura en ejecución)", "",
              f"*Generado por `video/grabar_demo_avance.py` con los tiempos reales de la grabación. "
              f"Narra: **{NARRADORA}**.*", "",
              f"- {MATERIA} · {INSTITUCION}", f"- Integrantes: {', '.join(INTEGRANTES)}",
              f"- Duración: **{int(total // 60)}:{int(total % 60):02}** (portada {DUR_PORTADA:.0f} s + "
              f"arquitectura {DUR_ARQ:.0f} s + demostración en vivo + cierre {DUR_CIERRE:.0f} s)",
              "- Si la voz no cabe en un tramo, recorten o alarguen la pausa en el editor; los tiempos son los de la pantalla.",
              ""]
    for i, paso in enumerate(pasos):
        ini = paso["inicio"]
        fin = pasos[i + 1]["inicio"] if i + 1 < len(pasos) else total
        texto = NARRACION[paso["clave"]]
        guion += [f"## {base._ts(ini)[3:8]} – {base._ts(fin)[3:8]} · {paso['clave']}", "", texto, ""]
        bloques = base._bloques(texto)
        pesos = [len(b) for b in bloques]
        util_ini, util_fin = ini + 0.6, max(ini + 1.2, fin - 0.4)
        t = util_ini
        for b, w in zip(bloques, pesos):
            dur = (util_fin - util_ini) * w / sum(pesos)
            srt += [str(n), f"{base._ts(t)} --> {base._ts(t + min(dur, 7.0))}", b, ""]
            n += 1
            t += dur
    otras = [p for p in datos["pasos"] if p["clave"] not in NARRACION]
    if otras:
        guion += ["## Marcas del progreso real de la GUI (referencia)", "",
                  "| Tiempo en el video | Marca (escenario_paso_estado) |", "|---|---|"]
        guion += [f"| {base._ts(p['inicio'] + desfase)[3:8]} | `{p['clave']}` |" for p in otras]
        guion.append("")
    SRT.write_text("\n".join(srt), encoding="utf-8")
    GUION.write_text("\n".join(guion), encoding="utf-8")

    diapositivas()
    relleno = "0x%02x%02x%02x" % FONDO
    unir = (
        f"[0:v]format=yuv420p,setsar=1,fade=t=in:st=0:d=0.6,fade=t=out:st={DUR_PORTADA - 0.6}:d=0.6[p];"
        f"[1:v]format=yuv420p,setsar=1,fade=t=in:st=0:d=0.5,fade=t=out:st={DUR_ARQ - 0.5}:d=0.5[a];"
        "[2:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:0:{relleno},fps=30,format=yuv420p,setsar=1,fade=t=in:st=0:d=0.5[g];"
        f"[3:v]format=yuv420p,setsar=1,fade=t=in:st=0:d=0.6,fade=t=out:st={DUR_CIERRE - 0.8}:d=0.8[c];"
        "[p][a][g][c]concat=n=4:v=1:a=0[v]"
    )
    entradas = ["-loop", "1", "-framerate", "30", "-t", str(DUR_PORTADA), "-i", PNG_PORTADA.name,
                "-loop", "1", "-framerate", "30", "-t", str(DUR_ARQ), "-i", PNG_ARQ.name,
                "-i", GRABACION.name,
                "-loop", "1", "-framerate", "30", "-t", str(DUR_CIERRE), "-i", PNG_CIERRE.name]
    codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30", "-an"]
    estilo = ("FontName=Arial,FontSize=15,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,"
              "BorderStyle=4,Outline=0,Shadow=0,MarginV=28")
    ff = base.ffmpeg()
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", *entradas,
                    "-filter_complex", unir, "-map", "[v]", *codec, FINAL_SIN_SUBS.name], cwd=VIDEO, check=True)
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", *entradas,
                    "-filter_complex", unir + f";[v]subtitles={SRT.name}:force_style='{estilo}'[s]",
                    "-map", "[s]", *codec, FINAL.name], cwd=VIDEO, check=True)
    print(f"Listo: {FINAL} ({int(total // 60)}:{int(total % 60):02})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ensayo", action="store_true", help="ejecutar sin grabar")
    ap.add_argument("--solo-subtitulos", action="store_true", help="rehacer subtítulos y video final")
    ap.add_argument("--solo-diapositivas", action="store_true", help="solo dibujar las diapositivas PNG")
    ap.add_argument("--gui", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.gui:
        demo_gui()
    elif a.solo_diapositivas:
        diapositivas()
    elif a.solo_subtitulos:
        generar_subtitulos()
    else:
        ejecutar_demo(grabar=not a.ensayo)
        if not a.ensayo:
            generar_subtitulos()


if __name__ == "__main__":
    main()
