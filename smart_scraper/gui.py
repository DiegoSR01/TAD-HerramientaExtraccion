"""Interfaz gráfica Tkinter para diagnosticar y ejecutar tareas controladas.

Rol en la arquitectura: capa de presentación. Recoge la configuración del
usuario, la convierte en ``ScrapeConfig`` y delega en ``app``. Las tareas de
red se ejecutan en hilos secundarios para no congelar la ventana; los
resultados se muestran de vuelta en el hilo de Tkinter con ``root.after``.
Los encabezados autorizados se mantienen solo en memoria (campo enmascarado).
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .app import RunFailure, diagnose_config, load_profile_for_url, run_job
from .config import AcquisitionMethod, ScrapeConfig, parse_field_rules
from .inspector import InspectedPage


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
        self.root.geometry("940x800")
        self.output_directory = Path.cwd() / "output"
        self.inspected_page: InspectedPage | None = None
        self.inspected_url = ""
        self._build()

    def _build(self) -> None:
        """Crea y distribuye todos los controles (campos, opciones, botones y salida)."""
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(frame, text="URL a inspeccionar").grid(row=row, column=0, sticky="w")
        self.url = ttk.Entry(frame)
        self.url.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        row += 1

        ttk.Label(frame, text="Método").grid(row=row, column=0, sticky="w")
        self.method = ttk.Combobox(
            frame, values=[method.value for method in AcquisitionMethod], state="readonly"
        )
        self.method.set(AcquisitionMethod.REQUESTS.value)
        self.method.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        self.headless = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Navegador sin interfaz", variable=self.headless).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        ttk.Label(frame, text="Selector de registros (CSS)").grid(row=row, column=0, sticky="w")
        self.item_selector = ttk.Entry(frame)
        self.item_selector.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        row += 1

        ttk.Label(frame, text="Ruta de lista JSON").grid(row=row, column=0, sticky="w")
        self.json_path = ttk.Entry(frame)
        self.json_path.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        row += 1

        ttk.Label(frame, text="Campos (uno por línea: nombre=CSS::atributo; * requerido)").grid(
            row=row, column=0, columnspan=3, sticky="w"
        )
        row += 1
        self.fields = tk.Text(frame, height=6, wrap="none")
        self.fields.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=4)
        row += 1

        ttk.Label(frame, text="Selector de siguiente página (CSS)").grid(row=row, column=0, sticky="w")
        self.pagination_selector = ttk.Entry(frame)
        self.pagination_selector.grid(row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        row += 1

        ttk.Label(frame, text="Selector botón cargar más").grid(row=row, column=0, sticky="w")
        self.load_more_selector = ttk.Entry(frame)
        self.load_more_selector.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Label(frame, text="Clics máx.").grid(row=row, column=2, sticky="w")
        row += 1

        settings = ttk.Frame(frame)
        settings.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Label(settings, text="Registros máx.").pack(side="left")
        self.max_records = ttk.Spinbox(settings, from_=1, to=1000, width=8)
        self.max_records.set("250")
        self.max_records.pack(side="left", padx=(4, 14))
        ttk.Label(settings, text="Páginas máx.").pack(side="left")
        self.max_pages = ttk.Spinbox(settings, from_=1, to=10, width=6)
        self.max_pages.set("1")
        self.max_pages.pack(side="left", padx=(4, 14))
        ttk.Label(settings, text="Scrolls (0-5)").pack(side="left")
        self.scroll_steps = ttk.Spinbox(settings, from_=0, to=5, width=5)
        self.scroll_steps.set("0")
        self.scroll_steps.pack(side="left", padx=4)
        ttk.Label(settings, text="Clics cargar más (0-5)").pack(side="left", padx=(10, 0))
        self.load_more_clicks = ttk.Spinbox(settings, from_=0, to=5, width=5)
        self.load_more_clicks.set("0")
        self.load_more_clicks.pack(side="left", padx=4)
        ttk.Label(settings, text="Pausa (s)").pack(side="left", padx=(10, 0))
        self.delay = ttk.Spinbox(settings, from_=1, to=30, increment=0.5, width=6)
        self.delay.set("1.5")
        self.delay.pack(side="left", padx=4)
        row += 1

        ttk.Label(frame, text="Encabezados autorizados (JSON; se mantienen en memoria)").grid(
            row=row, column=0, columnspan=3, sticky="w"
        )
        row += 1
        self.headers = tk.Entry(frame, show="*")
        self.headers.grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        options = ttk.Frame(frame)
        options.grid(row=row, column=0, columnspan=3, sticky="ew")
        self.authorized_api = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options, text="Confirmo autorización del endpoint API", variable=self.authorized_api
        ).pack(side="left")
        ttk.Label(options, text="Formato").pack(side="left", padx=(16, 4))
        self.format_name = ttk.Combobox(
            options, values=["csv", "excel", "json", "sqlite", "postgresql", "mongodb"],
            state="readonly", width=14,
        )
        self.format_name.set("csv")
        self.format_name.pack(side="left")
        self.output_label = ttk.Label(options, text=str(self.output_directory))
        self.output_label.pack(side="left", padx=8)
        ttk.Button(options, text="Carpeta…", command=self._choose_directory).pack(side="right")
        row += 1

        actions = ttk.Frame(frame)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        self.inspect_button = ttk.Button(actions, text="1. Inspeccionar", command=self._inspect)
        self.inspect_button.pack(side="left")
        self.run_button = ttk.Button(actions, text="2. Extraer y guardar", command=self._run)
        self.run_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Cargar perfil del sitio", command=self._load_profile).pack(side="left")
        row += 1

        ttk.Label(frame, text="Diagnóstico, estado e informe de ejecución").grid(
            row=row, column=0, columnspan=3, sticky="w"
        )
        row += 1
        self.output = tk.Text(frame, height=17, wrap="word", state="disabled")
        self.output.grid(row=row, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(row, weight=1)

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
        """Botón "Inspeccionar": diagnostica la URL en un hilo aparte.

        Guarda la inspección para reutilizarla en la ejecución y muestra el
        diagnóstico (incluidas advertencias de CAPTCHA, autenticación o bloqueo).
        """
        try:
            config = self._config()
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Configuración no válida", str(exc))
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                page = diagnose_config(config)
                self.inspected_page = page
                self.inspected_url = config.url
                display = json.dumps(page.report.to_dict(), indent=2, ensure_ascii=False)
                self.root.after(0, self._show, display)
            except Exception as exc:
                self.root.after(0, self._show, f"Inspección fallida: {exc}")
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _run(self) -> None:
        """Botón "Extraer y guardar": ejecuta ``run_job`` en un hilo aparte.

        Reutiliza la inspección previa si la URL no cambió. Ante ``RunFailure``
        (incluidas paradas por CAPTCHA/401/403/429) muestra el informe con el error.
        """
        try:
            config = self._config()
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Configuración no válida", str(exc))
            return
        cached = self.inspected_page if self.inspected_url == config.url else None
        self._set_busy(True)

        def worker() -> None:
            try:
                outcome = run_job(config, self.output_directory, self.format_name.get(), cached)
                report = outcome.report
                display = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
                self.root.after(0, self._show, display)
            except RunFailure as exc:
                self.root.after(
                    0, self._show,
                    json.dumps(exc.outcome.report.to_dict(), indent=2, ensure_ascii=False),
                )
            except Exception as exc:
                self.root.after(0, self._show, f"Error: {exc}")
            finally:
                self.root.after(0, lambda: self._set_busy(False))

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
