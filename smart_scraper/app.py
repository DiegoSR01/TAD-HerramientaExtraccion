"""Orquestación del flujo completo de una ejecución de scraping.

Rol en la arquitectura: capa coordinadora que une los siete módulos. Ejecuta
en orden inspección (``inspector``), adquisición (``extractor``), transformación
(``transform``), almacenamiento (``storage``) y monitoreo (``monitoring``),
y registra siempre un informe, incluso cuando la ejecución falla o es bloqueada
por una restricción de acceso (CAPTCHA, 401, 403, 429).

El flujo se informa en nueve pasos mediante un callback opcional ``progress``
(ver ``STEP_TITLES``), pensado para mostrar el avance en la interfaz gráfica.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import AcquisitionMethod, ScrapeConfig, format_field_rules, save_profile
from .estrategia import classify_scenario
from .extractor import AccessRestrictionError, captcha_atendible, scrape
from .inspector import InspectedPage, InspectionError, inspect_url
from .intervencion import CanalIntervencion, IntervencionHumana
from .monitoring import RunReport, configure_logging, write_report
from .selection import parse_json_body
from .storage import compare_and_store_snapshot, json_structure_signature, save_results
from .transform import transform_records

# Callback de progreso: progress(paso, total, titulo, detalle, estado)
# con estado en {"running", "done", "error", "blocked"}.
ProgressCallback = Callable[[int, int, str, str, str], None]

STEP_TITLES = [
    "Ingreso de URL y validación",
    "Diagnóstico automatizado",
    "Presentación de resultados",
    "Selección de datos",
    "Configuración de extracción",
    "Ejecución del motor",
    "Limpieza y validación",
    "Almacenamiento",
    "Reporte final",
]
TOTAL_STEPS = len(STEP_TITLES)


def _emit(progress: ProgressCallback | None, step: int, detail: str, status: str) -> None:
    """Notifica un evento de progreso; un fallo del callback nunca rompe la ejecución.

    Args:
        progress: callback opcional (``None`` no hace nada).
        step: número de paso (1 a 9).
        detail: texto descriptivo del evento.
        status: "running", "done", "error" o "blocked".
    """
    if progress is None:
        return
    try:
        progress(step, TOTAL_STEPS, STEP_TITLES[step - 1], detail, status)
    except Exception:  # la interfaz no debe interrumpir el scraping
        pass


@dataclass
class RunOutcome:
    """Resultado de una ejecución terminada.

    Atributos:
        report: informe de ejecución (estado, conteos, advertencias, rutas).
        diagnostic: diagnóstico de la inspección en forma de diccionario.
        report_path: ruta del informe JSON escrito en disco.
    """
    report: RunReport
    diagnostic: dict
    report_path: Path


class RunFailure(RuntimeError):
    """Error de ejecución que conserva el resultado parcial.

    Se lanza cuando ``run_job`` no pudo completarse; el atributo ``outcome``
    permite a la interfaz mostrar el informe con el error registrado.
    """
    def __init__(self, message: str, outcome: RunOutcome):
        """Crea el error.

        Args:
            message: descripción del fallo.
            outcome: resultado (con informe fallido) asociado a la ejecución.
        """
        super().__init__(message)
        self.outcome = outcome


def _announce_inspection(
    page: InspectedPage, progress: ProgressCallback | None, reused: bool = False,
    atendible: bool = False,
) -> None:
    """Emite los pasos 2 y 3 (diagnóstico y escenario detectado) de una inspección.

    Si el sitio restringe el acceso, el paso 3 se emite con estado "blocked",
    salvo que el bloqueo sea un CAPTCHA que se atenderá con intervención humana.

    Args:
        page: página ya inspeccionada.
        progress: callback de progreso opcional.
        reused: ``True`` si la inspección se reutilizó sin nueva solicitud.
        atendible: ``True`` si el CAPTCHA se resolverá a mano en el navegador.
    """
    report = page.report
    origin = "inspección previa reutilizada" if reused else "solicitud GET acotada"
    _emit(progress, 2, f"HTTP {report.status_code} ({origin}); {report.rendering}", "done")
    scenario = classify_scenario(report)
    detail = f"{scenario.summary()}\n{scenario.reason}"
    if report.blocked and atendible:
        _emit(
            progress, 3,
            f"{detail}\nCAPTCHA detectado: se pausará para que lo resuelvas en el navegador.",
            "done",
        )
    elif report.blocked:
        reasons = "; ".join(report.warnings) or "El servidor restringió el acceso."
        _emit(progress, 3, f"{detail}\nIncidencia: {reasons}", "blocked")
    else:
        _emit(progress, 3, detail, "done")


def diagnose_config(config: ScrapeConfig, progress: ProgressCallback | None = None) -> InspectedPage:
    """Valida la configuración e inspecciona la URL con una sola solicitud GET.

    Si se entrega ``progress`` emite los pasos 1 a 3 del flujo.

    Args:
        config: configuración de scraping.
        progress: callback de progreso opcional.

    Returns:
        Página inspeccionada con su informe de diagnóstico.

    Raises:
        ValueError: si la configuración no es válida.
        InspectionError: si la solicitud falla o la respuesta excede el límite.
    """
    _emit(progress, 1, f"Validando configuración de {config.url}", "running")
    try:
        config.validate()
    except Exception as exc:
        _emit(progress, 1, str(exc), "error")
        raise
    _emit(progress, 1, f"URL válida: {config.url}", "done")
    _emit(progress, 2, "Inspeccionando la URL (una sola solicitud GET)...", "running")
    try:
        page = inspect_url(config.url, config.timeout_seconds, config.headers)
    except Exception as exc:
        _emit(progress, 2, str(exc), "error")
        raise
    _announce_inspection(page, progress)
    return page


def run_job(
    config: ScrapeConfig,
    output_directory: Path,
    format_name: str = "csv",
    inspected_page: InspectedPage | None = None,
    progress: ProgressCallback | None = None,
    canal_captcha: CanalIntervencion | None = None,
) -> RunOutcome:
    """Ejecuta una tarea acotada; registra incluso los errores y restricciones.

    Flujo: validar, inspeccionar (o reutilizar ``inspected_page``), detenerse si
    el sitio restringe el acceso (401/403/429/CAPTCHA), adquirir, transformar,
    guardar resultados y perfil, comparar con la ejecución anterior y escribir el
    informe JSON. Cualquier excepción se registra en el informe antes de relanzarse
    como ``RunFailure``.

    Args:
        config: configuración de scraping (se valida al inicio).
        output_directory: carpeta de salida; se crea si no existe.
        format_name: formato de almacenamiento (csv, excel, json, sqlite,
            postgresql o mongodb).
        inspected_page: inspección previa reutilizable para evitar otra solicitud.
        progress: callback opcional ``progress(paso, total, titulo, detalle, estado)``
            que recibe los 9 pasos del flujo (estado: running, done, error o
            blocked). Sus excepciones se ignoran.
        canal_captcha: canal hacia la interfaz para resolver CAPTCHA a mano.
            Solo se usa con Selenium/Playwright; sin canal (o con Requests/API)
            un CAPTCHA detiene la ejecución como antes.

    Returns:
        ``RunOutcome`` con el informe, el diagnóstico y la ruta del informe. Si
        el usuario canceló ante un CAPTCHA, el estado es "cancelled" y se guardó
        lo extraído hasta ese momento.

    Raises:
        ValueError: si la configuración inicial no es válida.
        RunFailure: si la ejecución falló o fue bloqueada; contiene el informe.
    """
    _emit(progress, 1, f"Validando configuración de {config.url}", "running")
    try:
        config.validate()
    except Exception as exc:
        _emit(progress, 1, str(exc), "error")
        raise
    _emit(progress, 1, f"URL válida: {config.url}", "done")
    output_directory.mkdir(parents=True, exist_ok=True)
    logger = configure_logging(output_directory)
    report = RunReport(source_url=config.url, method=config.method.value)
    diagnostic: dict = {}
    intervencion = None
    if canal_captcha is not None:
        intervencion = IntervencionHumana(
            canal_captcha, config.captcha_timeout_seconds, logger,
            notificar=lambda texto, estado: _emit(progress, 6, texto, estado),
        )
    step = 2  # paso en curso, para informar en qué etapa ocurrió un error
    incident_reported = False
    try:
        if inspected_page is not None:
            page = inspected_page
        else:
            _emit(progress, 2, "Inspeccionando la URL (una sola solicitud GET)...", "running")
            page = inspect_url(config.url, config.timeout_seconds, config.headers)
        atendible = captcha_atendible(page.report, config.method, intervencion is not None)
        _announce_inspection(page, progress, reused=inspected_page is not None, atendible=atendible)
        step = 3
        diagnostic = page.report.to_dict()
        report.diagnostic = diagnostic
        report.warnings.extend(page.report.warnings)
        if page.report.blocked and not atendible:
            incident_reported = True  # ya se emitió "blocked" en el paso 3
            raise AccessRestrictionError(
                "; ".join(page.report.warnings) or "El servidor restringió el acceso."
            )
        step = 4
        automatico = config.method != AcquisitionMethod.API and not config.fields
        if automatico:
            _emit(
                progress, 4,
                "Selección automática: se detectarán registros, campos y paginación "
                "al cargar la primera página.",
                "done",
            )
        else:
            names = ", ".join(rule.name for rule in config.fields)
            where = config.json_records_path or config.item_selector or "página completa"
            _emit(progress, 4, f"Registros: {where}\nCampos: {names}", "done")
        step = 5
        _emit(
            progress, 5,
            f"Método {config.method.value}; máx. {config.max_records} registros, "
            f"{config.max_pages} página(s), pausa {config.delay_seconds}s",
            "done",
        )
        step = 6
        _emit(progress, 6, "Ejecutando el motor de extracción...", "running")

        def on_page(number: int, url: str, total: int) -> None:
            _emit(progress, 6, f"Página {number} visitada: {url}\n{total} registros acumulados", "running")

        def on_detect(estructura) -> None:
            if estructura is None:
                texto = (
                    "Selección automática: no se encontró un grupo repetido; "
                    "se usarán tablas o encabezados."
                )
            else:
                texto = f"{estructura.resumen()}\n{format_field_rules(estructura.fields)}"
            logger.info(texto.replace("\n", " | "))
            _emit(progress, 6, texto, "running")

        acquisition = scrape(
            config, page, on_page=on_page, intervencion=intervencion, on_detect=on_detect,
        )
        if acquisition.estructura is not None:
            config = acquisition.estructura.aplicar(config)  # perfil y linaje con lo detectado
            report.auto_selection = acquisition.estructura.to_dict()
            report.warnings.append(
                "Selectores detectados automáticamente; quedan en el perfil guardado para revisarlos."
            )
        report.skipped_urls = list(acquisition.skipped_urls)
        if acquisition.skipped_urls:
            report.warnings.append(
                f"{len(acquisition.skipped_urls)} página(s) omitida(s) por CAPTCHA: "
                + ", ".join(acquisition.skipped_urls)
            )
        if acquisition.cancelled:
            report.warnings.append(
                "Extracción cancelada por el usuario ante un CAPTCHA; se guardó lo extraído hasta ese momento."
            )
            _emit(
                progress, 6,
                f"Cancelada por el usuario: {acquisition.pages_visited} página(s), "
                f"{len(acquisition.records)} registros crudos (se guardarán)",
                "blocked",
            )
        else:
            _emit(
                progress, 6,
                f"{acquisition.pages_visited} página(s) visitada(s); {len(acquisition.records)} registros crudos",
                "done",
            )
        step = 7
        _emit(progress, 7, "Limpiando, normalizando y validando registros...", "running")
        records, lineage, report.execution_id = transform_records(
            acquisition.records,
            config.fields,
            config.url,
            config.method.value,
            report.execution_id,
        )
        report.records_found = len(acquisition.records)
        report.records_saved = len(records)
        if not records:
            report.warnings.append(
                "No se seleccionaron registros; verifica los selectores y el contenido de la respuesta."
            )
        report.invalid_fields = sum(
            item["validation_status"] != "valid" for item in lineage
        )
        if report.invalid_fields:
            report.warnings.append(
                f"Se detectaron {report.invalid_fields} valores ausentes en campos requeridos."
            )
        report.pages_visited = acquisition.pages_visited
        _emit(
            progress, 7,
            f"{report.records_saved} registros válidos de {report.records_found}; "
            f"{report.invalid_fields} valores requeridos ausentes",
            "done",
        )
        step = 8
        _emit(progress, 8, f"Guardando resultados en formato {format_name}...", "running")
        history_db = (
            output_directory / "scraper.sqlite3"
            if format_name == "sqlite"
            else output_directory / ".scraper_history.sqlite3"
        )
        report.output_paths.extend(
            str(path)
            for path in save_results(
                records,
                lineage,
                output_directory,
                format_name,
                config.url,
                config.method.value,
                report.execution_id,
            )
        )
        saved_profile = save_profile(config, output_directory / "profiles")
        report.output_paths.append(str(saved_profile))
        selectors = {
            rule.name: rule.selector + (f"::{rule.attribute}" if rule.attribute else "")
            for rule in config.fields
        }
        selectors["_item_selector"] = config.json_records_path or config.item_selector
        structure = None
        if config.method.value == "api":
            try:
                structure = json_structure_signature(parse_json_body(page.body, page.encoding))
            except (ValueError, UnicodeDecodeError):
                structure = None
        if structure is None:
            structure = json_structure_signature(records)
        report.changes = compare_and_store_snapshot(
            history_db, report.execution_id, records, page.report.api_hints, config.url,
            selectors=selectors, json_structure=structure,
        )
        if report.changes.get("baseline_created"):
            change_text = "línea base de cambios creada para este sitio"
        elif report.changes.get("changes_detected"):
            change_text = "cambios detectados respecto a la ejecución anterior"
        else:
            change_text = "sin cambios respecto a la ejecución anterior"
        _emit(
            progress, 8,
            f"{len(report.output_paths)} archivo(s) guardados (incluye perfil); {change_text}",
            "done",
        )
        report.status = "cancelled" if acquisition.cancelled else "completed"
        logger.info(
            "Ejecución %s %s: %s registros, método %s",
            report.execution_id,
            "cancelada por el usuario" if acquisition.cancelled else "completada",
            report.records_saved,
            report.method,
        )
    except Exception as exc:
        report.status = "failed"
        report.error = str(exc)
        logger.error("Ejecución %s fallida: %s", report.execution_id, exc)
        if not incident_reported:
            blocked = isinstance(exc, AccessRestrictionError)
            _emit(progress, step, str(exc), "blocked" if blocked else "error")
    if intervencion is not None:
        report.captcha_events = list(intervencion.eventos)
    report_path = output_directory / f"report-{report.execution_id}.json"
    report.output_paths.append(str(report_path))
    _emit(progress, 9, "Generando informe final...", "running")
    write_report(report, output_directory)
    _emit(
        progress, 9,
        f"Estado: {report.status}; informe: {report_path}",
        "done" if report.status in {"completed", "cancelled"} else "error",
    )
    outcome = RunOutcome(report, diagnostic, report_path)
    if report.status not in {"completed", "cancelled"}:
        raise RunFailure(report.error or "La ejecución no pudo completarse.", outcome)
    return outcome


def load_profile_for_url(directory: Path, url: str) -> ScrapeConfig | None:
    """Carga el perfil guardado para el host de ``url``.

    Se importa ``load_profile`` de forma diferida. El perfil nunca incluye
    encabezados ni autorización API, que deben ingresarse de nuevo.

    Args:
        directory: carpeta de perfiles.
        url: URL cuyo host identifica el perfil.

    Returns:
        Configuración reconstruida, o ``None`` si no hay perfil.
    """
    from .config import load_profile

    return load_profile(directory, url)
