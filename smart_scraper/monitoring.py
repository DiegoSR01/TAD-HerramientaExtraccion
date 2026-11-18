"""Trazabilidad y reportes legibles de cada ejecución.

Rol en la arquitectura: módulo de monitoreo. Configura el registro en archivo
(``smart_scraper.log``) y define el informe JSON por ejecución con estado,
conteos, advertencias, errores y cambios detectados, incluyendo las
ejecuciones detenidas por CAPTCHA, 401, 403 o 429.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def configure_logging(output_directory: Path) -> logging.Logger:
    """Configura el logger ``smart_scraper`` con salida a archivo.

    No añade manejadores duplicados si ya existe uno.

    Args:
        output_directory: carpeta donde se crea ``smart_scraper.log``.

    Returns:
        Logger listo para usar.
    """
    output_directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("smart_scraper")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(output_directory / "smart_scraper.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


@dataclass
class RunReport:
    """Informe de una ejecución.

    Atributos:
        execution_id: identificador único (UUID).
        started_at: marca de tiempo UTC ISO 8601.
        status: "started", "completed" o "failed".
        records_found, records_saved, invalid_fields, pages_visited: conteos.
        diagnostic: resultado de la inspección.
        output_paths: archivos generados.
        changes: diferencias respecto a la ejecución anterior.
        warnings, error: mensajes para el usuario.
    """
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_url: str = ""
    method: str = ""
    status: str = "started"
    records_found: int = 0
    records_saved: int = 0
    invalid_fields: int = 0
    pages_visited: int = 0
    diagnostic: dict = field(default_factory=dict)
    output_paths: list[str] = field(default_factory=list)
    changes: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        """Devuelve el informe como diccionario serializable a JSON."""
        return asdict(self)


def write_report(report: RunReport, output_directory: Path) -> Path:
    """Escribe el informe como ``report-<execution_id>.json``.

    Args:
        report: informe a guardar.
        output_directory: carpeta de salida; se crea si no existe.

    Returns:
        Ruta del archivo escrito.
    """
    import json

    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / f"report-{report.execution_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
