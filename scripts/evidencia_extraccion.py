"""Evidencia multisitio del Reto final: diagnostico + extraccion con UN solo motor.

Cada escenario es DATOS (un diccionario en `ESCENARIOS`), no codigo propio: todos
se ejecutan con la misma funcion `smart_scraper.app.run_job` y la misma
`ScrapeConfig`. Cuando un sitio no permite la extraccion (CAPTCHA, login) la
herramienta identifica la restriccion, se detiene y deja un informe; ese informe
tambien se registra como evidencia (incidencia).

Politica de cortesia: robots.txt consultado antes de cada escenario (si no
permite la ruta, se omite y se registra), pausa de 2 s entre paginas, maximo 3
paginas y pocos registros por escenario, una sola corrida, User-Agent honesto
de la herramienta, sin evadir ninguna proteccion.

Salidas:
  datasets/multisitio/runs/<escenario>/        informe, registros, linaje, perfil
  datasets/multisitio/dataset_multisitio.{sqlite,xlsx,csv}
  docs/evidencias/extraccion_<fecha>.json      evidencia completa
  docs/evidencias/MATRIZ_ESCENARIOS.md         matriz de escenarios

Uso (desde la raiz del repositorio):
    python scripts/evidencia_extraccion.py
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smart_scraper.app import RunFailure, run_job  # noqa: E402
from smart_scraper.config import AcquisitionMethod, ScrapeConfig, parse_field_rules  # noqa: E402

BASE = ROOT / "datasets" / "multisitio"
RUNS = BASE / "runs"
EVIDENCIAS = ROOT / "docs" / "evidencias"
USER_AGENT = "TAD-SmartScraper/0.1 (proyecto academico)"
PAUSA_ENTRE_ESCENARIOS = 2.0

# --------------------------------------------------------------------------
# Escenarios declarativos. `config` son los argumentos de ScrapeConfig;
# `campos` usa la sintaxis de `parse_field_rules`.
# `esperado`: "extraccion" (se espera dataset) o "incidencia" (se espera que la
# herramienta identifique la restriccion y se detenga con informe).
# `numericas`: columnas a convertir a numero en la limpieza.
# --------------------------------------------------------------------------
QUOTES_HTML = """
texto*=span.text
autor*=small.author
etiqueta=a.tag
"""

ESCENARIOS = [
    {
        "id": "01_html_estatico", "nombre": "HTML estático",
        "sitio": "quotes.toscrape.com", "mecanismo": "HTML estático (renderizado en servidor)",
        "estrategia": "requests + selectores CSS", "esperado": "extraccion",
        "campos": QUOTES_HTML,
        "config": dict(url="https://quotes.toscrape.com/", method=AcquisitionMethod.REQUESTS,
                       item_selector="div.quote", max_pages=1, max_records=20),
        "proteccion": "Ninguna (sandbox público de práctica)",
        "observacion": "Una página, HTTP directo; sin JavaScript necesario.",
    },
    {
        "id": "02_javascript", "nombre": "Sitio con JavaScript",
        "sitio": "quotes.toscrape.com/js/", "mecanismo": "Contenido renderizado por JavaScript",
        "estrategia": "selenium headless (DOM renderizado)", "esperado": "extraccion",
        "campos": QUOTES_HTML,
        "config": dict(url="https://quotes.toscrape.com/js/", method=AcquisitionMethod.SELENIUM,
                       item_selector="div.quote", max_pages=1, max_records=10),
        "proteccion": "Renderizado en cliente (sin WAF)",
        "observacion": "El HTML inicial no contiene las citas; se leen del DOM tras ejecutar JS.",
    },
    {
        "id": "03_api_json", "nombre": "Información vía API",
        "sitio": "quotes.toscrape.com/api/quotes", "mecanismo": "API JSON pública",
        "estrategia": "api (GET JSON, ruta `quotes`, autorización confirmada)", "esperado": "extraccion",
        "campos": "texto*=text\nautor*=author.name\nautor_slug=author.slug",
        "config": dict(url="https://quotes.toscrape.com/api/quotes?page=1", method=AcquisitionMethod.API,
                       json_records_path="quotes", authorized_api=True, max_pages=1, max_records=10),
        "proteccion": "Ninguna (API pública de práctica, sin autenticación)",
        "observacion": "Endpoint público de un sandbox pensado para prácticas; se declara autorizado.",
    },
    {
        "id": "04_paginacion", "nombre": "Paginación",
        "sitio": "books.toscrape.com", "mecanismo": "Paginación por enlace «siguiente»",
        "estrategia": "requests + selector de paginación `li.next a` (3 páginas)", "esperado": "extraccion",
        "campos": "titulo*=h3 a::title\nprecio*=p.price_color\ndisponibilidad=p.instock.availability\n"
                  "rating=p.star-rating::class",
        "config": dict(url="https://books.toscrape.com/", method=AcquisitionMethod.REQUESTS,
                       item_selector="article.product_pod", pagination_selector="li.next a",
                       max_pages=3, max_records=60),
        "numericas": {"precio": "precio_gbp"},
        "proteccion": "Ninguna (sandbox público de práctica)",
        "observacion": "Sigue la paginación solo dentro del mismo host y con pausa de 2 s.",
    },
    {
        "id": "05_scroll_infinito", "nombre": "Scroll infinito",
        "sitio": "quotes.toscrape.com/scroll", "mecanismo": "Carga progresiva por scroll infinito (AJAX)",
        "estrategia": "selenium headless + 2 desplazamientos acotados", "esperado": "extraccion",
        "campos": QUOTES_HTML,
        "config": dict(url="https://quotes.toscrape.com/scroll", method=AcquisitionMethod.SELENIUM,
                       item_selector="div.quote", scroll_steps=2, max_pages=1, max_records=30),
        "proteccion": "Renderizado en cliente (sin WAF)",
        "observacion": "Cada scroll dispara una petición AJAX que añade más citas.",
    },
    {
        "id": "06_tablas", "nombre": "Tablas HTML",
        "sitio": "scrapethissite.com/pages/forms/", "mecanismo": "Tabla HTML con paginación",
        "estrategia": "requests + filas `tr.team` y paginación `a[aria-label=Next]` (2 páginas)",
        "esperado": "extraccion",
        "campos": "equipo*=td.name\nanio*=td.year\nvictorias=td.wins\nderrotas=td.losses\n"
                  "porcentaje_victorias=td.pct\ngoles_favor=td.gf\ngoles_contra=td.ga",
        "config": dict(url="https://www.scrapethissite.com/pages/forms/?page_num=1", method=AcquisitionMethod.REQUESTS,
                       item_selector="tr.team", pagination_selector='a[aria-label="Next"]',
                       max_pages=2, max_records=50),
        "numericas": {"anio": "anio", "victorias": "victorias", "derrotas": "derrotas",
                      "porcentaje_victorias": "porcentaje_victorias",
                      "goles_favor": "goles_favor", "goles_contra": "goles_contra"},
        "proteccion": "Ninguna (sandbox público de práctica)",
        "observacion": "Se extrae por columnas con clases de `td`; el mismo motor, otro selector. "
                       "Se parte de `?page_num=1` porque el enlace «siguiente» de la URL sin parámetro apunta a la misma página.",
    },
    {
        "id": "07_bajo_demanda", "nombre": "Contenido bajo demanda (AJAX)",
        "sitio": "scrapethissite.com/pages/ajax-javascript/", "mecanismo": "Contenido cargado tras un clic (AJAX)",
        "estrategia": "selenium + clic acotado en `a.year-link` (carga bajo demanda)", "esperado": "extraccion",
        "campos": "pelicula*=td.film-title\nnominaciones=td.film-nominations\npremios=td.film-awards",
        "config": dict(url="https://www.scrapethissite.com/pages/ajax-javascript/",
                       method=AcquisitionMethod.SELENIUM, item_selector="tr.film",
                       load_more_selector="a.year-link", load_more_clicks=2,
                       max_pages=1, max_records=30),
        "numericas": {"nominaciones": "nominaciones", "premios": "premios"},
        "proteccion": "Renderizado en cliente (sin WAF)",
        "observacion": "La tabla está vacía hasta pulsar un año; la página añade una espera artificial de 1,5 s.",
    },
    {
        "id": "08_autenticacion", "nombre": "Autenticación autorizada",
        "sitio": "quotes.toscrape.com/login", "mecanismo": "Formulario de inicio de sesión",
        "estrategia": "selenium: detectar login y detenerse (no se automatiza el acceso)",
        "esperado": "incidencia",
        "campos": "usuario=input#username::name",
        "config": dict(url="https://quotes.toscrape.com/login", method=AcquisitionMethod.SELENIUM,
                       item_selector="form", max_pages=1, max_records=1),
        "proteccion": "Autenticación (formulario de login)",
        "observacion": "La herramienta no envía credenciales; extraer tras el login exige autorización "
                       "del titular y un mecanismo permitido (p. ej. token/encabezado autorizado).",
    },
    {
        "id": "09_captcha", "nombre": "CAPTCHA → incidencia",
        "sitio": "google.com/recaptcha/api2/demo", "mecanismo": "CAPTCHA (reCAPTCHA v2)",
        "estrategia": "requests: detectar CAPTCHA, detener y reportar (no se resuelve)",
        "esperado": "incidencia",
        "campos": "titulo=title",
        "config": dict(url="https://www.google.com/recaptcha/api2/demo", method=AcquisitionMethod.REQUESTS,
                       item_selector="body", max_pages=1, max_records=1),
        "proteccion": "CAPTCHA / verificación anti-bot",
        "observacion": "Página demo oficial de reCAPTCHA; el robots.txt de Google no permite la ruta, "
                       "así que la herramienta ni siquiera la solicita (control de cortesía previo al diagnóstico).",
    },
    {
        "id": "10_captcha_incidencia", "nombre": "CAPTCHA → incidencia (diagnóstico y reporte)",
        "sitio": "nopecha.com/demo/recaptcha", "mecanismo": "CAPTCHA (reCAPTCHA v2)",
        "estrategia": "requests: detectar CAPTCHA, detener y reportar (no se resuelve)",
        "esperado": "incidencia",
        "campos": "titulo=title",
        "config": dict(url="https://nopecha.com/demo/recaptcha", method=AcquisitionMethod.REQUESTS,
                       item_selector="body", max_pages=1, max_records=1),
        "proteccion": "CAPTCHA / verificación anti-bot",
        "observacion": "Demo pública de CAPTCHA (robots.txt permite todo); una sola solicitud de diagnóstico, "
                       "sin intento de resolverlo ni evadirlo.",
    },
]


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------
_robots_cache: dict[str, RobotFileParser | None] = {}


def robots_permite(url: str) -> dict:
    """Consulta robots.txt del host (1 GET por host) y evalua si la URL esta permitida."""
    p = urlparse(url)
    origen = f"{p.scheme}://{p.netloc}"
    if origen not in _robots_cache:
        rp = RobotFileParser()
        try:
            r = requests.get(f"{origen}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=15)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            elif r.status_code in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True  # sin robots.txt: no hay restriccion declarada
            _robots_cache[origen] = rp
            estado = f"HTTP {r.status_code}"
        except requests.RequestException as exc:
            _robots_cache[origen] = None
            estado = f"sin respuesta ({type(exc).__name__})"
        time.sleep(PAUSA_ENTRE_ESCENARIOS)
        _robots_cache[origen + "#estado"] = estado  # type: ignore[assignment]
    rp = _robots_cache[origen]
    estado = _robots_cache.get(origen + "#estado", "")
    permitido = True if rp is None else rp.can_fetch(USER_AGENT, url)
    return {"robots_url": f"{origen}/robots.txt", "robots_estado": estado, "permitido_por_robots": permitido}


# --------------------------------------------------------------------------
# Clasificacion de proteccion y viabilidad
# --------------------------------------------------------------------------
def clasificar(esc: dict, estado: str, diag: dict, error: str) -> tuple[str, str]:
    """Devuelve (esquema de proteccion, viabilidad legal/tecnica) segun diagnostico y resultado."""
    metodo = esc["config"]["method"]
    if estado == "omitido_robots":
        return "robots.txt no permite la ruta", "No viable – robots.txt"
    texto = f"{error} {' '.join(diag.get('warnings', []))}".lower()
    if diag.get("captcha_detected") or "captcha" in texto:
        return "CAPTCHA / verificación anti-bot", "No viable – CAPTCHA"
    if diag.get("authentication_detected") or "autenticaci" in texto:
        return "Autenticación (formulario de login)", "Requiere autorización"
    if diag.get("status_code") in (401, 403, 429):
        return f"Acceso restringido (HTTP {diag['status_code']})", "No viable – acceso restringido"
    if estado != "completed":
        return esc["proteccion"], "No concluyente – falló la ejecución"
    if metodo == AcquisitionMethod.API:
        return esc["proteccion"], "Viable (API pública autorizada)"
    if metodo in (AcquisitionMethod.SELENIUM, AcquisitionMethod.PLAYWRIGHT):
        return esc["proteccion"], "Viable con navegador"
    return esc["proteccion"], "Viable"


def resumen_diagnostico(diag: dict) -> dict:
    return {
        "http": diag.get("status_code"),
        "renderizado": diag.get("rendering"),
        "formularios": diag.get("has_forms"),
        "autenticacion": diag.get("authentication_detected"),
        "captcha": diag.get("captcha_detected"),
        "bloqueado": diag.get("blocked"),
        "paginacion": diag.get("pagination_detected"),
        "cargar_mas": diag.get("load_more_detected"),
        "scroll_infinito": diag.get("infinite_scroll_suspected"),
        "interaccion_usuario": diag.get("user_interaction_suspected"),
        "pistas_api": (diag.get("api_hints") or [])[:5],
    }


def mecanismo_detectado(diag: dict, esc: dict) -> str:
    """Mecanismo segun lo que detecto el diagnostico automatico (no lo declarado)."""
    if not diag:
        return "sin diagnóstico"
    señales = []
    if diag.get("captcha_detected"):
        señales.append("CAPTCHA")
    if diag.get("authentication_detected"):
        señales.append("login")
    if "json" in str(diag.get("content_type", "")).lower():
        señales.append("API JSON")
    elif "estático" in str(diag.get("rendering", "")).lower() and not señales:
        señales.append("HTML estático")
    elif "din" in str(diag.get("rendering", "")).lower():
        señales.append("JS/dinámico")
    if diag.get("pagination_detected"):
        señales.append("paginación")
    if diag.get("infinite_scroll_suspected"):
        señales.append("scroll infinito")
    if diag.get("load_more_detected") or diag.get("user_interaction_suspected"):
        señales.append("carga bajo demanda")
    return ", ".join(señales) or str(diag.get("rendering", "desconocido"))


# --------------------------------------------------------------------------
# Ejecucion de un escenario con el motor unico
# --------------------------------------------------------------------------
def construir_config(esc: dict) -> ScrapeConfig:
    return ScrapeConfig(fields=parse_field_rules(esc["campos"]), delay_seconds=2.0,
                        timeout_seconds=20, headless=True, **esc["config"])


def ejecutar(esc: dict) -> dict:
    cfg = construir_config(esc)
    salida = RUNS / esc["id"]
    if salida.exists():
        shutil.rmtree(salida)
    res = {
        "escenario": esc["id"], "nombre": esc["nombre"], "sitio": esc["sitio"], "url": cfg.url,
        "metodo": cfg.method.value, "mecanismo_declarado": esc["mecanismo"],
        "estrategia": esc["estrategia"], "esperado": esc["esperado"],
        "config": {"max_pages": cfg.max_pages, "max_records": cfg.max_records,
                   "delay_seconds": cfg.delay_seconds, "scroll_steps": cfg.scroll_steps,
                   "load_more_clicks": cfg.load_more_clicks, "item_selector": cfg.item_selector,
                   "campos": esc["campos"].strip().splitlines()},
    }
    res.update(robots_permite(cfg.url))
    if not res["permitido_por_robots"]:
        res.update(estado="omitido_robots", registros=0, paginas=0, advertencias=[],
                   error="robots.txt no permite esta ruta para el User-Agent de la herramienta.",
                   execution_id="", diagnostico={}, salidas=[])
    else:
        outcome, error = None, ""
        try:
            outcome = run_job(cfg, salida, "excel")
        except RunFailure as exc:
            outcome, error = exc.outcome, str(exc)
        except Exception as exc:  # fallo previo al informe (p. ej. validacion)
            error = f"{type(exc).__name__}: {exc}"
        if outcome is None:
            res.update(estado="failed", registros=0, paginas=0, advertencias=[], error=error,
                       execution_id="", diagnostico={}, salidas=[])
        else:
            rep = outcome.report
            res.update(estado=rep.status, registros=rep.records_saved, paginas=rep.pages_visited,
                       advertencias=rep.warnings, error=rep.error or error,
                       execution_id=rep.execution_id, diagnostico=outcome.diagnostic,
                       salidas=[Path(p).relative_to(ROOT).as_posix() if Path(p).is_absolute() else p
                                for p in rep.output_paths], cambios=rep.changes,
                       iniciado_utc=rep.started_at)
    diag = res["diagnostico"]
    res["diagnostico_resumen"] = resumen_diagnostico(diag)
    res["mecanismo_detectado"] = mecanismo_detectado(diag, esc)
    res["proteccion"], res["viabilidad"] = clasificar(esc, res["estado"], diag, res["error"])
    res["observacion"] = esc["observacion"]
    return res


# --------------------------------------------------------------------------
# Limpieza y consolidacion
# --------------------------------------------------------------------------
def limpiar(raw: pd.DataFrame, esc: dict) -> pd.DataFrame:
    df = raw.copy()
    for col in df.columns:
        df[col] = df[col].map(lambda v: re.sub(r"\s+", " ", str(v)).strip() if pd.notna(v) else None)
    df = df.dropna(how="all").drop_duplicates().reset_index(drop=True)
    # Citas: quitar comillas tipograficas envolventes.
    if "texto" in df.columns:
        df["texto"] = df["texto"].str.strip("“”\"")
    # Libros: la clase CSS "['star-rating', 'Three']" -> numero 1..5.
    if "rating" in df.columns:
        mapa = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
        df["rating"] = df["rating"].map(
            lambda v: next((n for k, n in mapa.items() if k in str(v)), None)).astype("Int64")
    if "disponibilidad" in df.columns:
        df["disponibilidad"] = df["disponibilidad"].str.contains("in stock", case=False, na=False)
    for origen, destino in esc.get("numericas", {}).items():
        if origen in df.columns:
            df[origen] = pd.to_numeric(df[origen].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
                                       errors="coerce")
            if destino != origen:
                df = df.rename(columns={origen: destino})
    return df


def consolidar(resultados: list[dict]) -> dict:
    anchos: dict[str, pd.DataFrame] = {}
    largos, linajes = [], []
    for esc, res in zip(ESCENARIOS, resultados):
        if res["estado"] != "completed":
            continue
        xlsx = next((RUNS / esc["id"]).glob("records-*.xlsx"), None)
        if xlsx is None:
            continue
        df = limpiar(pd.read_excel(xlsx, sheet_name="records"), esc)
        if df.empty:
            continue
        lin = pd.read_excel(xlsx, sheet_name="lineage")
        lin.insert(0, "escenario", esc["id"])
        lin["transformations"] = lin["transformations"].astype(str)
        linajes.append(lin)
        ancho = df.copy()
        ancho.insert(0, "registro_id", range(1, len(ancho) + 1))
        ancho.insert(0, "escenario", esc["id"])
        ancho["url_origen"] = res["url"]
        ancho["metodo"] = res["metodo"]
        ancho["execution_id"] = res["execution_id"]
        anchos[esc["id"]] = ancho
        meta = ["escenario", "registro_id", "url_origen", "metodo", "execution_id"]
        largos.append(ancho.melt(id_vars=meta, var_name="campo", value_name="valor")
                      .dropna(subset=["valor"]).assign(valor=lambda d: d["valor"].astype(str)))
    return {"anchos": anchos,
            "largo": pd.concat(largos, ignore_index=True) if largos else pd.DataFrame(),
            "linaje": pd.concat(linajes, ignore_index=True) if linajes else pd.DataFrame()}


def tabla_ejecuciones(resultados: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "escenario": r["escenario"], "nombre": r["nombre"], "url": r["url"], "metodo": r["metodo"],
        "estado": r["estado"], "registros": r["registros"], "paginas": r["paginas"],
        "execution_id": r["execution_id"], "mecanismo_detectado": r["mecanismo_detectado"],
        "proteccion": r["proteccion"], "viabilidad": r["viabilidad"],
        "error": r["error"], "advertencias": " | ".join(r["advertencias"]),
    } for r in resultados])


def guardar_dataset(resultados: list[dict], cons: dict) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    ejec = tabla_ejecuciones(resultados)
    cons["largo"].to_csv(BASE / "dataset_multisitio.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(BASE / "dataset_multisitio.xlsx", engine="openpyxl") as w:
        ejec.to_excel(w, sheet_name="resumen", index=False)
        for nombre, df in cons["anchos"].items():
            df.to_excel(w, sheet_name=nombre[:31], index=False)
        if not cons["linaje"].empty:
            cons["linaje"].to_excel(w, sheet_name="linaje", index=False)
    db = BASE / "dataset_multisitio.sqlite"
    db.unlink(missing_ok=True)
    with sqlite3.connect(db) as con:
        cons["largo"].to_sql("registros", con, index=False)
        cons["linaje"].to_sql("linaje", con, index=False)
        ejec.to_sql("ejecuciones", con, index=False)
        for nombre, df in cons["anchos"].items():
            out = df.copy()
            for c in out.columns:
                if str(out[c].dtype) == "boolean" or out[c].dtype == bool:
                    out[c] = out[c].astype(int)
                elif str(out[c].dtype) == "Int64":
                    out[c] = out[c].astype(object).where(out[c].notna(), None)
            out.to_sql(f"esc_{nombre}", con, index=False)


# --------------------------------------------------------------------------
# Evidencia: JSON y matriz Markdown
# --------------------------------------------------------------------------
def escribir_matriz(resultados: list[dict], fecha: str) -> Path:
    def cel(x) -> str:
        return str(x).replace("|", "/").replace("\n", " ")
    sitios = {r["sitio"].split("/")[0] for r in resultados}
    mecanismos = {r["mecanismo_declarado"] for r in resultados}
    metodos = {r["metodo"] for r in resultados}
    ok = [r for r in resultados if r["estado"] == "completed"]
    inc = [r for r in resultados if r["estado"] != "completed"]
    lineas = [
        "# Matriz de escenarios — Reto final",
        "",
        f"Generada por `scripts/evidencia_extraccion.py` el {fecha} (UTC). Un único motor "
        "(`smart_scraper.app.run_job`) ejecuta todos los escenarios; cada uno es solo una configuración.",
        "",
        f"- Sitios distintos probados: **{len(sitios)}** ({', '.join(sorted(sitios))})",
        f"- Escenarios ejecutados: **{len(resultados)}**; mecanismos de adquisición/escenario distintos: "
        f"**{len(mecanismos)}**; métodos del motor usados: **{len(metodos)}** ({', '.join(sorted(metodos))})",
        f"- Extracciones completadas: **{len(ok)}** ({sum(r['registros'] for r in ok)} registros); "
        f"incidencias/restricciones identificadas con informe: **{len(inc)}**",
        "",
        "| Escenario | Sitio | Mecanismo detectado | Estrategia elegida | Resultado | Registros | "
        "Esquema de protección | Viabilidad legal/técnica | Observación |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        resultado = {"completed": "Completado", "failed": "Detenido (incidencia)" if r["esperado"] == "incidencia"
                     else "Falló", "omitido_robots": "Omitido (robots.txt)"}.get(r["estado"], r["estado"])
        obs = r["observacion"]
        if r["error"]:
            obs += f" Informe: «{r['error'][:140]}»"
        lineas.append("| " + " | ".join(cel(x) for x in [
            r["nombre"], r["sitio"], r["mecanismo_detectado"], f"{r['estrategia']} [{r['metodo']}]",
            resultado, r["registros"], r["proteccion"], r["viabilidad"], obs]) + " |")
    lineas += ["", "Evidencia completa: `docs/evidencias/extraccion_" + fecha + ".json`; informes por "
               "escenario en `datasets/multisitio/runs/<escenario>/report-*.json`.", ""]
    destino = EVIDENCIAS / "MATRIZ_ESCENARIOS.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino


def retirar_residuos() -> None:
    """Quita logs e historiales locales de las corridas (ruido; el informe JSON ya lo conserva)."""
    logging.shutdown()  # libera los manejadores de archivo (en Windows bloquean el borrado)
    for patron in ("smart_scraper.log", ".scraper_history.sqlite3"):
        for f in RUNS.glob(f"*/{patron}"):
            try:
                f.unlink()
            except OSError:
                pass


def main() -> int:
    EVIDENCIAS.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    resultados = []
    for i, esc in enumerate(ESCENARIOS):
        if i:
            time.sleep(PAUSA_ENTRE_ESCENARIOS)
        print(f"[{esc['id']}] {esc['url'] if 'url' in esc else esc['config']['url']}")
        res = ejecutar(esc)
        print(f"    estado={res['estado']} registros={res['registros']} paginas={res['paginas']} "
              f"viabilidad={res['viabilidad']}" + (f" error={res['error'][:100]}" if res["error"] else ""))
        resultados.append(res)
    retirar_residuos()
    cons = consolidar(resultados)
    guardar_dataset(resultados, cons)
    fecha = ahora.strftime("%Y-%m-%d")
    evidencia = {"generado_utc": ahora.isoformat(), "user_agent": USER_AGENT,
                 "motor": "smart_scraper.app.run_job", "resultados": resultados}
    destino = EVIDENCIAS / f"extraccion_{fecha}.json"
    destino.write_text(json.dumps(evidencia, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    matriz = escribir_matriz(resultados, fecha)
    print("Guardado", destino, matriz, BASE, sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
