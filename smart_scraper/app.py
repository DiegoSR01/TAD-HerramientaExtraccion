"""Coordinación de diagnóstico, adquisición, transformación y almacenamiento."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ScrapeConfig, save_profile
from .extractor import AccessRestrictionError, scrape
from .inspector import InspectedPage, InspectionError, inspect_url
from .monitoring import RunReport, configure_logging, write_report
from .transform import transform_records
from .storage import compare_and_store_snapshot, save_results


@dataclass
class RunOutcome:
    report: RunReport
    diagnostic: dict
    report_path: Path


class RunFailure(RuntimeError):
    def __init__(self, message: str, outcome: RunOutcome):
        super().__init__(message)
        self.outcome = outcome


def diagnose_config(config: ScrapeConfig) -> InspectedPage:
    config.validate()
    return inspect_url(config.url, config.timeout_seconds, config.headers)


def run_job(
    config: ScrapeConfig,
    output_directory: Path,
    format_name: str = "csv",
    inspected_page: InspectedPage | None = None,
) -> RunOutcome:
    """Ejecuta una tarea acotada; registra incluso los errores y restricciones."""
    config.validate()
    output_directory.mkdir(parents=True, exist_ok=True)
    logger = configure_logging(output_directory)
    report = RunReport(source_url=config.url, method=config.method.value)
    diagnostic: dict = {}
    try:
        page = inspected_page or diagnose_config(config)
        diagnostic = page.report.to_dict()
        report.diagnostic = diagnostic
        report.warnings.extend(page.report.warnings)
        if page.report.blocked:
            raise AccessRestrictionError(
                "; ".join(page.report.warnings) or "El servidor restringió el acceso."
            )
        acquisition = scrape(config, page)
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
        report.changes = compare_and_store_snapshot(
            history_db, report.execution_id, records, page.report.api_hints, config.url
        )
        report.status = "completed"
        logger.info(
            "Ejecución %s completada: %s registros, método %s",
            report.execution_id,
            report.records_saved,
            report.method,
        )
    except Exception as exc:
        report.status = "failed"
        report.error = str(exc)
        logger.error("Ejecución %s fallida: %s", report.execution_id, exc)
    report_path = output_directory / f"report-{report.execution_id}.json"
    report.output_paths.append(str(report_path))
    write_report(report, output_directory)
    outcome = RunOutcome(report, diagnostic, report_path)
    if report.status != "completed":
        raise RunFailure(report.error or "La ejecución no pudo completarse.", outcome)
    return outcome


def load_profile_for_url(directory: Path, url: str) -> ScrapeConfig | None:
    from .config import load_profile

    return load_profile(directory, url)
