"""Graba automáticamente la demostración en vivo del proyecto (VS Code + pruebas + GUI + Selenium).

Uso:
    python video/grabar_demo.py            # graba la demo completa y genera el video subtitulado
    python video/grabar_demo.py --ensayo   # ejecuta los mismos pasos SIN grabar (para revisar)
    python video/grabar_demo.py --solo-subtitulos   # rehace .srt y video final desde la última grabación

Qué hace, en orden:
    1. Abre el proyecto en Visual Studio Code y lo maximiza.
    2. Empieza a grabar la pantalla completa con ffmpeg (gdigrab).
    3. Recorre en VS Code los archivos clave: extractor.py (_acquire_selenium), app.py (run_job)
       y config.py (ScrapeConfig).
    4. Abre una terminal y ejecuta ``pytest -v`` (14 pruebas).
    5. Abre la GUI Tkinter real del proyecto, "teclea" la configuración de books.toscrape.com,
       pulsa "1. Inspeccionar" y luego "2. Extraer y guardar" con Selenium y Chrome VISIBLE
       (3 páginas, pausa de 2 s, solo el sandbox de práctica).
    6. Abre en VS Code el CSV que acaba de generar la herramienta.
    7. Detiene la grabación, crea ``demo_en_vivo.srt`` con la narración sincronizada a los
       instantes reales de cada paso, quema los subtítulos y escribe ``guion_demo_en_vivo.md``
       para que la narradora grabe la voz.

Durante la grabación no se debe usar el teclado ni el mouse: ffmpeg captura TODA la pantalla.
Cierre antes aplicaciones con información privada y active "No molestar" (notificaciones).

Salidas (carpeta ``video/``):
    demo_en_vivo.mp4            video final con subtítulos quemados
    demo_en_vivo_sin_subs.mp4   grabación limpia (para editar con la voz)
    demo_en_vivo.srt            subtítulos
    guion_demo_en_vivo.md       guion con los tiempos reales de cada paso
    demo_output/                datos generados por la GUI durante la demo (ignorado por git)
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VIDEO = RAIZ / "video"
SALIDA_GUI = VIDEO / "demo_output"
GRABACION = VIDEO / "_demo_raw.mkv"
TIEMPOS = VIDEO / "_demo_tiempos.json"
FINAL = VIDEO / "demo_en_vivo.mp4"
FINAL_SIN_SUBS = VIDEO / "demo_en_vivo_sin_subs.mp4"
SRT = VIDEO / "demo_en_vivo.srt"
GUION = VIDEO / "guion_demo_en_vivo.md"
NARRADORA = "Andrea Arroyo"
INTEGRANTES = ["Nelson Noriega", "Andrea Arroyo", "Diego Salazar"]
INSTITUCION = "Tecnológico de Toluca"
MATERIA = "Técnicas de Adquisición de Datos"
PROYECTO = "Herramienta de Extracción Web Inteligente"
DUR_PORTADA, DUR_CIERRE = 10.0, 6.0  # segundos
PORTADA = VIDEO / "_portada.png"
CIERRE = VIDEO / "_cierre.png"

# Narración de cada paso: los subtítulos se reparten a lo largo de la duración REAL del paso.
NARRACION = {
    "portada": "Hola, somos Nelson Noriega, Andrea Arroyo y Diego Salazar, del Tecnológico de Toluca. "
               "Presentamos la demostración en vivo de nuestra herramienta para la materia "
               "Técnicas de Adquisición de Datos.",
    "cierre": "Gracias por su atención.",
    "intro": "Esta es la demostración en vivo. Abrimos el proyecto en Visual Studio Code: "
             "el paquete smart_scraper contiene los siete módulos de la arquitectura.",
    "extractor": "En extractor.py está la función _acquire_selenium. Configura Chrome, navega a la URL, "
                 "espera con WebDriverWait, revisa si hay CAPTCHA o login, hace clics y scroll acotados "
                 "y siempre cierra el navegador con driver.quit.",
    "app": "En app.py, la función run_job orquesta el flujo: inspecciona, extrae, selecciona, "
           "transforma, guarda y registra el informe de la ejecución.",
    "config": "En config.py, ScrapeConfig valida los límites: máximo diez páginas, mil registros "
              "y una pausa mínima de un segundo entre solicitudes.",
    "pruebas": "Ahora ejecutamos las pruebas automatizadas con pytest. Usan un servidor local con sitios "
               "simulados: HTML estático, JavaScript, API, paginación, autenticación y CAPTCHA. "
               "Las catorce pruebas pasan.",
    "gui": "Abrimos la interfaz gráfica de la herramienta. Ingresamos la URL de books.toscrape.com, "
           "un sitio creado para practicar extracción, elegimos el método Selenium con el navegador visible "
           "y definimos los selectores CSS de cada campo.",
    "inspeccion": "Primero pulsamos Inspeccionar. La herramienta diagnostica el sitio: título, señales "
                  "de JavaScript, paginación y si existe CAPTCHA o autenticación.",
    "extraccion": "Después pulsamos Extraer y guardar. Selenium abre Chrome, carga cada página, sigue el "
                  "enlace siguiente y respeta la pausa entre solicitudes. Al terminar, el panel muestra "
                  "el informe con el número de registros y las validaciones.",
    "resultado": "Por último abrimos el CSV generado: cada libro con su título, precio, disponibilidad, "
                 "rating y URL, listo para limpiar y analizar. Así se ejecuta la arquitectura de principio a fin.",
}

# Configuración que la demo "teclea" en la GUI.
DEMO_URL = "https://books.toscrape.com/"
DEMO_CAMPOS = "titulo*=h3 a::title\nprecio*=p.price_color\ndisponibilidad=p.instock.availability\n" \
              "rating=p.star-rating::class\nurl*=h3 a::href"


# ----------------------------------------------------------------- ventanas (Win32 vía ctypes)
user32 = ctypes.windll.user32
SW_MAXIMIZE = 3


def _ventanas() -> list[tuple[int, str]]:
    """Devuelve (handle, título) de las ventanas visibles de nivel superior."""
    res: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                res.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return res


def enfocar(*fragmentos: str, maximizar: bool = True, espera: float = 15.0) -> bool:
    """Busca una ventana cuyo título contenga todos los fragmentos, la maximiza y la trae al frente."""
    limite = time.time() + espera
    while time.time() < limite:
        for hwnd, titulo in _ventanas():
            if all(f.lower() in titulo.lower() for f in fragmentos):
                if maximizar:
                    user32.ShowWindow(hwnd, SW_MAXIMIZE)
                # Truco ALT: Windows solo permite SetForegroundWindow tras una entrada de teclado.
                user32.keybd_event(0x12, 0, 0, 0)
                user32.keybd_event(0x12, 0, 2, 0)
                user32.SetForegroundWindow(hwnd)
                return True
        time.sleep(0.3)
    print(f"  (aviso) no se encontró la ventana: {fragmentos}")
    return False


def minimizar_todo(deshacer: bool = False) -> None:
    """Minimiza (o restaura) todas las ventanas para que no aparezca nada privado detrás."""
    metodo = "UndoMinimizeALL" if deshacer else "MinimizeAll"
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"(New-Object -ComObject Shell.Application).{metodo}()"], capture_output=True)


def _titulo(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _es_chrome(hwnd: int) -> bool:
    """True si la ventana pertenece a un proceso chrome.exe (Chrome que abre Selenium)."""
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value.lower().endswith("\\chrome.exe")
        return False
    finally:
        k32.CloseHandle(h)


def vigilar_ventanas(activo) -> None:
    """Durante la GUI: maximiza las ventanas de Chrome que abre Selenium (sin robar el foco).

    ``activo`` es un callable que devuelve False cuando el vigilante debe terminar.
    """
    vistas: set[int] = set()
    flags = 0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
    while activo():
        for h, t in _ventanas():
            if _es_chrome(h):
                if not user32.IsZoomed(h):
                    user32.ShowWindow(h, SW_MAXIMIZE)
                if h not in vistas:  # traer al frente cada ventana nueva de Chrome
                    vistas.add(h)
                    user32.SetWindowPos(h, -1, 0, 0, 0, 0, flags)  # HWND_TOPMOST
                    user32.SetWindowPos(h, -2, 0, 0, 0, 0, flags)  # HWND_NOTOPMOST
        time.sleep(0.25)


# ----------------------------------------------------------------- utilidades
def ffmpeg() -> str:
    """Ruta del ejecutable de ffmpeg incluido en imageio-ffmpeg."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def code(*args: str) -> None:
    """Invoca la CLI de VS Code (``code``)."""
    exe = shutil.which("code") or shutil.which("code.cmd")
    if not exe:
        sys.exit("No se encontró la CLI 'code' de Visual Studio Code en el PATH.")
    subprocess.Popen([exe, *args], cwd=RAIZ, shell=exe.lower().endswith(".cmd"))


def linea_de(archivo: str, texto: str) -> int:
    """Número de línea (1-based) donde aparece ``texto`` por primera vez en ``archivo``."""
    for i, linea in enumerate((RAIZ / archivo).read_text(encoding="utf-8").splitlines(), 1):
        if texto in linea:
            return i
    return 1


class Grabadora:
    """Controla ffmpeg (gdigrab) y anota el instante de inicio de cada paso."""

    def __init__(self, activa: bool):
        self.activa = activa
        self.proc: subprocess.Popen | None = None
        self.t0 = 0.0
        self.pasos: list[dict] = []

    def iniciar(self) -> None:
        self.t0 = time.time()
        if self.activa:
            self.proc = subprocess.Popen(
                [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab",
                 "-framerate", "30", "-draw_mouse", "1", "-i", "desktop",
                 "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
                 str(GRABACION)],
                stdin=subprocess.PIPE,
            )
            time.sleep(1.5)  # ffmpeg tarda un momento en empezar a capturar

    def paso(self, clave: str) -> None:
        t = time.time() - self.t0
        self.pasos.append({"clave": clave, "inicio": round(t, 2)})
        print(f"  [{t:6.1f}s] {clave}")

    def detener(self) -> None:
        total = time.time() - self.t0
        if self.proc:
            self.proc.communicate(b"q", timeout=60)  # 'q' cierra el archivo correctamente
        TIEMPOS.write_text(json.dumps({"total": round(total, 2), "pasos": self.pasos}, indent=2),
                           encoding="utf-8")


# ----------------------------------------------------------------- GUI automatizada
def demo_gui() -> None:
    """Abre la GUI real del proyecto y la maneja programáticamente (tecleo visible y clics)."""
    sys.path.insert(0, str(RAIZ))
    import tkinter as tk
    from smart_scraper.gui import ScraperWindow

    # Solo para la grabación: antes de cerrar cada Chrome, desplazar la página despacio unos
    # segundos para que se vean los libros. No altera el HTML ya leído ni los datos extraídos;
    # el código del proyecto (smart_scraper) no se modifica.
    from selenium.webdriver.chrome.webdriver import WebDriver
    quit_original = WebDriver.quit

    def quit_con_pausa(self):
        try:
            for _ in range(8):
                self.execute_script("window.scrollBy(0, 350)")
                time.sleep(0.5)
        except Exception:
            pass
        quit_original(self)

    WebDriver.quit = quit_con_pausa

    root = tk.Tk()
    win = ScraperWindow(root)
    win.output_directory = SALIDA_GUI
    win.output_label.configure(text=str(SALIDA_GUI))
    root.state("zoomed")
    root.attributes("-topmost", True)  # siempre visible salvo mientras Chrome trabaja
    marcas = VIDEO / "_gui_eventos.txt"
    marcas.write_text("", encoding="utf-8")

    def marcar(evento: str) -> None:
        with marcas.open("a", encoding="utf-8") as f:
            f.write(evento + "\n")

    acciones: list = []  # cola de (retardo_ms, función)

    def teclear(widget, texto: str, es_text: bool = False, ms: int = 35) -> None:
        for ch in texto:
            if es_text:
                acciones.append((ms, lambda c=ch: widget.insert("end", c)))
            else:
                acciones.append((ms, lambda c=ch: widget.insert("end", c)))

    def fijar(widget, valor: str) -> None:
        acciones.append((400, lambda: widget.set(valor)))

    def pausa(ms: int) -> None:
        acciones.append((ms, lambda: None))

    # Configuración tecleada
    pausa(4000)
    teclear(win.url, DEMO_URL)
    fijar(win.method, "selenium")
    acciones.append((500, lambda: win.headless.set(False)))
    teclear(win.item_selector, "article.product_pod")
    teclear(win.fields, DEMO_CAMPOS, es_text=True, ms=22)
    teclear(win.pagination_selector, "li.next a")
    fijar(win.max_pages, "3")
    fijar(win.max_records, "60")
    fijar(win.delay, "2")
    pausa(3000)

    estado = {"fase": "config"}

    def boton_libre() -> bool:
        return win.run_button.instate(["!disabled"])

    def vigilar() -> None:
        """Avanza de fase cuando termina cada tarea en segundo plano de la GUI."""
        if estado["fase"] == "inspeccionando" and boton_libre():
            estado["fase"] = "inspeccionado"
            marcar("inspeccion_ok")
            root.after(12000, extraer)
        elif estado["fase"] == "extrayendo" and boton_libre():
            estado["fase"] = "fin"
            marcar("extraccion_ok")
            root.deiconify()
            root.state("zoomed")
            root.attributes("-topmost", True)
            root.lift()
            root.after(9000, root.destroy)
            return
        root.after(400, vigilar)

    def inspeccionar() -> None:
        marcar("inspeccion")
        estado["fase"] = "inspeccionando"
        win.inspect_button.invoke()
        root.after(800, vigilar)

    def extraer() -> None:
        marcar("extraccion")
        estado["fase"] = "extrayendo"
        win.run_button.invoke()
        # Minimizar la GUI para que Chrome (Selenium) sea lo que se vea mientras navega.
        root.after(1500, lambda: (root.attributes("-topmost", False), root.iconify()))

    def ejecutar(i: int = 0) -> None:
        if i < len(acciones):
            retardo, fn = acciones[i]
            fn()
            root.after(retardo, ejecutar, i + 1)
        else:
            inspeccionar()

    root.after(300, ejecutar)
    root.mainloop()


# ----------------------------------------------------------------- guion de la demo
def ejecutar_demo(grabar: bool) -> None:
    """Ejecuta (y opcionalmente graba) todos los pasos de la demostración."""
    SALIDA_GUI.mkdir(exist_ok=True)
    g = Grabadora(grabar)
    ext = linea_de("smart_scraper/extractor.py", "def _acquire_selenium")
    app = linea_de("smart_scraper/app.py", "def run_job")
    cfg = linea_de("smart_scraper/config.py", "class ScrapeConfig")

    print("Minimizando ventanas y abriendo VS Code…")
    minimizar_todo()
    time.sleep(1.5)
    code("-n", str(RAIZ), "-g", f"{RAIZ / 'README.md'}:1")
    time.sleep(6)
    enfocar("TAD-HerramientaExtraccion", "Visual Studio Code")
    time.sleep(2)

    g.iniciar()
    g.paso("intro")
    time.sleep(11)

    g.paso("extractor")
    code("-r", "-g", f"{RAIZ / 'smart_scraper/extractor.py'}:{ext}")
    time.sleep(17)

    g.paso("app")
    code("-r", "-g", f"{RAIZ / 'smart_scraper/app.py'}:{app}")
    time.sleep(12)

    g.paso("config")
    code("-r", "-g", f"{RAIZ / 'smart_scraper/config.py'}:{cfg}")
    time.sleep(12)

    g.paso("pruebas")
    marca = VIDEO / "_pytest_listo.txt"
    marca.unlink(missing_ok=True)
    comando = (
        "$host.UI.RawUI.WindowTitle='Pruebas TAD'; "
        f"Set-Location '{RAIZ}'; python -m pytest -v; "
        f"New-Item -ItemType File '{marca}' | Out-Null; Start-Sleep 600"
    )
    consola = subprocess.Popen(["powershell", "-NoProfile", "-Command", comando],
                               creationflags=subprocess.CREATE_NEW_CONSOLE)
    time.sleep(2)
    enfocar("Pruebas TAD", espera=8)
    limite = time.time() + 120
    while not marca.exists() and time.time() < limite:
        time.sleep(0.5)
    time.sleep(11)  # dejar ver el resultado "14 passed"
    consola.kill()
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(consola.pid)], capture_output=True)
    marca.unlink(missing_ok=True)

    g.paso("gui")
    eventos = VIDEO / "_gui_eventos.txt"
    eventos.unlink(missing_ok=True)
    gui = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--gui"], cwd=RAIZ)
    vistos: set[str] = set()
    import threading
    threading.Thread(target=vigilar_ventanas, args=(lambda: gui.poll() is None,), daemon=True).start()
    limite_gui = time.time() + 300  # salvaguarda: nunca dejar la grabación colgada
    while gui.poll() is None:
        if time.time() > limite_gui:
            print("  (aviso) la GUI excedió 5 min; se cierra")
            gui.kill()
            break
        if eventos.exists():
            for ev in eventos.read_text(encoding="utf-8").split():
                if ev in ("inspeccion", "extraccion") and ev not in vistos:
                    vistos.add(ev)
                    g.paso(ev)
        time.sleep(0.3)
    eventos.unlink(missing_ok=True)

    g.paso("resultado")
    csvs = sorted(SALIDA_GUI.glob("records-*.csv"), key=lambda p: p.stat().st_mtime)
    destino = csvs[-1] if csvs else RAIZ / "datasets/books_toscrape.csv"
    code("-r", "-g", f"{destino}:1")
    time.sleep(2)
    enfocar("Visual Studio Code")
    time.sleep(14)
    g.detener()
    minimizar_todo(deshacer=True)
    print("Demostración terminada.")


# ----------------------------------------------------------------- subtítulos y video final
def _ts(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def _bloques(texto: str, max_linea: int = 46) -> list[str]:
    """Divide la narración en bloques de hasta dos líneas de ``max_linea`` caracteres."""
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        if len(actual) + len(p) + 1 > max_linea and actual:
            lineas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    if actual:
        lineas.append(actual)
    return ["\n".join(lineas[i:i + 2]) for i in range(0, len(lineas), 2)]


def _tarjetas() -> None:
    """Dibuja con Pillow la portada y el cierre (1920x1080), con los datos del equipo."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1920, 1080
    BG, PANEL, CYAN, AMBAR, TXT, MUTED = (11, 22, 48), (21, 37, 74), (56, 189, 248), (251, 191, 36), (226, 232, 240), (148, 163, 184)

    def f(bold: bool, tam: int):
        return ImageFont.truetype("C:/Windows/Fonts/" + ("segoeuib.ttf" if bold else "segoeui.ttf"), tam)

    def base():
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, W, 10), fill=CYAN)
        d.rectangle((0, H - 10, W, H), fill=CYAN)
        return img, d

    def integrantes(d, y, tam):
        d.text((W / 2, y), "   ·   ".join(INTEGRANTES), font=f(True, tam), fill=AMBAR, anchor="mm")

    # Portada
    img, d = base()
    d.text((W / 2, 110), INSTITUCION.upper(), font=f(True, 44), fill=MUTED, anchor="mm")
    d.rounded_rectangle((W / 2 - 520, 165, W / 2 + 520, 245), radius=40, fill=PANEL, outline=CYAN, width=3)
    d.text((W / 2, 205), MATERIA, font=f(True, 46), fill=CYAN, anchor="mm")
    d.text((W / 2, 365), "Herramienta de Extracción Web", font=f(True, 96), fill=TXT, anchor="mm")
    d.text((W / 2, 480), "Inteligente", font=f(True, 96), fill=CYAN, anchor="mm")
    d.text((W / 2, 580), "Demostración en vivo: VS Code · pruebas · GUI · Selenium", font=f(False, 40),
           fill=MUTED, anchor="mm")
    d.line((W / 2 - 300, 650, W / 2 + 300, 650), fill=PANEL, width=3)
    d.text((W / 2, 700), "Integrantes", font=f(False, 34), fill=MUTED, anchor="mm")
    integrantes(d, 765, 52)
    img.save(PORTADA)

    # Cierre
    img, d = base()
    d.text((W / 2, 380), "¡Gracias!", font=f(True, 170), fill=CYAN, anchor="mm")
    d.text((W / 2, 530), "Gracias por su atención", font=f(False, 50), fill=TXT, anchor="mm")
    integrantes(d, 680, 48)
    d.text((W / 2, 770), f"{MATERIA}  ·  {INSTITUCION}", font=f(False, 38), fill=MUTED, anchor="mm")
    img.save(CIERRE)


def generar_subtitulos() -> None:
    """Agrega portada y cierre, crea el .srt, quema los subtítulos y escribe el guion.

    La grabación cruda (``_demo_raw.mkv``) no se modifica: se le antepone la portada y se
    le añade el cierre, y los tiempos de cada paso se desplazan ``DUR_PORTADA`` segundos.
    """
    datos = json.loads(TIEMPOS.read_text(encoding="utf-8"))
    total_grab = datos["total"]
    pasos = [{"clave": "portada", "inicio": 0.0}]
    pasos += [{"clave": p["clave"], "inicio": p["inicio"] + DUR_PORTADA} for p in datos["pasos"]]
    pasos.append({"clave": "cierre", "inicio": DUR_PORTADA + total_grab})
    total = DUR_PORTADA + total_grab + DUR_CIERRE

    srt, guion, n = [], [], 1
    guion += ["# Guion de la demostración en vivo", "",
              f"*Generado por `video/grabar_demo.py` con los tiempos reales de la grabación. Narra: **{NARRADORA}**.*",
              "", f"- {MATERIA} · {INSTITUCION}",
              f"- Integrantes: {', '.join(INTEGRANTES)}",
              f"- Duración: **{int(total // 60)}:{int(total % 60):02}** (portada {DUR_PORTADA:.0f} s + "
              f"demostración + cierre {DUR_CIERRE:.0f} s)",
              "- Si la voz no cabe en un paso, recorten o alarguen la pausa en el editor; los tiempos son los de la pantalla.", ""]
    for i, paso in enumerate(pasos):
        ini = paso["inicio"]
        fin = pasos[i + 1]["inicio"] if i + 1 < len(pasos) else total
        texto = NARRACION[paso["clave"]]
        guion += [f"## {_ts(ini)[3:8]} – {_ts(fin)[3:8]} · {paso['clave']}", "", texto, ""]
        bloques = _bloques(texto)
        pesos = [len(b) for b in bloques]
        util_ini, util_fin = ini + 0.6, max(ini + 1.2, fin - 0.4)
        t = util_ini
        for b, w in zip(bloques, pesos):
            d = (util_fin - util_ini) * w / sum(pesos)
            # no dejar un subtítulo más de 7 s en pantalla aunque el paso sea largo
            srt += [str(n), f"{_ts(t)} --> {_ts(t + min(d, 7.0))}", b, ""]
            n += 1
            t += d
    SRT.write_text("\n".join(srt), encoding="utf-8")
    GUION.write_text("\n".join(guion), encoding="utf-8")

    _tarjetas()
    unir = (
        f"[0:v]format=yuv420p,setsar=1,fade=t=in:st=0:d=0.6,fade=t=out:st={DUR_PORTADA - 0.6}:d=0.6[p];"
        "[1:v]scale=1920:1080,fps=30,format=yuv420p,setsar=1,fade=t=in:st=0:d=0.5[g];"
        f"[2:v]format=yuv420p,setsar=1,fade=t=in:st=0:d=0.6,fade=t=out:st={DUR_CIERRE - 0.8}:d=0.8[c];"
        "[p][g][c]concat=n=3:v=1:a=0[v]"
    )
    entradas = ["-loop", "1", "-framerate", "30", "-t", str(DUR_PORTADA), "-i", PORTADA.name,
                "-i", GRABACION.name,
                "-loop", "1", "-framerate", "30", "-t", str(DUR_CIERRE), "-i", CIERRE.name]
    codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "30", "-an"]
    estilo = ("FontName=Arial,FontSize=15,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,"
              "BorderStyle=4,Outline=0,Shadow=0,MarginV=28")
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *entradas,
                    "-filter_complex", unir, "-map", "[v]", *codec, FINAL_SIN_SUBS.name], cwd=VIDEO, check=True)
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *entradas,
                    "-filter_complex", unir + f";[v]subtitles={SRT.name}:force_style='{estilo}'[s]",
                    "-map", "[s]", *codec, FINAL.name], cwd=VIDEO, check=True)
    print(f"Listo: {FINAL} ({int(total // 60)}:{int(total % 60):02})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ensayo", action="store_true", help="ejecutar sin grabar")
    ap.add_argument("--solo-subtitulos", action="store_true", help="rehacer subtítulos y video final")
    ap.add_argument("--gui", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.gui:
        demo_gui()
    elif a.solo_subtitulos:
        generar_subtitulos()
    else:
        ejecutar_demo(grabar=not a.ensayo)
        if not a.ensayo:
            generar_subtitulos()


if __name__ == "__main__":
    main()
