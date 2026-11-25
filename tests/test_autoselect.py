"""Pruebas de la selección automática (``smart_scraper.autoselect``)."""

from __future__ import annotations

import json

from smart_scraper.app import run_job
from smart_scraper.autoselect import detectar_estructura
from smart_scraper.config import AcquisitionMethod, ScrapeConfig, load_profile
from smart_scraper.selection import select_html

TARJETAS = """
<html><body>
<nav><ul><li><a href="/">Inicio</a></li><li><a href="/a">A</a></li><li><a href="/b">B</a></li></ul></nav>
<ol class="row">
  {items}
</ol>
<ul class="pager"><li class="next"><a href="/page-2">next</a></li></ul>
</body></html>
"""
ITEM = """
<li class="col-xs-6 col-md-3"><article class="product_pod">
  <div class="image_container"><a href="/libro-{n}"><img class="thumbnail" src="/img/{n}.jpg" alt="Libro {n}"></a></div>
  <h3><a href="/libro-{n}" title="Libro número {n} completo">Libro {n}...</a></h3>
  <p class="price_color">£{n}.50</p>
  <p class="availability">En stock</p>
  <a class="btn btn-primary" href="/carrito">Añadir</a>
</article></li>
"""


def _html_tarjetas(cantidad: int = 5) -> str:
    return TARJETAS.format(items="".join(ITEM.format(n=n) for n in range(1, cantidad + 1)))


def test_detecta_tarjetas_campos_y_paginacion():
    estructura = detectar_estructura(_html_tarjetas())
    assert estructura is not None
    assert estructura.item_selector == "article.product_pod"
    assert estructura.total_registros == 5
    assert estructura.pagination_selector == "li.next > a"
    registros = select_html(_html_tarjetas(), estructura.item_selector, estructura.fields)
    primero = registros[0]
    valores = set(primero.values())
    assert "/img/1.jpg" in valores
    assert "Libro número 1 completo" in valores
    assert "£1.50" in valores
    assert "En stock" in valores  # constante pero informativa: se conserva
    assert "Añadir" not in valores  # enlace repetido de relleno: se descarta
    assert "/carrito" not in valores  # atributo constante: se descarta
    nombres = [regla.name for regla in estructura.fields]
    assert "price_color" in nombres
    assert len(nombres) == len(set(nombres))


def test_ignora_menus_de_navegacion():
    html = _html_tarjetas(3).replace("</ul></nav>", "".join(
        f'<li><a href="/m{n}">Menú {n}</a></li>' for n in range(10)) + "</ul></nav>")
    estructura = detectar_estructura(html)
    assert estructura is not None
    assert estructura.item_selector == "article.product_pod"


def test_tabla_usa_los_encabezados_como_nombres():
    filas = "".join(
        f'<tr class="team"><td class="name">Equipo {n}</td><td class="wins {"text-success" if n % 2 else "text-danger"}">{n}</td></tr>'
        for n in range(6)
    )
    html = f"<table><tr><th>Nombre del equipo</th><th>Victorias</th></tr>{filas}</table>"
    estructura = detectar_estructura(html)
    assert estructura is not None
    assert estructura.item_selector == "tr.team"
    assert [(r.name, r.selector) for r in estructura.fields] == [
        ("nombre_del_equipo", "td.name"),
        ("victorias", "td.wins"),  # sin la clase utilitaria que cambia por fila
    ]


def test_tarjetas_repartidas_en_filas_forman_un_solo_grupo():
    filas = "".join(
        '<div class="row">' + "".join(
            f'<div class="col-md-4 country"><h3 class="country-name">País {r}{c}</h3>'
            f'<span class="country-capital">Capital {r}{c}</span></div>'
            for c in range(3)
        ) + "</div>"
        for r in range(4)
    )
    estructura = detectar_estructura(f'<div id="countries" class="container">{filas}</div>')
    assert estructura is not None
    assert estructura.item_selector == "div.country"
    assert estructura.total_registros == 12
    assert [r.name for r in estructura.fields] == ["country_name", "country_capital"]


def test_registro_que_es_solo_texto_usa_scope():
    html = "<ul class='lista'>" + "".join(f"<li class='dato'>Valor {n}</li>" for n in range(4)) + "</ul>"
    estructura = detectar_estructura(html)
    assert estructura is not None
    assert estructura.fields[0].selector == ":scope"
    registros = select_html(html, estructura.item_selector, estructura.fields)
    assert [r[estructura.fields[0].name] for r in registros] == [f"Valor {n}" for n in range(4)]


def test_selector_del_usuario_invalido_o_vacio_se_ignora():
    assert detectar_estructura(_html_tarjetas(), item_selector="5").item_selector == "article.product_pod"
    assert detectar_estructura(_html_tarjetas(), item_selector="article.product_pod").total_registros == 5


def test_pagina_sin_registros_repetidos():
    assert detectar_estructura("<html><body><h1>Hola</h1><p>Un párrafo.</p></body></html>") is None


def test_run_job_sin_campos_detecta_y_guarda_el_perfil(site, tmp_path):
    config = ScrapeConfig(url=f"{site}/catalogo", method=AcquisitionMethod.REQUESTS)
    report = run_job(config, tmp_path, "json").report
    assert report.status == "completed"
    assert report.auto_selection["item_selector"] == "div.card"
    assert report.auto_selection["pagination_selector"] == 'a[rel~="next"]'
    assert report.records_saved == 4
    perfil = load_profile(tmp_path / "profiles", config.url)
    assert perfil is not None  # el perfil queda con los selectores detectados
    assert {regla.name for regla in perfil.fields} >= {"nombre", "precio", "enlace_url"}
    datos = json.loads(next(tmp_path.glob("records-*.json")).read_text(encoding="utf-8"))
    assert datos[0]["data"]["nombre"] == "Producto 1" and datos[0]["data"]["precio"] == "$10"


def test_run_job_sin_grupo_repetido_usa_la_tabla(site, tmp_path):
    config = ScrapeConfig(url=f"{site}/table", method=AcquisitionMethod.REQUESTS)
    report = run_job(config, tmp_path, "json").report
    assert report.status == "completed"
    assert report.auto_selection == {}
    assert report.records_saved == 1
