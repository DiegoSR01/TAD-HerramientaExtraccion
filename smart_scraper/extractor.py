"""Adaptadores de adquisición HTTP, Selenium, Playwright y API autorizada."""

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
    """Señal de bloqueo, CAPTCHA o autenticación que requiere acción legítima."""


@dataclass
class AcquisitionResult:
    records: list[dict[str, Any]]
    final_url: str
    methods_used: list[str] = field(default_factory=list)
    pages_visited: int = 0


def acquire_page(config: ScrapeConfig, inspected: InspectedPage | None = None) -> str | bytes:
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
    if config.method == AcquisitionMethod.API:
        payload = parse_json_body(body if isinstance(body, bytes) else body.encode("utf-8"))
        return select_json(payload, config.fields, config.json_records_path, config.max_records)
    html = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    report = diagnose(config.url, 200, "text/html", html.encode("utf-8"))
    if report.captcha_detected:
        raise AccessRestrictionError("Se detectó un CAPTCHA/challenge; no se intentará resolver.")
    return select_html(html, config.item_selector, config.fields, config.max_records)


def _check_browser_page(url: str, html: str) -> None:
    report = diagnose(url, 200, "text/html", html.encode("utf-8"))
    if report.captcha_detected:
        raise AccessRestrictionError("Se detectó un CAPTCHA/challenge; no se intentará resolver.")
    if report.authentication_detected:
        raise AccessRestrictionError("Se detectó un formulario de autenticación; se detuvo el navegador.")


def scrape(config: ScrapeConfig, initial_page: InspectedPage | None = None) -> AcquisitionResult:
    """Extrae hasta el límite configurado y solo sigue paginación del mismo host."""
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
    values = config.__dict__.copy()
    values["url"] = url
    return ScrapeConfig(**values)


def _acquire_selenium(config: ScrapeConfig) -> str:
    try:
        from selenium import webdriver
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:
        raise RuntimeError("Instala Selenium con `pip install selenium`.") from exc
    options = webdriver.ChromeOptions()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=1280,900")
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(config.timeout_seconds)
        driver.get(config.url)
        WebDriverWait(driver, config.timeout_seconds).until(
            lambda browser: browser.execute_script("return document.readyState") in {"interactive", "complete"}
        )
        _check_browser_page(config.url, driver.page_source)
        for _ in range(config.load_more_clicks):
            buttons = driver.find_elements("css selector", config.load_more_selector)
            if not buttons:
                break
            buttons[0].click()
            time.sleep(1)
            _check_browser_page(config.url, driver.page_source)
        for _ in range(config.scroll_steps):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            _check_browser_page(config.url, driver.page_source)
        html = driver.page_source
        if len(html.encode("utf-8")) > MAX_HTML_BYTES:
            raise InspectionError(f"El DOM renderizado supera el límite de {MAX_HTML_BYTES} bytes.")
        return html
    finally:
        driver.quit()


def _acquire_playwright(config: ScrapeConfig) -> str:
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
