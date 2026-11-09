"""Trazabilidad y reportes legibles de cada ejecución."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def configure_logging(output_directory: Path) -> logging.Logger:
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
        return asdict(self)


def write_report(report: RunReport, output_directory: Path) -> Path:
    import json

    output_directory.mkdir(parents=True, exist_ok=True)
    path = output_directory / f"report-{report.execution_id}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
