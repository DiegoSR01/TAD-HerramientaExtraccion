"""Interfaz gráfica Tkinter para diagnosticar y ejecutar tareas controladas.

Rol en la arquitectura: capa de presentación. Recoge la configuración del
usuario, la convierte en ``ScrapeConfig`` y delega en ``app``. Las tareas de
red se ejecutan en hilos secundarios para no congelar la ventana; los
resultados y el progreso se muestran de vuelta en el hilo de Tkinter con
``root.after``. Incluye un panel de progreso con los 9 pasos del flujo, barra
de avance, tiempo transcurrido, escenario detectado y un registro de eventos
con marcas de tiempo. Los encabezados autorizados se mantienen solo en
memoria (campo enmascarado).
"""

from __future__ import annotations

import json
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .app import STEP_TITLES, RunFailure, diagnose_config, load_profile_for_url, run_job
from .config import AcquisitionMethod, ScrapeConfig, parse_field_rules
from .inspector import InspectedPage

# Estado de cada paso -> (icono, color)
STATUS_STYLE = {
    "pending": ("○", "#8a94a6"),
    "running": ("▶", "#1f6feb"),
    "done": ("✔", "#1a7f37"),
    "error": ("✖", "#cf222e"),
    "blocked": ("⛔", "#d97706"),
}
HEADER_BG = "#14213d"
ACCENT = "#1f6feb"
PAGE_BG = "#f3f5f9"
FONT = "Segoe UI"


class ScraperWindow:
    """Ventana principal de la aplicación.

    Mantiene la última página inspeccionada para reutilizarla al ejecutar y
    la carpeta de salida elegida por el usuario.
    """
    def __init__(self, root: tk.Tk):
        """Inicializa la ventana y construye sus controles.

        Args:
            root: ventana raíz de Tkinter.
        """
        self.root = root
        self.root.title("Web Scraper Inteligente")
        width = min(1700, max(1100, root.winfo_screenwidth() - 80))
        height = min(960, max(700, root.winfo_screenheight() - 100))
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height) // 3)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(1100, 680)
        self.output_directory = Path.cwd() / "output"
        self.inspected_page: InspectedPage | None = None
        self.inspected_url = ""
        self._started_at = 0.0
        self._timer_running = False
        self._step_states = ["pending"] * len(STEP_TITLES)
        self._configure_style()
        self._build()

    # ------------------------------------------------------------------ estilo
    def _configure_style(self) -> None:
        """Aplica el tema ``clam`` y estilos modernos (colores, tipografía, botones)."""
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self.root.configure(bg=PAGE_BG)
        style.configure(".", font=(FONT, 10), background=PAGE_BG)
        style.configure("TFrame", background=PAGE_BG)
        style.configure("TLabel", background=PAGE_BG)
        style.configure("TCheckbutton", background=PAGE_BG)
        style.configure("TLabelframe", background=PAGE_BG, bordercolor="#c9d1de")
        style.configure("TLabelframe.Label", background=PAGE_BG, foreground=HEADER_BG,
                        font=(FONT, 10, "bold"))
        style.configure("TButton", padding=(12, 6))
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=(FONT, 10, "bold"), padding=(16, 8))
        style.map("Accent.TButton", background=[("active", "#1858b8"), ("disabled", "#9db7e0")],
                  foreground=[("disabled", "#eef2fa")])
        style.configure("Run.TButton", background="#1a7f37", foreground="white",
                        font=(FONT, 10, "bold"), padding=(16, 8))
        style.map("Run.TButton", background=[("active", "#146c2e"), ("disabled", "#9fcfae")],
                  foreground=[("disabled", "#eef2fa")])
        style.configure("Step.Horizontal.TProgressbar", troughcolor="#dde3ee", background=ACCENT, thickness=14)

    # --------------------------------------------------------------- construcción
    def _build(self) -> None:
        """Crea el encabezado, el panel de configuración y el panel de progreso."""
        header = tk.Frame(self.root, bg=HEADER_BG)
        header.pack(fill="x")
        tk.Label(header, text="Web Scraper Inteligente", bg=HEADER_BG, fg="white",
                 font=(FONT, 20, "bold")).pack(side="left", padx=20, pady=(12, 12))
        tk.Label(header, text="Diagnóstico · Extracción responsable · Detección de cambios",
                 bg=HEADER_BG, fg="#b8c4de", font=(FONT, 11)).pack(side="left", padx=8)

        body = ttk.Frame(self.root, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=5, uniform="cols")
        body.columnconfigure(1, weight=4, uniform="cols")
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_config(left)
        self._build_progress(right)

    def _build_config(self, parent: ttk.Frame) -> None:
        """Panel izquierdo: configuración agrupada en secciones y botones de acción."""
        parent.columnconfigure(0, weight=1)

        # --- Objetivo
        target = ttk.LabelFrame(parent, text=" 1. Objetivo ", padding=10)
        target.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        target.columnconfigure(1, weight=1)
        ttk.Label(target, text="URL a inspeccionar").grid(row=0, column=0, sticky="w")
        self.url = ttk.Entry(target)
        self.url.grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        ttk.Label(target, text="Método").grid(row=1, column=0, sticky="w")
        self.method = ttk.Combobox(
            target, values=[method.value for method in AcquisitionMethod], state="readonly"
        )
        self.method.set(AcquisitionMethod.REQUESTS.value)
        self.method.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        self.headless = tk.BooleanVar(value=True)
        ttk.Checkbutton(target, text="Navegador sin interfaz", variable=self.headless).grid(
            row=1, column=2, sticky="w"
        )

        # --- Selección de datos
        selection = ttk.LabelFrame(parent, text=" 2. Selección de datos ", padding=10)
        selection.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        selection.columnconfigure(1, weight=1)
        ttk.Label(selection, text="Selector de registros (CSS)").grid(row=0, column=0, sticky="w")
        self.item_selector = ttk.Entry(selection)
        self.item_selector.grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(selection, text="Ruta de lista JSON").grid(row=1, column=0, sticky="w")
        self.json_path = ttk.Entry(selection)
        self.json_path.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(selection, text="Campos (uno por línea: nombre=CSS::atributo; * requerido)").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.fields = tk.Text(selection, height=7, wrap="none", font=("Consolas", 10),
                              relief="solid", borderwidth=1)
        self.fields.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=4)
        selection.rowconfigure(3, weight=1)
        parent.rowconfigure(1, weight=1)

        # --- Navegación y límites
        limits = ttk.LabelFrame(parent, text=" 3. Navegación y límites ", padding=10)
        limits.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        limits.columnconfigure(1, weight=1)
        ttk.Label(limits, text="Selector de siguiente página (CSS)").grid(row=0, column=0, sticky="w")
        self.pagination_selector = ttk.Entry(limits)
        self.pagination_selector.grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(limits, text="Selector botón cargar más").grid(row=1, column=0, sticky="w")
        self.load_more_selector = ttk.Entry(limits)
        self.load_more_selector.grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        settings = ttk.Frame(limits)
        settings.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(settings, text="Registros máx.").pack(side="left")
        self.max_records = ttk.Spinbox(settings, from_=1, to=1000, width=7)
        self.max_records.set("250")
        self.max_records.pack(side="left", padx=(4, 12))
        ttk.Label(settings, text="Páginas máx.").pack(side="left")
        self.max_pages = ttk.Spinbox(settings, from_=1, to=10, width=5)
        self.max_pages.set("1")
        self.max_pages.pack(side="left", padx=(4, 12))
        ttk.Label(settings, text="Scrolls (0-5)").pack(side="left")
        self.scroll_steps = ttk.Spinbox(settings, from_=0, to=5, width=4)
        self.scroll_steps.set("0")
        self.scroll_steps.pack(side="left", padx=(4, 12))
        ttk.Label(settings, text="Clics cargar más (0-5)").pack(side="left")
        self.load_more_clicks = ttk.Spinbox(settings, from_=0, to=5, width=4)
        self.load_more_clicks.set("0")
        self.load_more_clicks.pack(side="left", padx=(4, 12))
        ttk.Label(settings, text="Pausa (s)").pack(side="left")
        self.delay = ttk.Spinbox(settings, from_=1, to=30, increment=0.5, width=5)
        self.delay.set("1.5")
        self.delay.pack(side="left", padx=4)

        # --- Seguridad y salida
        security = ttk.LabelFrame(parent, text=" 4. Acceso autorizado y salida ", padding=10)
        security.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        security.columnconfigure(0, weight=1)
        ttk.Label(security, text="Encabezados autorizados (JSON; se mantienen en memoria)").grid(
            row=0, column=0, sticky="w"
        )
        self.headers = tk.Entry(security, show="*", relief="solid", borderwidth=1)
        self.headers.grid(row=1, column=0, sticky="ew", pady=4)
        options = ttk.Frame(security)
        options.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        self.authorized_api = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options, text="Confirmo autorización del endpoint API", variable=self.authorized_api
        ).pack(side="left")
        ttk.Label(options, text="Formato").pack(side="left", padx=(16, 4))
        self.format_name = ttk.Combobox(
            options, values=["csv", "excel", "json", "sqlite", "postgresql", "mongodb"],
            state="readonly", width=12,
        )
        self.format_name.set("csv")
        self.format_name.pack(side="left")
        ttk.Button(options, text="Carpeta…", command=self._choose_directory).pack(side="right")
        self.output_label = ttk.Label(options, text=str(self.output_directory), foreground="#4a5568")
        self.output_label.pack(side="right", padx=8)

        # --- Acciones
        actions = ttk.Frame(parent)
        actions.grid(row=4, column=0, sticky="ew", pady=(4, 0))
        self.inspect_button = ttk.Button(
            actions, text="1. Inspeccionar", style="Accent.TButton", command=self._inspect
        )
        self.inspect_button.pack(side="left")
        self.run_button = ttk.Button(
            actions, text="2. Extraer y guardar", style="Run.TButton", command=self._run
        )
        self.run_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Cargar perfil del sitio", command=self._load_profile).pack(side="left")

    def _build_progress(self, parent: ttk.Frame) -> None:
        """Panel derecho: progreso del flujo (barra, pasos, escenario) y registro de salida."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        panel = ttk.LabelFrame(parent, text=" Progreso del flujo ", padding=10)
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        panel.columnconfigure(0, weight=1)

        top = ttk.Frame(panel)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(
            top, style="Step.Horizontal.TProgressbar", mode="determinate", maximum=100
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_text = ttk.Label(top, text="0 / 9", font=(FONT, 10, "bold"), width=6)
        self.progress_text.grid(row=0, column=1, padx=(8, 0))
        self.elapsed_label = ttk.Label(top, text="⏱ 00:00", font=(FONT, 10), width=9)
        self.elapsed_label.grid(row=0, column=2)

        self.step_icons: list[tk.Label] = []
        self.step_names: list[tk.Label] = []
        stepper = tk.Frame(panel, bg="white", highlightbackground="#c9d1de", highlightthickness=1)
        stepper.grid(row=1, column=0, sticky="ew", pady=8)
        for index, title in enumerate(STEP_TITLES, start=1):
            icon_text, color = STATUS_STYLE["pending"]
            icon = tk.Label(stepper, text=icon_text, fg=color, bg="white", font=(FONT, 13), width=3)
            icon.grid(row=index - 1, column=0, sticky="w", padx=(6, 0))
            name = tk.Label(stepper, text=f"{index}. {title}", fg=color, bg="white",
                            font=(FONT, 11), anchor="w")
            name.grid(row=index - 1, column=1, sticky="ew", padx=4, pady=1)
            self.step_icons.append(icon)
            self.step_names.append(name)
        stepper.columnconfigure(1, weight=1)

        self.detail_label = tk.Label(
            panel, text="Listo. Ingresa una URL y pulsa «1. Inspeccionar».", anchor="w",
            justify="left", wraplength=600, bg=PAGE_BG, fg="#1f2937", font=(FONT, 10),
        )
        self.detail_label.grid(row=2, column=0, sticky="ew")
        self.scenario_label = tk.Label(
            panel, text="Escenario detectado / Estrategia: —", anchor="w", justify="left",
            wraplength=600, bg="#e8f0fe", fg=HEADER_BG, font=(FONT, 11, "bold"), padx=8, pady=6,
        )
        self.scenario_label.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        log_frame = ttk.LabelFrame(parent, text=" Registro de eventos, diagnóstico e informe ", padding=6)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.output = tk.Text(log_frame, height=12, wrap="word", state="disabled",
                              font=("Consolas", 10), relief="flat", bg="#0f172a", fg="#e2e8f0")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        for status, (_, color) in STATUS_STYLE.items():
            self.output.tag_configure(status, foreground={
                "pending": "#94a3b8", "running": "#7cb7ff", "done": "#6ee7a0",
                "error": "#ff8a8a", "blocked": "#fbbf24",
            }[status])
        self.output.tag_configure("time", foreground="#64748b")

    # ------------------------------------------------------------------ progreso
    def _reset_progress(self) -> None:
        """Deja los 9 pasos en pendiente y reinicia barra, escenario, detalle y temporizador."""
        self._step_states = ["pending"] * len(STEP_TITLES)
        for index in range(len(STEP_TITLES)):
            self._paint_step(index, "pending")
        self.progress_bar.configure(value=0)
        self.progress_text.configure(text=f"0 / {len(STEP_TITLES)}")
        self.detail_label.configure(text="Iniciando...", fg="#1f2937")
        self.scenario_label.configure(text="Escenario detectado / Estrategia: —",
                                      bg="#e8f0fe", fg=HEADER_BG)
        self._started_at = time.monotonic()
        self.elapsed_label.configure(text="⏱ 00:00")

    def _paint_step(self, index: int, status: str) -> None:
        """Aplica icono y color del estado ``status`` al paso ``index`` (base 0)."""
        icon, color = STATUS_STYLE[status]
        self.step_icons[index].configure(text=icon, fg=color)
        self.step_names[index].configure(fg=color, font=(FONT, 11, "bold" if status != "pending" else "normal"))

    def _progress_callback(self, step: int, total: int, title: str, detail: str, status: str) -> None:
        """Callback de ``app`` (hilo de trabajo): reenvía el evento al hilo de Tkinter."""
        self.root.after(0, self._on_progress, step, total, title, detail, status)

    def _on_progress(self, step: int, total: int, title: str, detail: str, status: str) -> None:
        """Actualiza stepper, barra, detalle, escenario y registro (hilo de Tkinter)."""
        index = step - 1
        self._step_states[index] = status
        self._paint_step(index, status)
        finished = sum(1 for state in self._step_states if state == "done")
        partial = 0.5 if status == "running" else 0
        self.progress_bar.configure(value=min(100, (finished + partial) * 100 / total))
        self.progress_text.configure(text=f"{finished} / {total}")
        color = STATUS_STYLE[status][1]
        first_line = detail.splitlines()[0] if detail else ""
        self.detail_label.configure(text=f"Paso {step}: {title} — {first_line}", fg=color)
        if step == 3 and status in {"done", "blocked"}:
            lines = detail.splitlines()
            summary = lines[0].replace("Escenario:", "Escenario detectado:", 1).replace(
                "| Estrategia recomendada:", "/ Estrategia:", 1)
            reason = f"\n{lines[1]}" if len(lines) > 1 else ""
            if status == "blocked":
                self.scenario_label.configure(
                    text=f"⛔ INCIDENCIA — {summary}{reason}", bg="#fff4e5", fg="#b45309")
            else:
                self.scenario_label.configure(text=f"{summary}{reason}", bg="#e6f6ec", fg="#14532d")
        label = f"[{step}/{total}] {title}: " + detail.replace("\n", " | ")
        self._log(label, status)

    def _log(self, message: str, tag: str = "running") -> None:
        """Añade una línea con marca de tiempo al registro (no borra el contenido previo)."""
        self.output.configure(state="normal")
        self.output.insert("end", datetime.now().strftime("[%H:%M:%S] "), "time")
        self.output.insert("end", f"{STATUS_STYLE.get(tag, ('', ''))[0]} {message}\n", tag)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _tick(self) -> None:
        """Actualiza el tiempo transcurrido mientras hay una tarea en curso."""
        if not self._timer_running:
            return
        elapsed = int(time.monotonic() - self._started_at)
        self.elapsed_label.configure(text=f"⏱ {elapsed // 60:02d}:{elapsed % 60:02d}")
        self.root.after(250, self._tick)

    def _start_task(self, name: str) -> None:
        """Prepara la interfaz para una tarea: limpia el registro, reinicia el progreso y el reloj."""
        self._set_busy(True)
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._reset_progress()
        self._log(f"Inicio: {name}", "running")
        self._timer_running = True
        self._tick()

    def _finish_task(self) -> None:
        """Detiene el reloj y habilita los botones."""
        self._timer_running = False
        elapsed = int(time.monotonic() - self._started_at)
        self.elapsed_label.configure(text=f"⏱ {elapsed // 60:02d}:{elapsed % 60:02d}")
        self._set_busy(False)

    def _config(self) -> ScrapeConfig:
        """Construye y valida un ``ScrapeConfig`` desde los controles.

        Returns:
            Configuración validada.

        Raises:
            ValueError: si algún valor numérico, campo o encabezado no es válido.
            json.JSONDecodeError: si los encabezados no son JSON válido.
        """
        raw_headers = self.headers.get().strip()
        headers = json.loads(raw_headers) if raw_headers else {}
        if not isinstance(headers, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()
        ):
            raise ValueError("Los encabezados deben ser un objeto JSON de cadenas.")
        config = ScrapeConfig(
            url=self.url.get().strip(),
            method=AcquisitionMethod(self.method.get()),
            item_selector=self.item_selector.get().strip(),
            fields=parse_field_rules(self.fields.get("1.0", "end")),
            json_records_path=self.json_path.get().strip(),
            pagination_selector=self.pagination_selector.get().strip(),
            load_more_selector=self.load_more_selector.get().strip(),
            load_more_clicks=int(self.load_more_clicks.get()),
            max_records=int(self.max_records.get()),
            max_pages=int(self.max_pages.get()),
            delay_seconds=float(self.delay.get()),
            scroll_steps=int(self.scroll_steps.get()),
            headless=self.headless.get(),
            authorized_api=self.authorized_api.get(),
            headers=headers,
        )
        config.validate()
        return config

    def _inspect(self) -> None:
        """Botón "Inspeccionar": ejecuta los pasos 1 a 3 en un hilo aparte.

        Guarda la inspección para reutilizarla en la ejecución y muestra el
        diagnóstico (incluidas advertencias de CAPTCHA, autenticación o bloqueo).
        """
        try:
            config = self._config()
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Configuración no válida", str(exc))
            return
        self._start_task(f"inspección de {config.url}")

        def worker() -> None:
            try:
                page = diagnose_config(config, progress=self._progress_callback)
                self.inspected_page = page
                self.inspected_url = config.url
                display = json.dumps(page.report.to_dict(), indent=2, ensure_ascii=False)
                self.root.after(0, self._append, display)
            except Exception as exc:
                self.root.after(0, self._log, f"Inspección fallida: {exc}", "error")
            finally:
                self.root.after(0, self._finish_task)

        threading.Thread(target=worker, daemon=True).start()

    def _run(self) -> None:
        """Botón "Extraer y guardar": ejecuta ``run_job`` (9 pasos) en un hilo aparte.

        Reutiliza la inspección previa si la URL no cambió. Ante ``RunFailure``
        (incluidas paradas por CAPTCHA/401/403/429) muestra el informe con el error.
        """
        try:
            config = self._config()
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Configuración no válida", str(exc))
            return
        cached = self.inspected_page if self.inspected_url == config.url else None
        self._start_task(f"extracción de {config.url}")

        def worker() -> None:
            try:
                outcome = run_job(
                    config, self.output_directory, self.format_name.get(), cached,
                    progress=self._progress_callback,
                )
                display = json.dumps(outcome.report.to_dict(), indent=2, ensure_ascii=False)
                self.root.after(0, self._append, display)
            except RunFailure as exc:
                self.root.after(
                    0, self._append,
                    json.dumps(exc.outcome.report.to_dict(), indent=2, ensure_ascii=False),
                )
            except Exception as exc:
                self.root.after(0, self._log, f"Error: {exc}", "error")
            finally:
                self.root.after(0, self._finish_task)

        threading.Thread(target=worker, daemon=True).start()

    def _load_profile(self) -> None:
        """Carga el perfil guardado del host y rellena los controles.

        Credenciales y autorización API no se restauran; deben ingresarse de nuevo.
        """
        try:
            config = load_profile_for_url(self.output_directory / "profiles", self.url.get().strip())
            if config is None:
                messagebox.showinfo("Perfil", "No hay un perfil guardado para este host.")
                return
            self.method.set(config.method.value)
            self.item_selector.delete(0, "end")
            self.item_selector.insert(0, config.item_selector)
            self.json_path.delete(0, "end")
            self.json_path.insert(0, config.json_records_path)
            self.fields.delete("1.0", "end")
            self.fields.insert(
                "1.0",
                "\n".join(
                    f"{rule.name}{'*' if rule.required else ''}={rule.selector}"
                    f"{'::' + rule.attribute if rule.attribute else ''}"
                    for rule in config.fields
                ),
            )
            self.pagination_selector.delete(0, "end")
            self.pagination_selector.insert(0, config.pagination_selector)
            self.load_more_selector.delete(0, "end")
            self.load_more_selector.insert(0, config.load_more_selector)
            self.load_more_clicks.set(str(config.load_more_clicks))
            self._show("Perfil cargado. Las credenciales y la autorización API deben ingresarse de nuevo.")
        except Exception as exc:
            messagebox.showerror("Perfil", str(exc))

    def _choose_directory(self) -> None:
        """Permite elegir la carpeta de salida y descarta la inspección en caché."""
        selected = filedialog.askdirectory(initialdir=self.output_directory)
        if selected:
            self.output_directory = Path(selected)
            self.output_label.configure(text=selected)
            self.inspected_page = None

    def _set_busy(self, busy: bool) -> None:
        """Habilita o deshabilita los botones de acción mientras hay una tarea en curso."""
        state = "disabled" if busy else "normal"
        self.inspect_button.configure(state=state)
        self.run_button.configure(state=state)

    def _append(self, text: str) -> None:
        """Añade ``text`` al final del panel de salida (de solo lectura)."""
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def _show(self, text: str) -> None:
        """Reemplaza el contenido del panel de salida (de solo lectura) con ``text``."""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")


def main() -> None:
    """Crea la ventana raíz y arranca el bucle de eventos de Tkinter."""
    root = tk.Tk()
    ScraperWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
