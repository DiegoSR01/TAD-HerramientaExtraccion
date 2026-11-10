"""Recolecta evidencia de bajo impacto sobre esquemas de proteccion de sitios.

Para cada sitio hace UNA peticion GET a la pagina y UNA a /robots.txt, con
pausa de 2 s entre peticiones, timeout de 15 s, User-Agent honesto, TLS
verificado y sin reintentos. No evade ninguna proteccion: si el sitio
responde 403, CAPTCHA o error TLS, solo se registra.

Reutiliza `smart_scraper.inspector.diagnose` para el analisis del HTML (la
funcion `inspect_url` no expone las cabeceras completas, por eso la peticion
se hace aqui y el cuerpo se pasa a `diagnose`).

Salidas:
  docs/evidencias/sitios_<fecha>.json   resultados crudos
  docs/evidencias/robots/<host>.txt     resumen de robots.txt por sitio

Uso:  python scripts/evidencia_sitios.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smart_scraper.inspector import diagnose  # noqa: E402

SITIOS = [
    "https://www.inegi.org.mx/datosabiertos/",
    "https://www.datos.gob.mx/",
    "https://data.worldbank.org/",
    "https://data.gov/",
    "https://www.dof.gob.mx/",
    "https://books.toscrape.com/",
    "https://quotes.toscrape.com/",
]
USER_AGENT = "TAD-SmartScraper/0.1 (proyecto academico)"
TIMEOUT = 15
PAUSA = 2
MAX_BYTES = 2_000_000
CABECERAS = [
    "server", "via", "cf-ray", "cf-cache-status", "x-cache", "x-amz-cf-id",
    "x-akamai-transformed", "x-served-by", "x-powered-by", "strict-transport-security",
    "content-type", "retry-after", "x-frame-options",
]
# Nombres de cookie asociados a WAF/CDN conocidos (solo se registran nombres).
WAF_COOKIES = ("__cf_bm", "cf_clearance", "__cfduid", "incap_ses", "visid_incap", "nlbi_",
               "ak_bmsc", "bm_sz", "_abck", "awsalb", "awsalbcors", "aws-waf-token",
               "ts", "barracuda", "sucuri", "citrix_ns_id", "f5avr", "bigipserver")
SPA_MARCADORES = ("__next_data__", "ng-version", "data-reactroot", "id=\"root\"", "id=\"app\"",
                  "__nuxt", "webpack", "enable javascript", "habilita javascript")
CHALLENGE_MARCADORES = ("just a moment", "attention required", "access denied",
                        "cf-chl-", "captcha", "request unsuccessful", "incapsula")


def peticion(url: str) -> dict:
    """Una sola peticion GET, sin reintentos, TLS verificado, lectura acotada."""
    t0 = time.monotonic()
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
                            stream=True, allow_redirects=True)
        body = b""
        for chunk in resp.iter_content(16_384):
            body += chunk
            if len(body) > MAX_BYTES:
                body = body[:MAX_BYTES]
                break
        resp.close()
        return {"ok": True, "url_final": resp.url, "status": resp.status_code,
                "segundos": round(time.monotonic() - t0, 2), "headers": dict(resp.headers),
                "body": body, "error": None}
    except requests.exceptions.SSLError as exc:
        return {"ok": False, "tipo_error": "TLS", "error": str(exc)[:400]}
    except requests.RequestException as exc:
        return {"ok": False, "tipo_error": type(exc).__name__, "error": str(exc)[:400]}


def analizar_pagina(r: dict) -> dict:
    if not r["ok"]:
        return {"error_tipo": r["tipo_error"], "error": r["error"]}
    h = {k.lower(): v for k, v in r["headers"].items()}
    body: bytes = r["body"]
    texto = body.decode("utf-8", errors="replace").lower()
    rep = diagnose(r["url_final"], r["status"], h.get("content-type", ""), body)
    cookies = re.findall(r"(?:^|,\s*)([A-Za-z0-9_\-\.]+)=", h.get("set-cookie", ""))
    waf = sorted({c for c in cookies if any(c.lower().startswith(w) for w in WAF_COOKIES)})
    return {
        "url_final": r["url_final"], "status": r["status"], "segundos": r["segundos"],
        "bytes": len(body), "titulo": rep.title,
        "cabeceras": {k: h[k] for k in CABECERAS if k in h},
        "cabeceras_akamai": {k: v for k, v in h.items() if "akamai" in k},
        "set_cookie_nombres": sorted(set(cookies)),
        "set_cookie_waf": waf,
        "csp_presente": "content-security-policy" in h,
        "senales_js_spa": [m for m in SPA_MARCADORES if m in texto],
        "rendering_inspector": rep.rendering,
        "captcha_detectado": rep.captcha_detected,
        "marcadores_challenge": [m for m in CHALLENGE_MARCADORES if m in texto],
        "bloqueado_inspector": rep.blocked,
        "paginacion": rep.pagination_detected,
        "api_hints": rep.api_hints[:10],
    }


def analizar_robots(r: dict) -> dict:
    if not r["ok"]:
        return {"error_tipo": r["tipo_error"], "error": r["error"]}
    texto = r["body"].decode("utf-8", errors="replace")
    es_robots = "text/plain" in r["headers"].get("Content-Type", "").lower() or \
        re.search(r"(?im)^\s*(user-agent|disallow)\s*:", texto) is not None
    res = {"status": r["status"], "url_final": r["url_final"], "bytes": len(r["body"]),
           "parece_robots": bool(es_robots), "crawl_delay": [], "sitemaps": [],
           "disallow_agente_todos": [], "bloqueos_ia_o_generales": []}
    if not es_robots:
        return res
    agentes: list[str] = []
    previo_regla = False
    for linea in texto.splitlines():
        linea = linea.split("#", 1)[0].strip()
        if ":" not in linea:
            continue
        k, v = (s.strip() for s in linea.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if previo_regla:
                agentes, previo_regla = [], False
            agentes.append(v)
        elif k == "disallow":
            previo_regla = True
            if v and "*" in agentes:
                res["disallow_agente_todos"].append(v)
        elif k == "crawl-delay":
            previo_regla = True
            res["crawl_delay"].append({"agentes": list(agentes), "valor": v})
        elif k == "sitemap":
            res["sitemaps"].append(v)
    res["disallow_agente_todos"] = res["disallow_agente_todos"][:60]
    res["disallow_raiz_total"] = "/" in res["disallow_agente_todos"]
    res["texto_crudo_primeros_3000"] = texto[:3000]
    return res


def escribir_robots(host: str, url: str, robots: dict, dest: Path) -> None:
    lineas = [f"Sitio: {url}", f"robots.txt consultado: {datetime.now(timezone.utc).isoformat()}"]
    if "error" in robots:
        lineas.append(f"No se obtuvo robots.txt: {robots['error_tipo']} - {robots['error']}")
    else:
        lineas.append(f"HTTP {robots['status']} ({robots['bytes']} bytes); parece robots.txt valido: "
                      f"{robots['parece_robots']}")
        if robots["parece_robots"]:
            lineas.append(f"Disallow para User-agent '*': {len(robots['disallow_agente_todos'])}")
            lineas += [f"  Disallow: {d}" for d in robots["disallow_agente_todos"]]
            lineas.append(f"Disallow total de '/': {robots.get('disallow_raiz_total')}")
            lineas.append(f"Crawl-delay: {robots['crawl_delay'] or 'no declarado'}")
            lineas.append(f"Sitemaps: {robots['sitemaps'] or 'ninguno'}")
        else:
            lineas.append("La respuesta no parece un robots.txt (sin reglas); no hay politica declarada.")
    dest.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main() -> None:
    ahora = datetime.now(timezone.utc)
    out_dir = ROOT / "docs" / "evidencias"
    (out_dir / "robots").mkdir(parents=True, exist_ok=True)
    resultados = []
    primera = True
    for url in SITIOS:
        p = urlparse(url)
        host = p.netloc
        item = {"sitio": url, "host": host}
        for clave, objetivo, analizador in (
            ("pagina", url, analizar_pagina),
            ("robots", f"{p.scheme}://{host}/robots.txt", analizar_robots),
        ):
            if not primera:
                time.sleep(PAUSA)
            primera = False
            item[clave] = analizador(peticion(objetivo))
            print(host, clave, item[clave].get("status", item[clave].get("error_tipo")))
        escribir_robots(host, url, item["robots"], out_dir / "robots" / f"{host}.txt")
        resultados.append(item)
    salida = {"generado_utc": ahora.isoformat(), "user_agent": USER_AGENT,
              "timeout_s": TIMEOUT, "pausa_s": PAUSA, "resultados": resultados}
    destino = out_dir / f"sitios_{ahora.strftime('%Y-%m-%d')}.json"
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Guardado", destino)


if __name__ == "__main__":
    main()
