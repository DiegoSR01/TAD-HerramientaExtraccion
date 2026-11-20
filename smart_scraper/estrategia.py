"""Clasificación del escenario detectado y recomendación de estrategia.

Rol en la arquitectura: traduce el ``InspectionReport`` (señales heurísticas
del inspector) a una etiqueta legible y a la estrategia de adquisición
recomendada (requests, selenium, playwright, api o detener). Lo usan la
orquestación (``app``) y la interfaz gráfica para el paso "Presentación de
resultados" del flujo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .inspector import InspectionReport

STRATEGY_REQUESTS = "requests"
STRATEGY_SELENIUM = "selenium"
STRATEGY_PLAYWRIGHT = "playwright"
STRATEGY_API = "api"
STRATEGY_STOP = "detener"


@dataclass
class Scenario:
    """Escenario detectado y estrategia recomendada.

    Atributos:
        label: etiqueta legible del escenario principal.
        strategy: requests, selenium, playwright, api o detener.
        reason: explicación breve de la recomendación.
        signals: etiquetas de todas las señales detectadas (no solo la principal).
        blocked: ``True`` si es una incidencia que obliga a detener el acceso.
    """
    label: str
    strategy: str
    reason: str
    signals: list[str] = field(default_factory=list)
    blocked: bool = False

    def summary(self) -> str:
        """Texto de una línea: escenario y estrategia."""
        return f"Escenario: {self.label} | Estrategia recomendada: {self.strategy}"

    def to_dict(self) -> dict:
        """Devuelve el escenario como diccionario serializable."""
        return asdict(self)


def classify_scenario(report: InspectionReport) -> Scenario:
    """Clasifica el escenario a partir del diagnóstico de la inspección.

    Prioridad: CAPTCHA/bloqueo, autenticación, API JSON, scroll infinito,
    carga bajo demanda (botón), JavaScript/SPA, paginación, tablas y HTML
    estático. Las señales secundarias se listan en ``signals``.

    Args:
        report: informe de diagnóstico de la inspección.

    Returns:
        ``Scenario`` con etiqueta, estrategia, motivo y señales.
    """
    signals: list[str] = []
    is_json = "json" in report.content_type.lower()
    dynamic = report.rendering != "HTML estático"
    if is_json:
        signals.append("API JSON")
    if report.pagination_detected:
        signals.append("Paginación")
    if report.infinite_scroll_suspected:
        signals.append("Scroll infinito")
    if report.load_more_detected:
        signals.append("Carga bajo demanda (botón)")
    if report.tables_detected:
        signals.append("Tablas")
    if dynamic and not is_json:
        signals.append("JavaScript/SPA")
    if report.api_hints:
        signals.append("Endpoints API candidatos")

    if report.captcha_detected:
        return Scenario(
            "CAPTCHA/bloqueo → incidencia", STRATEGY_STOP,
            "Se detectó un CAPTCHA o challenge; no se intenta resolver ni evadir.",
            signals + ["CAPTCHA"], blocked=True,
        )
    if report.authentication_detected:
        return Scenario(
            "Requiere autenticación", STRATEGY_STOP,
            "El sitio exige credenciales; continuar solo con permisos legítimos.",
            signals + ["Autenticación"], blocked=report.blocked,
        )
    if report.blocked:
        return Scenario(
            "CAPTCHA/bloqueo → incidencia", STRATEGY_STOP,
            f"El servidor restringió el acceso (HTTP {report.status_code}).",
            signals + [f"HTTP {report.status_code}"], blocked=True,
        )
    if is_json:
        return Scenario("API JSON", STRATEGY_API, "La respuesta es JSON; usa el método API (autorizado).", signals)
    if report.infinite_scroll_suspected:
        return Scenario(
            "Scroll infinito", STRATEGY_SELENIUM,
            "El contenido se carga al desplazarse; requiere un navegador real con scrolls acotados.",
            signals,
        )
    if report.load_more_detected:
        return Scenario(
            "Carga bajo demanda (botón)", STRATEGY_SELENIUM,
            "Hay un botón 'cargar más'; requiere un navegador real con clics acotados.",
            signals,
        )
    if dynamic:
        hint = " Existen endpoints API candidatos que podrían usarse si están autorizados." if report.api_hints else ""
        return Scenario(
            "JavaScript/SPA", STRATEGY_SELENIUM,
            "El contenido parece renderizarse en el cliente; usa un navegador real (selenium o playwright)." + hint,
            signals,
        )
    if report.pagination_detected:
        return Scenario(
            "Paginación", STRATEGY_REQUESTS,
            "HTML con enlace a la siguiente página; usa requests con selector de siguiente y límite de páginas.",
            signals,
        )
    if report.tables_detected:
        return Scenario("Tablas", STRATEGY_REQUESTS, "HTML con tablas; requests basta, sin selector de registros.", signals)
    return Scenario("HTML estático", STRATEGY_REQUESTS, "HTML estático; requests es suficiente.", signals)
