"""Pausa por CAPTCHA con intervención humana: detección, canal entre hilos y flujo completo.

No se usa ningún navegador real: Selenium se sustituye por un driver simulado
que sirve HTML por URL, y la "persona" es un canal falso con respuestas
programadas. Ninguna prueba intenta resolver un CAPTCHA.
"""

from __future__ import annotations

import logging
import threading
import time
from types import ModuleType
from unittest.mock import patch

import pytest

from smart_scraper.app import run_job
from smart_scraper.config import AcquisitionMethod, FieldRule, ScrapeConfig
from smart_scraper.inspector import detectar_captcha, diagnose
from smart_scraper.intervencion import (
    CanalIntervencion,
    Decision,
    IntervencionHumana,
    Resultado,
)

WIDGET = '<div class="g-recaptcha" data-sitekey="demo"></div>'


# ---------------------------------------------------------------- detección
@pytest.mark.parametrize(
    "html",
    [
        '<iframe src="https://www.google.com/recaptcha/api2/anchor?k=x"></iframe>',
        '<iframe src="https://newassets.hcaptcha.com/captcha/v1/x"></iframe>',
        '<iframe src="https://challenges.cloudflare.com/cdn-cgi/challenge-platform/turnstile/x"></iframe>',
        WIDGET,
        '<div class="h-captcha"></div>',
        '<div class="cf-turnstile"></div>',
        '<div id="captcha"></div>',
        '<div data-captcha-demo></div>',
        "<p>Verify you are human</p>",
    ],
)
def test_detectar_captcha_reconoce_widgets_iframes_y_challenges(html):
    assert detectar_captcha(html)
    assert detectar_captcha(html.encode("utf-8"))


def test_detectar_captcha_no_marca_menciones_sueltas():
    assert not detectar_captcha("<p>Nuestra política de CAPTCHA y privacidad</p><iframe src='/mapa'></iframe>")
    assert not diagnose("http://x.test", 200, "text/html", b"<p>sin captcha aqui</p>").blocked


def test_detectar_captcha_acepta_driver_y_pagina():
    driver = type("Driver", (), {"page_source": WIDGET})()
    page = type("Page", (), {"content": lambda self: "<article></article>"})()
    assert detectar_captcha(driver)
    assert not detectar_captcha(page)


# ------------------------------------------------------------ canal (hilos)
def test_canal_entrega_la_decision_entre_hilos():
    canal = CanalIntervencion()
    resultado = {}
    hilo = threading.Thread(
        target=lambda: resultado.setdefault("d", canal.solicitar("http://x.test", 1, time.monotonic() + 5))
    )
    hilo.start()
    solicitud = None
    for _ in range(100):
        solicitud = canal.siguiente()
        if solicitud:
            break
        time.sleep(0.01)
    assert solicitud is not None and "http://x.test" in solicitud.mensaje
    assert solicitud.responder(Decision.CONTINUAR)
    hilo.join(timeout=2)
    assert resultado["d"] == Decision.CONTINUAR


def test_canal_vence_y_descarta_respuestas_tardias():
    canal = CanalIntervencion()
    assert canal.solicitar("http://x.test", 1, time.monotonic() + 0.05) is None
    solicitud = canal.siguiente()
    assert solicitud.cerrada
    assert not solicitud.responder(Decision.CONTINUAR)


# ------------------------------------------------- esperar_intervencion_humana
class CanalProgramado:
    """Canal falso: devuelve decisiones en orden y ejecuta efectos (la "persona")."""

    def __init__(self, *pasos):
        self.pasos = list(pasos)
        self.solicitudes = []

    def solicitar(self, url, intento, plazo):
        self.solicitudes.append((url, intento))
        decision, efecto = self.pasos.pop(0)
        if efecto:
            efecto()
        return decision


def _intervencion(canal, presente):
    visible = []
    control = IntervencionHumana(canal, timeout_seconds=60)
    control.vincular(lambda: presente["v"], lambda: visible.append(True) or True)
    return control, visible


def test_continuar_con_captcha_presente_vuelve_a_avisar_y_luego_reanuda():
    presente = {"v": True}
    canal = CanalProgramado(
        (Decision.CONTINUAR, None),  # la persona pulsa Continuar sin resolver
        (Decision.CONTINUAR, lambda: presente.update(v=False)),  # ahora sí lo resolvió
    )
    control, visible = _intervencion(canal, presente)
    assert control.esperar_intervencion_humana("http://x.test/p") == Resultado.RESUELTO
    assert [intento for _, intento in canal.solicitudes] == [1, 2]
    assert visible == [True]
    eventos = [e["evento"] for e in control.eventos]
    assert eventos == ["detectado", "navegador relanzado en modo visible", "sigue presente", "resuelto"]
    assert all(e["url"] == "http://x.test/p" and e["hora"] for e in control.eventos)


@pytest.mark.parametrize(
    "decision, esperado",
    [(Decision.OMITIR, Resultado.OMITIDO), (Decision.CANCELAR, Resultado.CANCELADO), (None, Resultado.EXPIRADO)],
)
def test_omitir_cancelar_y_expirar(decision, esperado, caplog):
    control, _ = _intervencion(CanalProgramado((decision, None)), {"v": True})
    with caplog.at_level(logging.INFO, logger="smart_scraper"):
        assert control.esperar_intervencion_humana("http://x.test/p") == esperado
    assert control.eventos[-1]["evento"] == esperado.value
    assert f"CAPTCHA {esperado.value} | http://x.test/p" in caplog.text


def test_navegador_cerrado_durante_la_espera_cancela():
    control = IntervencionHumana(CanalProgramado((Decision.CONTINUAR, None)), timeout_seconds=60)

    def cerrado():
        raise RuntimeError("no such window")

    control.vincular(cerrado, lambda: False)
    assert control.esperar_intervencion_humana("http://x.test/p") == Resultado.CANCELADO


# ------------------------------------------------- flujo completo con Selenium simulado
class NavegadorSimulado:
    """Estado compartido de los drivers simulados (una "persona" puede resolverlo)."""

    def __init__(self, paginas_con_captcha):
        self.paginas_con_captcha = set(paginas_con_captcha)
        self.lanzamientos = []  # argumentos de cada Chrome lanzado
        self.cookies_copiadas = []
        self.quits = 0

    def resolver(self):
        self.paginas_con_captcha.clear()


def _selenium_simulado(navegador: NavegadorSimulado):
    class Options:
        def __init__(self):
            self.args = []

        def add_argument(self, arg):
            self.args.append(arg)

    class Driver:
        def __init__(self, options):
            navegador.lanzamientos.append(options.args)
            self.current_url = ""

        @property
        def page_source(self):
            if any(self.current_url.endswith(p) for p in navegador.paginas_con_captcha):
                return f"<html><body>{WIDGET}</body></html>"
            numero = "2" if "page=2" in self.current_url else "1"
            siguiente = "" if numero == "2" else "<a class='next' href='/pagination?page=2'>Next</a>"
            return f"<article><h2>Página {numero}</h2></article>{siguiente}"

        def set_page_load_timeout(self, _):
            pass

        def get(self, url):
            self.current_url = url

        def execute_script(self, script):
            return "complete" if "readyState" in script else None

        def find_elements(self, *_):
            return []

        def get_cookies(self):
            return [{"name": "sesion", "value": "abc"}]

        def add_cookie(self, cookie):
            navegador.cookies_copiadas.append(cookie)

        def quit(self):
            navegador.quits += 1

    class Wait:
        def __init__(self, driver, _):
            self.driver = driver

        def until(self, condition):
            return condition(self.driver)

    selenium = ModuleType("selenium")
    webdriver = ModuleType("selenium.webdriver")
    webdriver.ChromeOptions = Options
    webdriver.Chrome = lambda options: Driver(options)
    support = ModuleType("selenium.webdriver.support")
    ui = ModuleType("selenium.webdriver.support.ui")
    ui.WebDriverWait = Wait
    selenium.webdriver = webdriver
    return {
        "selenium": selenium,
        "selenium.webdriver": webdriver,
        "selenium.webdriver.support": support,
        "selenium.webdriver.support.ui": ui,
    }


def _config(site):
    return ScrapeConfig(
        f"{site}/pagination",
        method=AcquisitionMethod.SELENIUM,
        item_selector="article",
        fields=[FieldRule("titulo", "h2")],
        pagination_selector="a.next",
        max_pages=3,
        headless=True,
    )


def _ejecutar(site, tmp_path, navegador, canal):
    with patch.dict("sys.modules", _selenium_simulado(navegador)), patch("smart_scraper.extractor.time.sleep"):
        return run_job(_config(site), tmp_path, "json", canal_captcha=canal)


def test_captcha_resuelto_reanuda_en_el_mismo_navegador_visible(site, tmp_path):
    navegador = NavegadorSimulado({"page=2"})
    canal = CanalProgramado((Decision.CONTINUAR, navegador.resolver))
    outcome = _ejecutar(site, tmp_path, navegador, canal)
    report = outcome.report
    assert report.status == "completed"
    assert report.records_saved == 2 and report.pages_visited == 2
    # Headless al inicio; un único relanzamiento visible con las cookies copiadas.
    assert len(navegador.lanzamientos) == 2
    assert "--headless=new" in navegador.lanzamientos[0]
    assert "--headless=new" not in navegador.lanzamientos[1]
    assert navegador.cookies_copiadas == [{"name": "sesion", "value": "abc"}]
    assert [e["evento"] for e in report.captcha_events] == [
        "detectado", "navegador relanzado en modo visible", "resuelto",
    ]


def test_omitir_registra_la_url_y_guarda_el_resto(site, tmp_path):
    navegador = NavegadorSimulado({"page=2"})
    outcome = _ejecutar(site, tmp_path, navegador, CanalProgramado((Decision.OMITIR, None)))
    report = outcome.report
    assert report.status == "completed"
    assert report.skipped_urls == [f"{site}/pagination?page=2"]
    assert report.records_saved == 1


def test_expirar_se_trata_como_omitir(site, tmp_path):
    navegador = NavegadorSimulado({"page=2"})
    outcome = _ejecutar(site, tmp_path, navegador, CanalProgramado((None, None)))
    assert outcome.report.skipped_urls == [f"{site}/pagination?page=2"]
    assert outcome.report.captcha_events[-1]["evento"] == "expirado"


def test_cancelar_detiene_todo_y_guarda_lo_extraido(site, tmp_path):
    navegador = NavegadorSimulado({"page=2"})
    outcome = _ejecutar(site, tmp_path, navegador, CanalProgramado((Decision.CANCELAR, None)))
    report = outcome.report
    assert report.status == "cancelled"
    assert report.records_saved == 1
    assert outcome.report_path.exists()
    assert any(path.endswith(".json") and "records" in path for path in report.output_paths)
    assert navegador.quits >= 1  # el navegador se cierra al terminar


def test_sin_canal_el_captcha_sigue_deteniendo_la_ejecucion(site, tmp_path):
    from smart_scraper.app import RunFailure

    navegador = NavegadorSimulado({"page=2"})
    with pytest.raises(RunFailure) as error:
        _ejecutar(site, tmp_path, navegador, None)
    assert "CAPTCHA" in error.value.outcome.report.error


def test_modo_requests_no_pausa_aunque_haya_canal(site, tmp_path):
    from smart_scraper.app import RunFailure

    canal = CanalProgramado()
    with pytest.raises(RunFailure):
        run_job(ScrapeConfig(f"{site}/captcha"), tmp_path, canal_captcha=canal)
    assert canal.solicitudes == []
