"""Adquisición de contenido: HTTP (Requests), Selenium, Playwright y API autorizada.

Rol en la arquitectura: módulo de adquisición/navegación. Obtiene el HTML o
JSON de la página (``acquire_page``), delega la selección de datos en
``selection`` (``extract_page``) y gestiona la paginación acotada
(``scrape``). Con Selenium o Playwright controla un navegador real: espera la
carga, hace clic en "cargar más" y se desplaza un número limitado de veces.

Seguridad: ante formularios de autenticación o respuestas 401/403/429 se
lanza ``AccessRestrictionError`` y se detiene la navegación. Ante un CAPTCHA
con navegador real y un canal hacia la interfaz, la extracción se pausa para
que una persona lo resuelva a mano (``intervencion``); sin ese canal, o en modo
Requests/API, se detiene igual que antes. El módulo nunca intenta resolver ni
evadir esas restricciones. Solo se sigue
paginación del mismo host y siempre con límites de páginas, registros y bytes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .config import AcquisitionMethod, ScrapeConfig
from .inspector import (
    MAX_HTML_BYTES,
    InspectionError,
    InspectedPage,
    InspectionReport,
    detectar_captcha,
    diagnose,
    inspect_url,
)
from .autoselect import EstructuraDetectada, detectar_estructura
from .intervencion import ExtraccionCancelada, IntervencionHumana, PaginaOmitida, Resultado
from .selection import parse_json_body, select_html, select_json


class AccessRestrictionError(RuntimeError):
    """Señal de bloqueo, CAPTCHA o autenticación que requiere acción legítima.

    Cuando se lanza, la ejecución se detiene y se informa al usuario; no se
    reintenta ni se intenta eludir la restricción.
    """


@dataclass
class AcquisitionResult:
    """Resultado de ``scrape``.

    Atributos:
        records: registros crudos extraídos (sin limpiar).
        final_url: última URL visitada.
        methods_used: métodos de adquisición empleados.
        pages_visited: número de páginas procesadas.
        skipped_urls: páginas omitidas por CAPTCHA (decisión del usuario o tiempo agotado).
        cancelled: ``True`` si el usuario canceló la extracción desde el aviso de CAPTCHA.
    """
    records: list[dict[str, Any]]
    final_url: str
    methods_used: list[str] = field(default_factory=list)
    pages_visited: int = 0
    skipped_urls: list[str] = field(default_factory=list)
    cancelled: bool = False
    estructura: EstructuraDetectada | None = None


def acquire_page(config: ScrapeConfig, inspected: InspectedPage | None = None) -> str | bytes:
    """Obtiene el cuerpo de una página según el método configurado.

    Con Requests/API reutiliza la inspección previa (o hace una solicitud GET
    acotada); con Selenium/Playwright abre un navegador. Se detiene si el
    diagnóstico marca bloqueo (401/403/429/CAPTCHA).

    Args:
        config: configuración de la ejecución.
        inspected: página ya inspeccionada, para no repetir la solicitud.

    Returns:
        HTML (``str``) renderizado o cuerpo crudo (``bytes``) de la respuesta.

    Raises:
        AccessRestrictionError: si el acceso está restringido.
        InspectionError: si el sitio responde HTTP >= 400 o excede el tamaño.
        ValueError: si el contenido no coincide con el método elegido o el
            método no está soportado.
    """
    if inspected and inspected.report.blocked:
        raise AccessRestrictionError("; ".join(inspected.report.warnings) or "Acceso restringido.")
    if config.method in {AcquisitionMethod.REQUESTS, AcquisitionMethod.API}:
        page = inspected or inspect_url(config.url, config.timeout_seconds, config.headers)
        if page.report.blocked:
            raise AccessRestrictionError("; ".join(page.report.warnings) or "Acceso restringido.")
        if page.report.status_code >= 400:
            raise InspectionError(f"El sitio respondió HTTP {page.report.status_code}; no se extrajeron datos.")
        if config.method == AcquisitionMethod.API and "json" not in page.report.content_type.lower():
            try:
                parse_json_body(page.body, page.encoding)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("El endpoint autorizado no devolvió un documento JSON válido.") from exc
        if (
            config.method == AcquisitionMethod.REQUESTS
            and page.report.content_type
            and not any(token in page.report.content_type.lower() for token in ("text/html", "application/xhtml"))
        ):
            raise ValueError("La respuesta no es HTML; selecciona el método API si es JSON.")
        return page.body
    if config.method == AcquisitionMethod.SELENIUM:
        return _acquire_selenium(config)
    if config.method == AcquisitionMethod.PLAYWRIGHT:
        return _acquire_playwright(config)
    raise ValueError(f"Método de adquisición no soportado: {config.method}")


def extract_page(config: ScrapeConfig, body: str | bytes) -> list[dict[str, Any]]:
    """Convierte el cuerpo de una página en registros usando las reglas de campos.

    Para API interpreta JSON; para HTML verifica que no haya CAPTCHA y aplica
    los selectores CSS.

    Args:
        config: configuración con selectores, campos y límite de registros.
        body: contenido obtenido por ``acquire_page``.

    Returns:
        Lista de registros (diccionarios nombre-valor).

    Raises:
        AccessRestrictionError: si se detecta un CAPTCHA/challenge.
        ValueError: si el JSON o la ruta de registros no son válidos.
    """
    if config.method == AcquisitionMethod.API:
        payload = parse_json_body(body if isinstance(body, bytes) else body.encode("utf-8"))
        return select_json(payload, config.fields, config.json_records_path, config.max_records)
    html = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    report = diagnose(config.url, 200, "text/html", html.encode("utf-8"))
    if report.captcha_detected:
        raise AccessRestrictionError(_CAPTCHA_MSG)
    return select_html(html, config.item_selector, config.fields, config.max_records)


BROWSER_METHODS = {AcquisitionMethod.SELENIUM, AcquisitionMethod.PLAYWRIGHT}
_CAPTCHA_MSG = "Se detectó un CAPTCHA/challenge; no se intentará resolver."
_AUTH_MSG = "Se detectó un formulario de autenticación; se detuvo el navegador."


def captcha_atendible(report: InspectionReport, method: AcquisitionMethod, hay_intervencion: bool) -> bool:
    """Indica si un bloqueo por CAPTCHA puede pasar a intervención humana.

    Solo aplica con navegador real (Selenium/Playwright), con un canal hacia la
    interfaz y cuando el bloqueo se debe únicamente al CAPTCHA (no a 401/403/429).
    En modo Requests/API no hay ventana donde resolverlo: se sigue deteniendo.
    """
    return (
        hay_intervencion
        and method in BROWSER_METHODS
        and report.captcha_detected
        and report.status_code not in {401, 403, 429}
    )


class _BrowserSession:
    """Navegador que permanece abierto durante toda la ejecución.

    Conserva sesión, cookies y página actual entre páginas y durante la pausa
    por CAPTCHA. Las subclases implementan las operaciones de Selenium o
    Playwright; aquí está el flujo común de ``adquirir`` y la vigilancia.
    """

    def __init__(self, config: ScrapeConfig, intervencion: IntervencionHumana | None = None):
        self.config = config
        self.headless = config.headless
        self.intervencion = intervencion
        self._lanzar(self.headless)
        if intervencion is not None:
            intervencion.vincular(self._captcha_presente, self.asegurar_visible)

    # --- operaciones propias de cada motor -------------------------------
    def _lanzar(self, headless: bool) -> None:
        raise NotImplementedError

    def _navegar(self, url: str) -> None:
        raise NotImplementedError

    def _documento(self) -> object:
        """Objeto que entiende ``detectar_captcha`` (driver o página)."""
        raise NotImplementedError

    def html(self) -> str:
        raise NotImplementedError

    def _clic_cargar_mas(self) -> bool:
        raise NotImplementedError

    def _desplazar(self) -> None:
        raise NotImplementedError

    def _relanzar_visible(self) -> None:
        raise NotImplementedError

    def cerrar(self) -> None:
        raise NotImplementedError

    # --- flujo común ------------------------------------------------------
    def _captcha_presente(self) -> bool:
        return detectar_captcha(self._documento())

    def asegurar_visible(self) -> bool:
        """Relanza en modo visible (copiando cookies) si estaba en headless.

        Returns:
            ``True`` si hubo que relanzar el navegador.
        """
        if not self.headless:
            return False
        self._relanzar_visible()
        self.headless = False
        return True

    def html_seguro(self) -> str:
        """HTML actual, o cadena vacía si el navegador ya no responde."""
        try:
            return self.html()
        except Exception:
            return ""

    def vigilar(self, url: str) -> None:
        """Revisa la página tras cada navegación, clic, scroll o envío de formulario.

        Sin intervención humana se detiene como antes. Con intervención, pausa
        con ``esperar_intervencion_humana`` y continúa solo si el CAPTCHA se resolvió.

        Raises:
            AccessRestrictionError: CAPTCHA sin intervención disponible, o autenticación.
            PaginaOmitida: el usuario omitió la página o venció el tiempo de espera.
            ExtraccionCancelada: el usuario canceló la extracción.
        """
        if self._captcha_presente():
            if self.intervencion is None:
                raise AccessRestrictionError(_CAPTCHA_MSG)
            resultado = self.intervencion.esperar_intervencion_humana(url)
            if resultado == Resultado.CANCELADO:
                raise ExtraccionCancelada(url)
            if resultado in {Resultado.OMITIDO, Resultado.EXPIRADO}:
                raise PaginaOmitida(url, resultado)
        if diagnose(url, 200, "text/html", self.html().encode("utf-8")).authentication_detected:
            raise AccessRestrictionError(_AUTH_MSG)

    def adquirir(self, url: str) -> str:
        """Abre ``url`` en el navegador ya lanzado y devuelve el DOM final.

        Pasos: navegar, vigilar, clics acotados en "cargar más" y
        desplazamientos acotados (vigilando tras cada uno) y leer el DOM.

        Raises:
            InspectionError: si el DOM supera ``MAX_HTML_BYTES``.
        """
        self._navegar(url)
        self.vigilar(url)
        for _ in range(self.config.load_more_clicks):
            if not self._clic_cargar_mas():
                break  # ya no hay botón: no quedan más datos por cargar
            self.vigilar(url)
        for _ in range(self.config.scroll_steps):
            self._desplazar()
            self.vigilar(url)
        html = self.html()
        if len(html.encode("utf-8")) > MAX_HTML_BYTES:
            raise InspectionError(f"El DOM renderizado supera el límite de {MAX_HTML_BYTES} bytes.")
        return html


class _SeleniumSession(_BrowserSession):
    """Sesión de Selenium/Chrome."""

    def __init__(self, config: ScrapeConfig, intervencion: IntervencionHumana | None = None):
        # Importación diferida: Selenium es opcional y solo se exige si se usa este método.
        try:
            from selenium import webdriver
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise RuntimeError("Instala Selenium con `pip install selenium`.") from exc
        self._webdriver = webdriver
        self._wait = WebDriverWait
        super().__init__(config, intervencion)

    def _lanzar(self, headless: bool) -> None:
        options = self._webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")  # headless moderno de Chrome
        options.add_argument("--disable-notifications")
        options.add_argument("--window-size=1280,900")
        # Selenium Manager localiza/descarga el chromedriver adecuado.
        self.driver = self._webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(self.config.timeout_seconds)

    def _navegar(self, url: str) -> None:
        self.driver.get(url)
        # Espera explícita a que el documento esté "interactive" o "complete".
        self._wait(self.driver, self.config.timeout_seconds).until(
            lambda browser: browser.execute_script("return document.readyState") in {"interactive", "complete"}
        )

    def _documento(self) -> object:
        return self.driver

    def html(self) -> str:
        return self.driver.page_source

    def _clic_cargar_mas(self) -> bool:
        buttons = self.driver.find_elements("css selector", self.config.load_more_selector)
        if not buttons:
            return False
        buttons[0].click()
        time.sleep(1)  # pausa cortés para dejar que cargue el contenido
        return True

    def _desplazar(self) -> None:
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)

    def _relanzar_visible(self) -> None:
        # Chrome no puede salir de headless en caliente: se relanza visible,
        # se copian las cookies y se vuelve a abrir la misma URL.
        url = self.driver.current_url
        cookies = self.driver.get_cookies()
        self.driver.quit()
        self._lanzar(False)
        self.driver.get(url)
        for cookie in cookies:
            try:
                self.driver.add_cookie(cookie)
            except Exception:
                pass  # cookies de otro dominio o expiradas
        self.driver.get(url)

    def cerrar(self) -> None:
        self.driver.quit()


class _PlaywrightSession(_BrowserSession):
    """Sesión de Playwright/Chromium."""

    def __init__(self, config: ScrapeConfig, intervencion: IntervencionHumana | None = None):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Instala Playwright con `pip install '.[playwright]'` y `playwright install chromium`."
            ) from exc
        self._contexto = sync_playwright()
        self._playwright = self._contexto.__enter__()
        try:
            super().__init__(config, intervencion)
        except Exception:
            self._contexto.__exit__(None, None, None)
            raise

    def _lanzar(self, headless: bool) -> None:
        self.browser = self._playwright.chromium.launch(headless=headless)
        self.page = self.browser.new_page(extra_http_headers=self.config.headers)

    def _navegar(self, url: str) -> None:
        response = self.page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_seconds * 1000)
        if response and response.status >= 400:
            raise AccessRestrictionError(f"El sitio respondió HTTP {response.status}; se detuvo la navegación.")

    def _documento(self) -> object:
        return self.page

    def html(self) -> str:
        return self.page.content()

    def _clic_cargar_mas(self) -> bool:
        button = self.page.locator(self.config.load_more_selector)
        if not button.count():
            return False
        button.first.click(timeout=self.config.timeout_seconds * 1000)
        self.page.wait_for_timeout(1000)
        return True

    def _desplazar(self) -> None:
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.page.wait_for_timeout(1000)

    def _relanzar_visible(self) -> None:
        url = self.page.url
        cookies = self.page.context.cookies()
        self.browser.close()
        self._lanzar(False)
        if cookies:
            self.page.context.add_cookies(cookies)
        self.page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_seconds * 1000)

    def cerrar(self) -> None:
        try:
            self.browser.close()
        finally:
            self._contexto.__exit__(None, None, None)


def _abrir_sesion(config: ScrapeConfig, intervencion: IntervencionHumana | None) -> _BrowserSession:
    """Lanza el navegador del método configurado."""
    if config.method == AcquisitionMethod.SELENIUM:
        return _SeleniumSession(config, intervencion)
    return _PlaywrightSession(config, intervencion)


def scrape(
    config: ScrapeConfig,
    initial_page: InspectedPage | None = None,
    on_page: Callable[[int, str, int], None] | None = None,
    intervencion: IntervencionHumana | None = None,
    on_detect: Callable[[EstructuraDetectada | None], None] | None = None,
) -> AcquisitionResult:
    """Extrae hasta el límite configurado y solo sigue paginación del mismo host.

    Recorre como máximo ``max_pages`` páginas, evita URL repetidas, espera
    ``delay_seconds`` entre páginas y se detiene al alcanzar ``max_records`` o si
    el enlace de siguiente página apunta a otro host. Con Selenium/Playwright
    usa un único navegador para todas las páginas (conserva sesión y cookies).

    Si hay ``intervencion`` y aparece un CAPTCHA en el navegador, la extracción
    se pausa hasta que una persona decide: *Continuar* (reanuda en la misma
    página), *Omitir* (registra la URL en ``skipped_urls`` y sigue con la
    siguiente página si el DOM actual tiene enlace) o *Cancelar* (marca
    ``cancelled`` y devuelve lo extraído hasta ese momento).

    Args:
        config: configuración (se valida al inicio).
        initial_page: inspección ya hecha de la primera página, si existe.
        on_page: callback opcional ``on_page(numero_pagina, url, registros_acumulados)``
            invocado tras procesar cada página (para mostrar progreso).
        intervencion: controlador de intervención humana ante CAPTCHA (opcional).
        on_detect: callback con la estructura detectada en modo automático
            (``None`` si no se encontró ningún grupo repetido).

    Selección automática: si la configuración no tiene campos (y no es API),
    la primera página obtenida se analiza con ``autoselect.detectar_estructura``
    y los selectores detectados se usan en todas las páginas; quedan en
    ``AcquisitionResult.estructura``.

    Returns:
        ``AcquisitionResult`` con registros, URL final y páginas visitadas.

    Raises:
        AccessRestrictionError: si alguna página está bloqueada o restringida.
        ValueError: si la configuración no es válida.
    """
    config.validate()
    url = config.url
    result = AcquisitionResult([], url, [config.method.value])
    visited: set[str] = set()
    page = initial_page
    original_host = urlparse(config.url).netloc.lower()
    con_navegador = config.method in BROWSER_METHODS
    sesion: _BrowserSession | None = None
    automatico = config.method != AcquisitionMethod.API and not config.fields

    try:
        for page_number in range(config.max_pages):
            if url in visited:
                break
            visited.add(url)
            page_config = _with_url(config, url)
            if page_number:
                page = inspect_url(url, config.timeout_seconds, config.headers)
            if page and page.report.blocked and not captcha_atendible(
                page.report, config.method, intervencion is not None
            ):
                raise AccessRestrictionError("; ".join(page.report.warnings) or "Acceso restringido.")
            omitida = False
            try:
                if con_navegador:
                    if sesion is None:
                        sesion = _abrir_sesion(config, intervencion)
                    body: str | bytes = sesion.adquirir(url)
                    result.methods_used.append(config.method.value)
                else:
                    body = acquire_page(page_config, page)
                if automatico:
                    automatico = False  # se detecta una sola vez, con la primera página real
                    estructura = detectar_estructura(body, config.item_selector)
                    result.estructura = estructura
                    if estructura is not None:
                        config = estructura.aplicar(config)
                        page_config = _with_url(config, url)
                    if on_detect:
                        on_detect(estructura)
                records = extract_page(page_config, body)
            except PaginaOmitida:
                omitida = True
                result.skipped_urls.append(url)
                records = []
                # Se intenta seguir la paginación con el DOM que quedó en pantalla.
                body = sesion.html_seguro() if sesion else ""
            except ExtraccionCancelada:
                result.cancelled = True
                break
            remaining = config.max_records - len(result.records)
            result.records.extend(records[:remaining])
            if not omitida:
                result.pages_visited += 1
                if on_page:
                    on_page(result.pages_visited, url, len(result.records))
            if len(result.records) >= config.max_records or not config.pagination_selector:
                break
            html = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
            node = BeautifulSoup(html, "html.parser").select_one(config.pagination_selector)
            href = node.get("href") if node else None
            next_url = urljoin(url, href) if href else ""
            if not next_url or urlparse(next_url).netloc.lower() != original_host:
                break
            if page_number + 1 < config.max_pages:
                time.sleep(config.delay_seconds)
                url = next_url
                page = None
    finally:
        if sesion is not None:
            sesion.cerrar()  # el navegador se cierra solo al terminar toda la ejecución
    result.final_url = url
    return result


def _with_url(config: ScrapeConfig, url: str) -> ScrapeConfig:
    """Devuelve una copia de ``config`` con otra URL (usado en la paginación)."""
    values = config.__dict__.copy()
    values["url"] = url
    return ScrapeConfig(**values)


def _acquire_selenium(config: ScrapeConfig) -> str:
    """Navega con Selenium/Chrome una sola URL y devuelve el HTML renderizado.

    Sin intervención humana: ante CAPTCHA o autenticación se detiene. El
    navegador siempre se cierra al terminar.

    Raises:
        RuntimeError: si Selenium no está instalado.
        AccessRestrictionError: si aparece CAPTCHA o autenticación.
        InspectionError: si el DOM supera ``MAX_HTML_BYTES``.
    """
    sesion = _SeleniumSession(config)
    try:
        return sesion.adquirir(config.url)
    finally:
        sesion.cerrar()


def _acquire_playwright(config: ScrapeConfig) -> str:
    """Navega con Playwright/Chromium una sola URL y devuelve el HTML renderizado.

    Equivalente a ``_acquire_selenium``; además se detiene ante HTTP >= 400.

    Raises:
        RuntimeError: si Playwright no está instalado.
        AccessRestrictionError: si el sitio responde >= 400 o hay CAPTCHA/login.
        InspectionError: si el DOM supera ``MAX_HTML_BYTES``.
    """
    sesion = _PlaywrightSession(config)
    try:
        return sesion.adquirir(config.url)
    finally:
        sesion.cerrar()
