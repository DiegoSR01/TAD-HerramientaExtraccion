"""Actualiza ``docs/INFORME_TECNICO.docx`` con la evidencia del avance (nov. 2026).

El informe Word conserva el formato institucional (portada, encabezados, figuras,
tablas y anexos); por eso este script NO lo regenera desde cero: abre el docx
existente con python-docx, reutiliza el formato directo de sus párrafos/tablas
(clonándolos) y añade o actualiza el contenido:

- panel de progreso de 9 pasos, clasificador de escenarios y estrategia;
- detección de cambios ampliada;
- evidencia multisitio (matriz de escenarios y correspondencia con los 9
  criterios de aceptación del reto) leída de ``docs/evidencias/``;
- conteo de pruebas (32), módulo ``estrategia.py``, video y checklist de entregables.

Es idempotente: si el documento ya contiene la sección nueva, no hace nada.

Uso:
    python scripts/generar_informe_docx.py [entrada.docx] [salida.docx]
Por omisión lee y sobrescribe docs/INFORME_TECNICO.docx. Si se necesita volver al
original, recuperarlo con ``git show c1aff03:docs/INFORME_TECNICO.docx``.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import docx
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
MATRIZ = ROOT / "docs" / "evidencias" / "MATRIZ_ESCENARIOS.md"
MARKER = "7. Interfaz con panel de progreso y estrategia"


def texto(p) -> str:
    return "".join(t.text or "" for t in p.iter(qn("w:t")))


def set_text(p, value: str) -> None:
    """Pone el texto en el primer run con texto y vacía el resto (conserva el formato)."""
    ts = list(p.iter(qn("w:t")))
    ts[0].text = value
    ts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for t in ts[1:]:
        t.text = ""


def find_par(doc, startswith: str, nth: int = 0):
    hits = [p for p in doc.paragraphs if p.text.startswith(startswith)]
    return hits[nth]


class Builder:
    """Crea elementos clonando plantillas del propio documento."""

    def __init__(self, doc):
        self.doc = doc
        body = doc.element.body
        self.next_id = 1 + max(int(b.get(qn("w:id"))) for b in body.iter(qn("w:bookmarkStart")))
        self.t_h2 = copy.deepcopy(find_par(doc, "1. Arquitectura de la herramienta", 1)._p)
        self.t_h1 = copy.deepcopy(find_par(doc, "Análisis de Código")._p)
        self.t_body = copy.deepcopy(find_par(doc, "El paquete smart_scraper")._p)
        self.t_bullet = copy.deepcopy(find_par(doc, "Implementar el script de extracción")._p)
        self.t_code = copy.deepcopy(find_par(doc, "pip install -r requirements.txt")._p)
        self.t_caption = copy.deepcopy(find_par(doc, "Figura 1.")._p)
        self.t_table = copy.deepcopy(doc.tables[0]._tbl)

    def _bookmark(self, p, name: str) -> None:
        for tag in ("w:bookmarkStart", "w:bookmarkEnd"):
            for b in p.findall(qn(tag)):
                b.set(qn("w:id"), str(self.next_id))
                if tag == "w:bookmarkStart":
                    b.set(qn("w:name"), name)
        self.next_id += 1

    def h2(self, text: str, name: str):
        p = copy.deepcopy(self.t_h2)
        set_text(p, text)
        self._bookmark(p, name)
        return p

    def body(self, text: str):
        p = copy.deepcopy(self.t_body)
        set_text(p, text)
        return p

    def bullet(self, text: str):
        p = copy.deepcopy(self.t_bullet)
        set_text(p, text)
        return p

    def code(self, text: str):
        p = copy.deepcopy(self.t_code)
        set_text(p, text)
        return p

    def caption(self, text: str):
        p = copy.deepcopy(self.t_caption)
        for r in p.findall(qn("w:r")):
            if r.find(qn("w:drawing")) is not None:
                p.remove(r)
        set_text(p, text)
        return p

    def table(self, widths: list[int], header: list[str], rows: list[list[str]], size: int = 20):
        tbl = copy.deepcopy(self.t_table)
        trs = tbl.findall(qn("w:tr"))
        head_t, body_t = copy.deepcopy(trs[0]), copy.deepcopy(trs[1])
        for tr in trs:
            tbl.remove(tr)
        grid = tbl.find(qn("w:tblGrid"))
        for g in list(grid):
            grid.remove(g)
        for w in widths:
            g = grid.makeelement(qn("w:gridCol"), {qn("w:w"): str(w)})
            grid.append(g)
        tbl.find(qn("w:tblPr")).find(qn("w:tblW")).set(qn("w:w"), str(sum(widths)))

        def make_row(template, values):
            tr = copy.deepcopy(template)
            tcs = tr.findall(qn("w:tc"))
            for tc in tcs[1:]:
                tr.remove(tc)
            first = tcs[0]
            tr.remove(first)
            for width, value in zip(widths, values):
                tc = copy.deepcopy(first)
                tc.find(qn("w:tcPr")).find(qn("w:tcW")).set(qn("w:w"), str(width))
                set_text(tc.find(qn("w:p")), value)
                for sz in tc.iter(qn("w:sz")):
                    sz.set(qn("w:val"), str(size))
                tr.append(tc)
            return tr

        tbl.append(make_row(head_t, header))
        for values in rows:
            tbl.append(make_row(body_t, values))
        return tbl


def leer_matriz() -> list[list[str]]:
    filas = [l for l in MATRIZ.read_text(encoding="utf8").splitlines() if l.startswith("|")]
    return [[c.strip().replace("`", "") for c in l.strip("|").split("|")] for l in filas]


# Páginas impresas (según Word, tras añadir el contenido nuevo); la numeración del
# informe empieza una página después de la portada.
PAGINAS_TOC = {
    "7. Limitaciones": 11, "Análisis de Código": 12, "Conclusiones": 13, "Bibliografía": 13,
    "Anexos": 15, "Anexo A.": 15, "Anexo B.": 15, "Anexo C.": 16,
}


def actualizar_toc(doc, nuevas: list[tuple[str, str, int]]) -> None:
    """Añade entradas al índice y corrige los números de página posteriores.

    Si el contenido cambia, en Word: clic derecho sobre el índice -> «Actualizar
    campos» recalcula los números con las páginas reales.
    """
    toc = [p for p in doc.paragraphs if p.style.name.startswith("toc")]
    plantilla = next(p for p in toc if p.text.startswith("7. Limitaciones"))
    for p in toc:
        for prefijo, pagina in PAGINAS_TOC.items():
            if p.text.startswith(prefijo):
                list(p._p.iter(qn("w:t")))[-1].text = str(pagina)
                break
    referencia = plantilla._p
    for titulo, ancla, pagina in nuevas:
        nuevo = copy.deepcopy(referencia)
        link = nuevo.find(qn("w:hyperlink"))
        link.set(qn("w:anchor"), ancla)
        ts = list(nuevo.iter(qn("w:t")))
        ts[0].text = titulo
        ts[-1].text = str(pagina)
        for it in nuevo.iter(qn("w:instrText")):
            it.text = f" PAGEREF {ancla} \\h "
        referencia.addprevious(nuevo)


def main(entrada: Path, salida: Path) -> None:
    doc = docx.Document(str(entrada))
    if any(p.text.startswith(MARKER) for p in doc.paragraphs):
        print("El informe ya contiene las secciones nuevas; no se modifica.")
        return
    b = Builder(doc)
    matriz = leer_matriz()

    # ---------------------------------------------------------------- texto existente
    p = find_par(doc, "Este informe documenta el reto final")
    set_text(p._p, p.text.replace(
        "La aplicación se usa desde una interfaz gráfica (Tkinter) o desde código,",
        "La aplicación se usa desde una interfaz gráfica (Tkinter) con un panel de progreso de nueve pasos, "
        "que además clasifica el escenario detectado y recomienda una estrategia, o desde código,"))

    p = find_par(doc, "Para validar la herramienta")
    set_text(p._p, (
        "Para validar la herramienta se extrajo un dataset real de 100 libros del sitio books.toscrape.com, un sandbox "
        "público creado para practicar scraping; se ejecutaron diez escenarios de extracción con un único motor sobre "
        "cinco sitios de práctica y demos públicas (siete extracciones con 186 registros y tres incidencias: login "
        "detectado, ruta no permitida por robots.txt y CAPTCHA), y se clasificaron siete sitios (cinco portales de "
        "datos y dos sandboxes) según su esquema de protección y la viabilidad legal de extraer sus datos. Todo el "
        "código, los datos, las evidencias y el video de demostración están en el repositorio "
        "https://github.com/DiegoSR01/TAD-HerramientaExtraccion. "))

    p = find_par(doc, "El paquete smart_scraper")
    set_text(p._p, (
        "El paquete smart_scraper se divide en siete módulos funcionales con una responsabilidad cada uno, más el "
        "módulo de apoyo estrategia.py, que clasifica el escenario detectado y recomienda la estrategia de "
        "adquisición. El módulo app.py, mediante la función run_job, los orquesta en orden e informa su avance con un "
        "callback opcional, y gui.py ofrece la interfaz gráfica con el panel de progreso. Así cada etapa se puede "
        "probar o reemplazar por separado."))

    t0 = next(t for t in doc.tables if t.rows[0].cells[0].text == "Módulo")
    nueva = copy.deepcopy(t0.rows[-1]._tr)
    celdas = nueva.findall(qn("w:tc"))
    for tc, val in zip(celdas, ["Apoyo", "estrategia.py",
                                "Clasificación del escenario detectado y estrategia recomendada (requests, selenium, api o detener)"]):
        set_text(tc.find(qn("w:p")), val)
    t0.rows[-1]._tr.addnext(nueva)

    p = find_par(doc, "tests/test_pipeline.py levanta")
    set_text(p._p, (
        "tests/test_pipeline.py levanta un servidor HTTP local con sitios simulados, de modo que las pruebas no envían "
        "solicitudes a páginas públicas. A ellas se suman las de tests/test_progreso_y_cambios.py, que verifican el "
        "orden y los estados de los nueve pasos del progreso, el clasificador de escenarios (estático, paginación, "
        "tablas, JavaScript, scroll infinito, carga bajo demanda, API, autenticación y CAPTCHA) y la detección de "
        "cambios ampliada con la migración de una base SQLite antigua. En total pasan 32 pruebas (14 + 18). Selenium y "
        "Playwright se prueban con adaptadores de navegador simulados; su funcionamiento real se comprobó con la "
        "corrida del dataset, con la evidencia multisitio (sección 9) y en el video."))

    p = find_par(doc, "Figura 5.")
    set_text(p._p, "Figura 5. Ejecución de pytest (captura de la primera entrega; la suite actual suma 32 pruebas y también pasa)")

    p = find_par(doc, "El video video/demo_en_vivo.mp4")
    set_text(p._p, (
        "La versión actualizada del video, video/demo_avance.mp4, muestra la interfaz con el panel de progreso de nueve "
        "pasos recorriendo distintos escenarios, con el cuadro de escenario y estrategia y la detección de incidencias. "
        "La versión anterior, video/demo_en_vivo.mp4 (3:16, 1920×1080, con una versión sin subtítulos), se conserva: es "
        "una grabación real de la pantalla generada con video/grabar_demo.py que muestra el código en VS Code, la "
        "ejecución de las pruebas, la interfaz configurando books.toscrape.com, el diagnóstico de «Inspeccionar», la "
        "extracción con Selenium y Chrome visible recorriendo tres páginas y el CSV resultante. Incluye portada, cierre "
        "y un guion con los tiempos para la narración."))

    p = find_par(doc, "La herramienta cumple el flujo completo")
    set_text(p._p, (
        "La herramienta cumple el flujo completo de adquisición de datos: inspecciona el sitio, clasifica el escenario y "
        "recomienda una estrategia, extrae con Selenium navegando y gestionando elementos, selecciona los campos con "
        "reglas configurables, limpia y valida los datos, registra su linaje y los guarda en formatos listos para el "
        "análisis. El dataset de 100 libros, las 32 pruebas aprobadas y la evidencia multisitio (10 escenarios, 5 sitios, "
        "186 registros y 3 incidencias detectadas sin evadirlas) lo confirman, y el video muestra la arquitectura "
        "ejecutándose con el panel de progreso."))

    p = find_par(doc, "La clasificación de siete sitios")
    set_text(p._p, p.text.replace(
        "Por eso la herramienta se detiene ante bloqueos en lugar de evadirlos.",
        "Por eso la herramienta se detiene ante bloqueos, autenticación y CAPTCHA en lugar de evadirlos, y los reporta "
        "como incidencias."))

    # Limitaciones: renumerar y añadir viñeta
    lim = find_par(doc, "7. Limitaciones", 1)  # el índice es la entrada 0
    set_text(lim._p, "10. Limitaciones")
    ultima = find_par(doc, "Selenium por página")
    ultima._p.addnext(b.body(
        "Evidencia multisitio sobre sandboxes: los diez escenarios usan sitios de práctica y demos públicas; demuestran "
        "el motor, no la viabilidad legal de portales reales. La autenticación se evidencia como detección y detención, "
        "no como acceso."))

    # ---------------------------------------------------------------- secciones nuevas
    nuevos: list = []
    nuevos.append(b.h2(MARKER, "_TocAvance01"))
    nuevos.append(b.body(
        "La interfaz (gui.py) muestra el flujo esperado del reto como un stepper de nueve pasos que se actualiza en vivo "
        "mientras la tarea corre en un hilo de trabajo: 1) ingreso de URL y validación, 2) diagnóstico automatizado, "
        "3) presentación de resultados, 4) selección de datos, 5) configuración de extracción, 6) ejecución del motor, "
        "7) limpieza y validación, 8) almacenamiento y 9) reporte final. Cada paso pasa por los estados pendiente, en "
        "ejecución, completado, error o bloqueado. Junto al stepper hay una barra de progreso con el contador n / 9, el "
        "tiempo transcurrido, un cuadro «Escenario detectado / Estrategia» (que se pinta en naranja como INCIDENCIA "
        "cuando el acceso se detiene) y un registro con marcas de tiempo. La orquestación notifica el avance mediante "
        "un callback opcional: run_job(config, ..., progress=cb) y diagnose_config(config, progress=cb); sin callback "
        "el comportamiento no cambia."))
    nuevos.append(b.body(
        "El módulo estrategia.py convierte el diagnóstico del inspector en un Scenario (etiqueta, estrategia, motivo, "
        "señales y bandera de bloqueo) mediante classify_scenario. La prioridad de evaluación y la estrategia "
        "recomendada se resumen en la tabla siguiente. Las señales secundarias (paginación, tablas, endpoints API "
        "candidatos) se listan aparte. La clasificación es heurística: apoya la decisión del operador y no sustituye "
        "la revisión legal."))
    nuevos.append(b.table(
        [3600, 5238], ["Escenario detectado", "Estrategia recomendada"],
        [["CAPTCHA o bloqueo (HTTP 403/429)", "detener: incidencia; no se resuelve ni se evade"],
         ["Requiere autenticación", "detener, salvo permisos legítimos"],
         ["API JSON", "api, con autorización confirmada"],
         ["Scroll infinito", "selenium con desplazamientos acotados"],
         ["Carga bajo demanda (botón)", "selenium con clics acotados"],
         ["JavaScript/SPA", "selenium (o playwright)"],
         ["Paginación", "requests con selector de siguiente y límite de páginas"],
         ["Tablas", "requests"],
         ["HTML estático", "requests"]]))
    nuevos.append(b.body(""))

    nuevos.append(b.h2("8. Detección de cambios entre ejecuciones", "_TocAvance02"))
    nuevos.append(b.body(
        "La función compare_and_store_snapshot (storage.py) guarda por host el último snapshot y lo compara con la "
        "ejecución actual. Además de campos añadidos o faltantes, endpoints nuevos o eliminados y variación de "
        "registros, ahora registra: selector_changes (selectores que cambiaron, con valor anterior y posterior), "
        "new_columns (columnas nuevas), json_structure_added y json_structure_removed (rutas de claves del JSON que "
        "aparecieron o desaparecieron, calculadas por json_structure_signature), record_count_previous, "
        "record_count_delta y record_count_percent (volumen anterior, diferencia y porcentaje) y changes_detected "
        "(bandera global). La tabla run_snapshots se migra automáticamente con ALTER TABLE si proviene de una versión "
        "anterior, sin perder datos. No se comparan los valores de cada campo entre ejecuciones ni se inspecciona el "
        "tráfico de red."))

    nuevos.append(b.h2("9. Evidencia multisitio: matriz de escenarios", "_TocAvance03"))
    nuevos.append(b.body(
        "El script scripts/evidencia_extraccion.py ejecutó el 20 de noviembre de 2026 diez escenarios declarativos "
        "(cada uno es solo una configuración ScrapeConfig; no hay un scraper por sitio) a través del mismo motor, "
        "smart_scraper.app.run_job. Controles de cortesía: consulta previa de robots.txt (si no permite la ruta, el "
        "escenario se omite y se registra), User-Agent identificado, pausa de 2 s, máximo 3 páginas por escenario y una "
        "sola corrida (unas 30 peticiones públicas). Se probaron 5 sitios distintos (books.toscrape.com, google.com, "
        "nopecha.com, quotes.toscrape.com y scrapethissite.com), con 9 mecanismos distintos y 3 métodos del motor "
        "(requests, selenium y api): 7 extracciones completadas (186 registros) y 3 incidencias o restricciones "
        "identificadas con informe."))
    cuerpo = matriz[2:]
    nuevos.append(b.table(
        [1500, 1900, 2538, 1400, 1500],
        ["Escenario", "Sitio", "Estrategia elegida", "Resultado", "Viabilidad"],
        [[r[0], r[1], re.sub(r"\s*\[[a-z]+\]$", "", r[3]), f"{r[4]} ({r[5]} reg.)", r[7]] for r in cuerpo], size=16))
    nuevos.append(b.body(""))
    nuevos.append(b.body(
        "Correspondencia con los nueve criterios de aceptación del reto: HTML estático (escenario 01, 10 registros); "
        "sitio con JavaScript (02, Selenium, 10); información vía API (03, 10); paginación (04, 60 registros en 3 "
        "páginas); scroll infinito (05, Selenium con dos desplazamientos, 30); contenido bajo demanda (07, clic acotado, "
        "16); tablas (06, 50 registros en 2 páginas); autenticación (08, se detecta el formulario de login y se detiene "
        "sin enviar credenciales) y CAPTCHA con reporte de incidencia (09, omitido porque el robots.txt de Google no "
        "permite la ruta, y 10, demo de nopecha.com: CAPTCHA detectado y ejecución detenida con informe, sin intentar "
        "resolverlo)."))
    nuevos.append(b.body(
        "Los resultados se consolidaron en datasets/multisitio/ (dataset_multisitio.sqlite con las tablas registros, "
        "linaje, ejecuciones y una tabla tipada por escenario; dataset_multisitio.xlsx y dataset_multisitio.csv, más "
        "runs/<escenario>/ con el informe y los registros crudos de cada corrida). La matriz completa está en "
        "docs/evidencias/MATRIZ_ESCENARIOS.md y el resultado crudo en docs/evidencias/extraccion_2026-11-20.json; el "
        "Anexo D la reproduce con todas sus columnas."))

    lim_par = lim._p
    for el in nuevos:
        lim_par.addprevious(el)

    # ---------------------------------------------------------------- índice
    actualizar_toc(doc, [
        (MARKER, "_TocAvance01", 9),
        ("8. Detección de cambios entre ejecuciones", "_TocAvance02", 10),
        ("9. Evidencia multisitio: matriz de escenarios", "_TocAvance03", 10),
    ])
    for p in doc.paragraphs:
        if p.style.name.startswith("toc") and p.text.startswith("7. Limitaciones"):
            next(p._p.iter(qn("w:t"))).text = "10. Limitaciones"
    toc_anexos = next(p for p in doc.paragraphs if p.style.name.startswith("toc") and p.text.startswith("Anexo C"))
    nuevo = copy.deepcopy(toc_anexos._p)
    ts = list(nuevo.iter(qn("w:t")))
    ts[0].text = "Anexo D. Matriz completa de escenarios"
    ts[-1].text = "16"
    nuevo.find(qn("w:hyperlink")).set(qn("w:anchor"), "_TocAvance04")
    for it in nuevo.iter(qn("w:instrText")):
        it.text = " PAGEREF _TocAvance04 \\h "
    toc_anexos._p.addnext(nuevo)

    # ---------------------------------------------------------------- Anexo B
    t5 = next(t for t in doc.tables if t.rows[0].cells[0].text.startswith("Entregable solicitado"))
    def fila(inicio):
        return next(r for r in t5.rows if r.cells[0].text.startswith(inicio))
    set_text(fila("Base de datos")._tr.findall(qn("w:tc"))[1].find(qn("w:p")),
             "datasets/books_toscrape.* (100 filas) y datasets/multisitio/dataset_multisitio.* (186 registros, 7 escenarios), con linaje")
    set_text(fila("Evidencia de pruebas")._tr.findall(qn("w:tc"))[1].find(qn("w:p")),
             "docs/evidencias/ (sitios_2026-11-09.json, MATRIZ_ESCENARIOS.md y extraccion_2026-11-20.json), Anexos A y D")
    v = fila("Video")._tr
    set_text(v.findall(qn("w:tc"))[1].find(qn("w:p")), "video/demo_avance.mp4 (nuevo, 3:20) y video/demo_en_vivo.mp4 (previo, 3:16)")
    set_text(v.findall(qn("w:tc"))[2].find(qn("w:p")), "Cumplido (3:20)")
    extra = copy.deepcopy(fila("Documento")._tr)
    cs = extra.findall(qn("w:tc"))
    for tc, val in zip(cs, ["Pruebas automatizadas", "tests/ (32 pruebas aprobadas)", "Cumplido"]):
        set_text(tc.find(qn("w:p")), val)
    fila("Video")._tr.addprevious(extra)

    # ---------------------------------------------------------------- Anexo C
    c14 = find_par(doc, "python -m pytest -v")
    set_text(c14._p, "python -m pytest -q                          # 32 pruebas con sitios simulados")
    ev = find_par(doc, "python scripts/evidencia_sitios.py")
    ev._p.addnext(b.code("python scripts/evidencia_extraccion.py     # matriz multisitio: 10 escenarios, 5 sitios (requiere Chrome)"))

    # ---------------------------------------------------------------- Anexo D (apaisado, al final)
    body = doc.element.body
    sect = body.find(qn("w:sectPr"))
    h = b.h2("Anexo D. Matriz completa de escenarios", "_TocAvance04")
    sect.addprevious(h)
    sect.addprevious(b.body(
        "Generada por scripts/evidencia_extraccion.py el 2026-11-20 (UTC). Cada fila es una configuración del mismo "
        "motor (run_job)."))
    hdr = ["Escenario", "Sitio", "Mecanismo detectado", "Estrategia elegida", "Resultado", "Reg.", "Protección", "Viabilidad"]
    sect.addprevious(b.table(
        [1500, 1700, 1650, 2300, 1300, 600, 2022, 2500], hdr,
        [[r[0], r[1], r[2], re.sub(r"\s*\[[a-z]+\]$", "", r[3]), r[4], r[5], r[6], r[7]] for r in cuerpo], size=16))
    sect.addprevious(b.body(""))

    doc.save(str(salida))
    print(f"Informe actualizado: {salida}")


if __name__ == "__main__":
    entrada = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "INFORME_TECNICO.docx"
    salida = Path(sys.argv[2]) if len(sys.argv) > 2 else entrada
    main(entrada, salida)
