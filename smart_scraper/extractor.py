"""Adquisición de contenido: HTTP (Requests), Selenium, Playwright y API autorizada.

Rol en la arquitectura: módulo de adquisición/navegación. Obtiene el HTML o
JSON de la página (``acquire_page``), delega la selección de datos en
``selection`` (``extract_page``) y gestiona la paginación acotada
(``scrape``). Con Selenium o Playwright controla un navegador real: espera la
carga, hace clic en "cargar más" y se desplaza un número limitado de veces.

Seguridad: ante CAPTCHA, formularios de autenticación o respuestas
401/403/429 se lanza ``AccessRestrictionError`` y se detiene la navegación; el
módulo nunca intenta resolver ni evadir esas restricciones. Solo se sigue
paginación del mismo host y siempre con límites de páginas, registros y bytes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .config import AcquisitionMethod, ScrapeConfig
from .inspector import (
    MAX_HTML_BYTES,
    InspectionError,
    InspectedPage,
    diagnose,
    inspect_url,
)
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
    """
    records: list[dict[str, Any]]
    final_url: str
    methods_used: list[str] = field(default_factory=list)
    pages_visited: int = 0


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
        raise AccessRestrictionError("Se detectó un CAPTCHA/challenge; no se intentará resolver.")
    return select_html(html, config.item_selector, config.fields, config.max_records)


def _check_browser_page(url: str, html: str) -> None:
    """Revisa el DOM renderizado por el navegador y se detiene ante restricciones.

    Se invoca tras cada carga, clic o desplazamiento para no seguir navegando
    si aparece un CAPTCHA o un formulario de autenticación.

    Raises:
        AccessRestrictionError: si se detecta CAPTCHA o autenticación.
    """
    report = diagnose(url, 200, "text/html", html.encode("utf-8"))
    if report.captcha_detected:
        raise AccessRestrictionError("Se detectó un CAPTCHA/challenge; no se intentará resolver.")
    if report.authentication_detected:
        raise AccessRestrictionError("Se detectó un formulario de autenticación; se detuvo el navegador.")


def scrape(config: ScrapeConfig, initial_page: InspectedPage | None = None) -> AcquisitionResult:
    """Extrae hasta el límite configurado y solo sigue paginación del mismo host.

    Recorre como máximo ``max_pages`` páginas, evita URL repetidas, espera
    ``delay_seconds`` entre páginas y se detiene al alcanzar ``max_records`` o si
    el enlace de siguiente página apunta a otro host.

    Args:
        config: configuración (se valida al inicio).
        initial_page: inspección ya hecha de la primera página, si existe.

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

    for page_number in range(config.max_pages):
        if url in visited:
            break
        visited.add(url)
        page_config = _with_url(config, url)
        if page_number:
            page = inspect_url(url, config.timeout_seconds, config.headers)
        if page and page.report.blocked:
            raise AccessRestrictionError("; ".join(page.report.warnings) or "Acceso restringido.")
        body = acquire_page(page_config, page)
        if config.method in {AcquisitionMethod.SELENIUM, AcquisitionMethod.PLAYWRIGHT}:
            result.methods_used.append(config.method.value)
        records = extract_page(page_config, body)
        remaining = config.max_records - len(result.records)
        result.records.extend(records[:remaining])
        result.pages_visited += 1
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
    result.final_url = url
    return result


def _with_url(config: ScrapeConfig, url: str) -> ScrapeConfig:
    """Devuelve una copia de ``config`` con otra URL (usado en la paginación)."""
    values = config.__dict__.copy()
    values["url"] = url
    return ScrapeConfig(**values)


def _acquire_selenium(config: ScrapeConfig) -> str:
    """Navega con Selenium/Chrome y devuelve el HTML renderizado.

    Pasos: configurar Chrome, abrir la URL, esperar a que el documento cargue,
    revisar CAPTCHA/autenticación, pulsar "cargar más" un número acotado de
    veces, desplazarse un número acotado de veces y leer el DOM final. El
    navegador siempre se cierra al terminar.

    Raises:
        RuntimeError: si Selenium no está instalado.
        AccessRestrictionError: si aparece CAPTCHA o autenticación.
        InspectionError: si el DOM supera ``MAX_HTML_BYTES``.
    """
    # Importación diferida: Selenium es opcional y solo se exige si se usa este método.
    try:
        from selenium import webdriver
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:
        raise RuntimeError("Instala Selenium con `pip install selenium`.") from exc
    # --- Opciones de Chrome ---
    options = webdriver.ChromeOptions()
    if config.headless:
        # Modo sin interfaz gráfica (headless moderno de Chrome).
        options.add_argument("--headless=new")
    # Evita ventanas emergentes de notificaciones que bloquearían la página.
    options.add_argument("--disable-notifications")
    # Tamaño de ventana fijo para que el diseño responsivo sea reproducible.
    options.add_argument("--window-size=1280,900")
    # Selenium Manager localiza/descarga el chromedriver adecuado.
    driver = webdriver.Chrome(options=options)
    try:
        # Tope de tiempo para la carga de la página (evita esperas infinitas).
        driver.set_page_load_timeout(config.timeout_seconds)
        # Navegación inicial a la URL objetivo.
        driver.get(config.url)
        # Espera explícita (WebDriverWait): continúa cuando el documento está
        # "interactive" o "complete"; falla con timeout si no ocurre a tiempo.
        WebDriverWait(driver, config.timeout_seconds).until(
            lambda browser: browser.execute_script("return document.readyState") in {"interactive", "complete"}
        )
        # Seguridad: si ya hay CAPTCHA o login, se detiene antes de interactuar.
        _check_browser_page(config.url, driver.page_source)
        # Clics acotados (0-5) en el botón "cargar más" para revelar más elementos.
        for _ in range(config.load_more_clicks):
            # find_elements (plural) no lanza excepción si el botón no existe.
            buttons = driver.find_elements("css selector", config.load_more_selector)
            if not buttons:
                # Ya no hay botón: no quedan más datos por cargar.
                break
            buttons[0].click()
            # Pausa cortés para no saturar el servidor y dejar que cargue el contenido.
            time.sleep(1)
            # Revalida el DOM tras cada clic (CAPTCHA/autenticación).
            _check_browser_page(config.url, driver.page_source)
        # Desplazamiento acotado (0-5 pasos) hasta el final de la página, útil
        # para el scroll infinito / carga perezosa.
        for _ in range(config.scroll_steps):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            # Pausa para que el contenido nuevo se renderice.
            time.sleep(1)
            _check_browser_page(config.url, driver.page_source)
        # DOM final ya renderizado por JavaScript.
        html = driver.page_source
        # Límite de tamaño para evitar procesar documentos desproporcionados.
        if len(html.encode("utf-8")) > MAX_HTML_BYTES:
            raise InspectionError(f"El DOM renderizado supera el límite de {MAX_HTML_BYTES} bytes.")
        return html
    finally:
        # Cierra siempre el navegador y el driver, incluso si hubo errores o restricciones.
        driver.quit()


def _acquire_playwright(config: ScrapeConfig) -> str:
    """Navega con Playwright/Chromium y devuelve el HTML renderizado.

    Equivalente a ``_acquire_selenium``: carga la URL, se detiene ante HTTP
    >= 400, CAPTCHA o autenticación, hace clics acotados en "cargar más" y
    desplazamientos acotados, y cierra siempre el navegador.

    Raises:
        RuntimeError: si Playwright no está instalado.
        AccessRestrictionError: si el sitio responde >= 400 o hay CAPTCHA/login.
        InspectionError: si el DOM supera ``MAX_HTML_BYTES``.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Instala Playwright con `pip install '.[playwright]'` y `playwright install chromium`.") from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.headless)
        page = browser.new_page(extra_http_headers=config.headers)
        try:
            response = page.goto(config.url, wait_until="domcontentloaded", timeout=config.timeout_seconds * 1000)
            if response and response.status >= 400:
                raise AccessRestrictionError(f"El sitio respondió HTTP {response.status}; se detuvo la navegación.")
            _check_browser_page(config.url, page.content())
            if config.load_more_selector:
                button = page.locator(config.load_more_selector)
                for _ in range(config.load_more_clicks):
                    if not button.count():
                        break
                    button.first.click(timeout=config.timeout_seconds * 1000)
                    page.wait_for_timeout(1000)
                    _check_browser_page(config.url, page.content())
            for _ in range(config.scroll_steps):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
                _check_browser_page(config.url, page.content())
            html = page.content()
            if len(html.encode("utf-8")) > MAX_HTML_BYTES:
                raise InspectionError(f"El DOM renderizado supera el límite de {MAX_HTML_BYTES} bytes.")
            return html
        finally:
            browser.close()
