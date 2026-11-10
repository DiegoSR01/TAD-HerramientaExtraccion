"""Normalización, validación, deduplicación y linaje de datos extraídos.

Rol en la arquitectura: módulo de transformación. Limpia los registros crudos
que entrega ``extractor``, descarta vacíos y duplicados, valida campos
requeridos y registra el linaje de cada valor para su almacenamiento.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pandas as pd

from .config import FieldRule


def transform_records(
    records: list[dict[str, Any]],
    rules: list[FieldRule],
    source_url: str,
    method: str,
    execution_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Limpia, valida y deduplica registros, generando su linaje.

    Recorta y colapsa espacios, convierte cadenas vacías en ``None``, descarta
    registros totalmente vacíos o duplicados y marca ``missing_required`` los
    campos requeridos ausentes.

    Args:
        records: registros crudos.
        rules: reglas de campos (indican cuáles son requeridos).
        source_url: URL de origen.
        method: método de adquisición.
        execution_id: identificador existente; si es ``None`` se genera uno.

    Returns:
        Tupla ``(registros_limpios, linaje, execution_id)``.
    """
    execution_id = execution_id or str(uuid4())
    acquired_at = datetime.now(timezone.utc).isoformat()
    required = {rule.name for rule in rules if rule.required}
    cleaned: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    for index, record in enumerate(records):
        normalized: dict[str, Any] = {}
        for name, value in record.items():
            if isinstance(value, str):
                value = re.sub(r"\s+", " ", value).strip()
                if not value:
                    value = None
            normalized[str(name)] = value
        if not any(value is not None for value in normalized.values()):
            continue
        fingerprint = tuple(sorted((key, repr(value)) for key, value in normalized.items()))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        cleaned.append(normalized)
        for name, value in normalized.items():
            lineage.append(
                {
                    "execution_id": execution_id,
                    "record_index": len(cleaned) - 1,
                    "source_url": source_url,
                    "acquired_at": acquired_at,
                    "method": method,
                    "field": name,
                    "value": value,
                    "validation_status": (
                        "missing_required" if name in required and value is None else "valid"
                    ),
                    "transformations": ["trim_whitespace", "collapse_whitespace", "deduplicate_record"],
                }
            )
        for missing_name in required.difference(normalized):
            lineage.append(
                {
                    "execution_id": execution_id,
                    "record_index": len(cleaned) - 1,
                    "source_url": source_url,
                    "acquired_at": acquired_at,
                    "method": method,
                    "field": missing_name,
                    "value": None,
                    "validation_status": "missing_required",
                    "transformations": ["required_field_validation"],
                }
            )
    if cleaned:
        frame = pd.DataFrame(cleaned)
        cleaned = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
    return cleaned, lineage, execution_id
