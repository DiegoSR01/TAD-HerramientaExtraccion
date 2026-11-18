"""Inspección de bajo impacto de una URL antes de extraer datos.

Rol en la arquitectura: módulo de inspección/diagnóstico. Hace una única
solicitud GET acotada y analiza el HTML en busca de señales de renderizado
dinámico, paginación, "cargar más", scroll infinito, formularios, endpoints
de API, autenticación y CAPTCHA. Marca como ``blocked`` las respuestas 401,
403 y 429 o la presencia de CAPTCHA, para que el resto del sistema se detenga
sin intentar evadir la restricción.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MAX_HTML_BYTES = 2_000_000
DEFAULT_USER_AGENT = "SmartWebScraper/1.0 (user-initiated; responsible access)"
_CAPTCHA_MARKERS = ("captcha", "hcaptcha", "recaptcha", "cf-chl-", "verify you are human")
_AUTH_MARKERS = ("type=\"password\"", "type='password'", "name=\"password\"", "name='password'")
_API_PATTERN = re.compile(
    r"""(?:(?:https?:)?//[^\s"'<>]+|/[A-Za-z0-9_./?=&%-]+)""",
    re.IGNORECASE,
)


@dataclass
class InspectionReport:
    """Diagnóstico de una página.

    Atributos principales:
        status_code, content_type, title: datos básicos de la respuesta.
        rendering: "HTML estático" o "dinámico o mixto" (heurístico).
        authentication_detected, captcha_detected: señales de restricción.
        blocked: ``True`` si hay 401/403/429 o CAPTCHA; se debe detener el acceso.
        pagination_detected, load_more_detected, infinite_scroll_suspected,
        user_interaction_suspected: señales de carga bajo demanda.
        api_hints: posibles endpoints del mismo host.
        warnings: mensajes legibles para el usuario.
    """
    url: str
    status_code: int
    content_type: str
    title: str = ""
    rendering: str = "desconocido"
    has_forms: bool = False
    authentication_detected: bool = False
    captcha_detected: bool = False
    blocked: bool = False
    pagination_detected: bool = False
    load_more_detected: bool = False
    infinite_scroll_suspected: bool = False
    user_interaction_suspected: bool = False
    api_hints: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Devuelve el informe como diccionario serializable a JSON."""
        return asdict(self)


@dataclass
class InspectedPage:
    """Página inspeccionada: informe, cuerpo crudo, encabezados y codificación.

    Permite reutilizar la respuesta ya descargada sin repetir la solicitud.
    """
    report: InspectionReport
    body: bytes
    headers: dict[str, str]
    encoding: str | None


class InspectionError(RuntimeError):
    """Error al inspeccionar o adquirir una URL (red, tamaño excedido o HTTP de error)."""
    pass


def inspect_url(
    url: str, timeout_seconds: int = 15, headers: dict[str, str] | None = None
) -> InspectedPage:
    """Hace una sola solicitud GET con tamaño máximo y sin seguir páginas automáticamente.

    La respuesta se lee por bloques y se aborta si supera ``MAX_HTML_BYTES``.
    Se identifica con un User-Agent explícito y no evade restricciones.

    Args:
        url: URL http/https a inspeccionar.
        timeout_seconds: tiempo límite de la solicitud.
        headers: encabezados autorizados adicionales (no se almacenan).

    Returns:
        ``InspectedPage`` con el diagnóstico y el cuerpo descargado.

    Raises:
        InspectionError: si falla la red o la respuesta excede el límite.
    """
    try:
        response = requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": DEFAULT_USER_AGENT, **(headers or {})},
            stream=True,
            allow_redirects=True,
        )
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=16_384):
            size += len(chunk)
            if size > MAX_HTML_BYTES:
                response.close()
                raise InspectionError(
                    f"La respuesta supera el límite de {MAX_HTML_BYTES} bytes; se detuvo la lectura."
                )
            chunks.append(chunk)
        body = b"".join(chunks)
        report = diagnose(
            response.url,
            response.status_code,
            response.headers.get("Content-Type", ""),
            body,
        )
        response_headers = {"Content-Type": response.headers.get("Content-Type", "")}
        encoding = response.encoding
        response.close()
        return InspectedPage(report, body, response_headers, encoding)
    except requests.RequestException as exc:
        raise InspectionError(f"No se pudo inspeccionar la URL: {exc}") from exc


def diagnose(url: str, status_code: int, content_type: str, body: bytes) -> InspectionReport:
    """Analiza una respuesta y genera un ``InspectionReport``.

    Detecta endpoints candidatos del mismo host, formularios, autenticación
    (HTTP 401 o formulario con contraseña), CAPTCHA, paginación, "cargar más",
    scroll infinito y uso de JavaScript. Marca ``blocked`` ante 401/403/429 o
    CAPTCHA y añade advertencias; las señales son heurísticas.

    Args:
        url: URL final de la respuesta.
        status_code: código HTTP.
        content_type: valor del encabezado Content-Type.
        body: contenido de la respuesta en bytes.

    Returns:
        Informe de diagnóstico.
    """
    text = body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    scripts = "\n".join(script.get_text(" ", strip=True) for script in soup.find_all("script"))
    script_sources = [script.get("src", "") for script in soup.find_all("script") if script.get("src")]
    source = f"{text}\n{scripts}".lower()
    parsed = urlparse(url)
    hints = set()
    for script_url in script_sources:
        candidate = urljoin(url, script_url)
        if urlparse(candidate).netloc == parsed.netloc and any(
            token in candidate.lower() for token in ("api", "graphql", "json")
        ):
            hints.add(candidate)
    if any(token in parsed.path.lower() for token in ("/api/", "graphql", ".json")):
        hints.add(url)
    for match in _API_PATTERN.findall(text):
        if any(token in match.lower() for token in ("/api/", "graphql", ".json")):
            candidate = urljoin(url, match.rstrip(".,);"))
            if urlparse(candidate).netloc == parsed.netloc:
                hints.add(candidate)

    forms = soup.find_all("form")
    captcha = any(marker in source for marker in _CAPTCHA_MARKERS)
    auth_status = status_code == 401
    auth_form = any(marker in source for marker in _AUTH_MARKERS)
    pagination = bool(
        soup.select_one('a[rel~="next"], a.next, .pagination a[aria-label*="next" i]')
        or re.search(r">\s*(?:next|siguiente|older)\s*<", text, re.IGNORECASE)
    )
    load_more = any(
        re.search(r"load more|show more|cargar más|ver más", element.get_text(" ", strip=True), re.I)
        for element in soup.find_all(["button", "a"])
    )
    infinite = any(
        indicator in source
        for indicator in ("intersectionobserver", "infinite-scroll", "infinite_scroll", "onscroll")
    )
    interaction = any(
        re.search(r"click|onclick|addEventListener", script.get_text(" ", strip=True), re.I)
        for script in soup.find_all("script")
    ) and not pagination and not load_more
    dynamic = bool(scripts or script_sources)
    report = InspectionReport(
        url=url,
        status_code=status_code,
        content_type=content_type,
        title=title,
        rendering="dinámico o mixto" if dynamic else "HTML estático",
        has_forms=bool(forms),
        authentication_detected=auth_status or (bool(forms) and auth_form),
        captcha_detected=captcha,
        blocked=status_code in {401, 403, 429} or captcha,
        pagination_detected=pagination,
        load_more_detected=load_more,
        infinite_scroll_suspected=infinite,
        user_interaction_suspected=interaction,
        api_hints=sorted(hints),
    )
    if status_code == 429:
        report.warnings.append("El servidor respondió 429; detén las solicitudes y consulta al responsable.")
    if status_code >= 400 and status_code != 429:
        report.warnings.append(f"El servidor respondió HTTP {status_code}.")
    if report.authentication_detected:
        report.warnings.append("Se detectó autenticación; usa solo credenciales y permisos legítimos.")
    if captcha:
        report.warnings.append("Se detectó un CAPTCHA o challenge; el scraper no intentará resolverlo.")
    if dynamic:
        report.warnings.append("Las señales de JavaScript son heurísticas; no se inspeccionó el tráfico del navegador.")
    return report
