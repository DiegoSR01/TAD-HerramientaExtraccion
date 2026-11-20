"""Persistencia de resultados y detección de cambios entre ejecuciones.

Rol en la arquitectura: módulo de almacenamiento. Guarda registros y su
linaje en CSV, Excel, JSON o SQLite y, de forma opcional, en PostgreSQL o
MongoDB (credenciales por variables de entorno, nunca en la configuración).
También compara cada ejecución con la anterior del mismo host.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd


def save_results(
    records: list[dict[str, Any]],
    lineage: list[dict[str, Any]],
    destination: Path,
    format_name: str,
    source_url: str,
    method: str,
    execution_id: str,
) -> list[Path]:
    """Guarda registros y linaje en el formato indicado.

    Args:
        records: registros limpios.
        lineage: filas de linaje (origen, validación, transformaciones).
        destination: carpeta de salida.
        format_name: csv, excel, json, sqlite, postgresql o mongodb.
        source_url: URL de origen.
        method: método de adquisición usado.
        execution_id: identificador de la ejecución.

    Returns:
        Rutas de los archivos creados (vacío para bases de datos externas).

    Raises:
        ValueError: si el formato no se reconoce.
        RuntimeError: si faltan variables de entorno o dependencias opcionales.
    """
    destination.mkdir(parents=True, exist_ok=True)
    if format_name == "sqlite":
        path = destination / "scraper.sqlite3"
        _save_sqlite(records, lineage, path, source_url, method, execution_id)
        return [path]
    if format_name in {"csv", "excel"}:
        frame = pd.DataFrame(records)
        lineage_frame = _lineage_frame(lineage)
        if format_name == "csv":
            path = destination / f"records-{execution_id}.csv"
            frame.to_csv(path, index=False, encoding="utf-8-sig")
            lineage_path = destination / f"lineage-{execution_id}.csv"
            lineage_frame.to_csv(lineage_path, index=False, encoding="utf-8-sig")
            return [path, lineage_path]
        path = destination / f"records-{execution_id}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            frame.to_excel(writer, sheet_name="records", index=False)
            lineage_frame.to_excel(writer, sheet_name="lineage", index=False)
        return [path]
    if format_name == "json":
        path = destination / f"records-{execution_id}.json"
        lineage_by_record: dict[int, list[dict]] = {}
        for item in lineage:
            lineage_by_record.setdefault(item["record_index"], []).append(
                {key: value for key, value in item.items() if key not in {"record_index", "value"}}
                | {"value": item.get("value")}
            )
        rows = [
            {"data": record, "_lineage": lineage_by_record.get(index, [])}
            for index, record in enumerate(records)
        ]
        path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return [path]
    if format_name == "postgresql":
        _save_postgres(records, lineage, source_url, method, execution_id)
        return []
    if format_name == "mongodb":
        _save_mongodb(records, lineage, source_url, method, execution_id)
        return []
    raise ValueError(f"Formato de almacenamiento no reconocido: {format_name}")


def _save_sqlite(
    records: list[dict],
    lineage: list[dict],
    path: Path,
    source_url: str,
    method: str,
    execution_id: str,
) -> None:
    """Guarda registros y linaje en SQLite (tablas ``records``, ``lineage`` y ``run_snapshots``)."""
    acquired_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS records (
                execution_id TEXT NOT NULL, record_index INTEGER NOT NULL,
                source_url TEXT NOT NULL, acquired_at TEXT NOT NULL, method TEXT NOT NULL,
                data_json TEXT NOT NULL, PRIMARY KEY (execution_id, record_index))"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS lineage (
                execution_id TEXT NOT NULL, record_index INTEGER NOT NULL,
                source_url TEXT NOT NULL, acquired_at TEXT NOT NULL, method TEXT NOT NULL,
                field TEXT NOT NULL, value_json TEXT, validation_status TEXT NOT NULL,
                transformations_json TEXT NOT NULL)"""
        )
        _ensure_snapshot_table(connection)
        connection.executemany(
            "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?, ?, ?)",
            [
                (execution_id, index, source_url, acquired_at, method, json.dumps(record, default=str))
                for index, record in enumerate(records)
            ],
        )
        connection.executemany(
            "INSERT INTO lineage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    item["execution_id"],
                    item["record_index"],
                    item["source_url"],
                    item["acquired_at"],
                    item["method"],
                    item["field"],
                    json.dumps(item["value"], ensure_ascii=False, default=str),
                    item["validation_status"],
                    json.dumps(item["transformations"], ensure_ascii=False),
                )
                for item in lineage
            ],
        )


_SNAPSHOT_TABLE = """CREATE TABLE IF NOT EXISTS run_snapshots (
    host TEXT PRIMARY KEY, execution_id TEXT NOT NULL, field_names TEXT NOT NULL,
    endpoints TEXT NOT NULL, record_count INTEGER NOT NULL, captured_at TEXT NOT NULL,
    selectors TEXT, json_structure TEXT)"""


def _ensure_snapshot_table(connection: sqlite3.Connection) -> None:
    """Crea ``run_snapshots`` y migra tablas antiguas añadiendo columnas nuevas.

    Si la tabla existía sin ``selectors`` o ``json_structure`` se agregan con
    ``ALTER TABLE`` (valores NULL en las filas previas), sin perder datos.
    """
    connection.execute(_SNAPSHOT_TABLE)
    existing = {row[1] for row in connection.execute("PRAGMA table_info(run_snapshots)")}
    for column in ("selectors", "json_structure"):
        if column not in existing:
            connection.execute(f"ALTER TABLE run_snapshots ADD COLUMN {column} TEXT")


def json_structure_signature(value: Any, max_paths: int = 500) -> list[str]:
    """Calcula la firma estructural de un valor JSON como rutas de claves.

    Los diccionarios anidados usan rutas con puntos (``a.b``) y las listas se
    marcan con ``[]`` (``items[].id``). Si ``value`` es una lista de registros
    se analizan todos y se unen sus rutas.

    Args:
        value: documento JSON ya interpretado, o lista de registros.
        max_paths: tope de rutas para acotar el tamaño de la firma.

    Returns:
        Lista ordenada de rutas únicas.
    """
    paths: set[str] = set()

    def walk(node: Any, prefix: str) -> None:
        if len(paths) >= max_paths:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                paths.add(path)
                walk(child, path)
        elif isinstance(node, list):
            for child in node:
                walk(child, f"{prefix}[]")

    walk(value, "")
    return sorted(paths)


def compare_and_store_snapshot(
    database: Path,
    execution_id: str,
    records: list[dict],
    endpoints: list[str],
    source_url: str,
    *,
    selectors: dict[str, str] | None = None,
    json_structure: list[str] | None = None,
) -> dict:
    """Compara la ejecución actual con la anterior del mismo host y guarda la nueva.

    Sin ``selectors`` ni ``json_structure`` devuelve el conjunto original de
    cambios (compatibilidad). Si se pasa alguno, el resultado incluye además
    ``new_columns``, ``selector_changes``, ``json_structure_added/removed``,
    ``record_count_previous``, ``record_count_percent`` y ``changes_detected``.
    La tabla SQLite se migra automáticamente si es de una versión anterior.

    Args:
        database: archivo SQLite de historial.
        execution_id: identificador de la ejecución actual.
        records: registros guardados.
        endpoints: endpoints sugeridos por la inspección.
        source_url: URL de origen (su host identifica el historial).
        selectors: selectores CSS/rutas por campo (y ``_item_selector``).
        json_structure: firma de rutas JSON (ver ``json_structure_signature``).

    Returns:
        Diccionario de cambios o ``{"baseline_created": True}`` si no hay
        ejecución previa.
    """
    host = urlparse(source_url).netloc.lower()
    fields = sorted({str(name) for record in records for name in record})
    captured_at = datetime.now(timezone.utc).isoformat()
    extended = selectors is not None or json_structure is not None
    with sqlite3.connect(database) as connection:
        _ensure_snapshot_table(connection)
        previous = connection.execute(
            "SELECT field_names, endpoints, record_count, selectors, json_structure "
            "FROM run_snapshots WHERE host = ?",
            (host,),
        ).fetchone()
        current_endpoints = sorted(set(endpoints))
        changes: dict[str, Any] = {}
        if previous:
            old_fields, old_endpoints, old_count, old_selectors, old_structure = previous
            old_fields_set = set(json.loads(old_fields))
            old_endpoints_set = set(json.loads(old_endpoints))
            added = sorted(set(fields) - old_fields_set)
            changes = {
                "added_fields": added,
                "missing_fields": sorted(old_fields_set - set(fields)),
                "new_endpoints": sorted(set(current_endpoints) - old_endpoints_set),
                "removed_endpoints": sorted(old_endpoints_set - set(current_endpoints)),
                "record_count_delta": len(records) - old_count,
            }
            if extended:
                changes["new_columns"] = added
                changes["record_count_previous"] = old_count
                changes["record_count_percent"] = (
                    round((len(records) - old_count) * 100 / old_count, 2) if old_count else None
                )
                changes["selector_changes"] = {}
                if selectors is not None and old_selectors:
                    before = json.loads(old_selectors)
                    for name in sorted(set(before) | set(selectors)):
                        if before.get(name) != selectors.get(name):
                            changes["selector_changes"][name] = {
                                "before": before.get(name), "after": selectors.get(name),
                            }
                changes["json_structure_added"] = []
                changes["json_structure_removed"] = []
                if json_structure is not None and old_structure:
                    before_paths = set(json.loads(old_structure))
                    changes["json_structure_added"] = sorted(set(json_structure) - before_paths)
                    changes["json_structure_removed"] = sorted(before_paths - set(json_structure))
                changes["changes_detected"] = any(
                    bool(changes[key]) for key in (
                        "added_fields", "missing_fields", "new_endpoints", "removed_endpoints",
                        "record_count_delta", "selector_changes",
                        "json_structure_added", "json_structure_removed",
                    )
                )
        else:
            changes = {"baseline_created": True}
        connection.execute(
            """INSERT OR REPLACE INTO run_snapshots
                (host, execution_id, field_names, endpoints, record_count, captured_at,
                 selectors, json_structure)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                host,
                execution_id,
                json.dumps(fields),
                json.dumps(current_endpoints),
                len(records),
                captured_at,
                json.dumps(selectors, ensure_ascii=False) if selectors is not None else None,
                json.dumps(sorted(json_structure)) if json_structure is not None else None,
            ),
        )
    return changes


def _lineage_frame(lineage: list[dict]) -> pd.DataFrame:
    """Convierte el linaje en DataFrame serializando las transformaciones a JSON."""
    frame = pd.DataFrame(lineage)
    if "transformations" in frame:
        frame["transformations"] = frame["transformations"].map(json.dumps)
    return frame


def _save_postgres(records: list[dict], lineage: list[dict], source_url: str, method: str, execution_id: str) -> None:
    """Guarda en PostgreSQL usando el DSN de ``SCRAPER_POSTGRES_DSN``.

    Raises:
        RuntimeError: si falta la variable de entorno o el extra ``psycopg``.
    """
    dsn = os.environ.get("SCRAPER_POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("Define SCRAPER_POSTGRES_DSN para guardar en PostgreSQL.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Instala el extra PostgreSQL: `pip install '.[postgres]'`.") from exc
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS scraper_records (
                execution_id text, record_index integer, source_url text, acquired_at timestamptz,
                method text, data jsonb, PRIMARY KEY (execution_id, record_index))"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS scraper_lineage (
                execution_id text, record_index integer, source_url text, acquired_at timestamptz,
                method text, field text, value jsonb, validation_status text, transformations jsonb)"""
        )
        acquired = datetime.now(timezone.utc)
        for index, record in enumerate(records):
            connection.execute(
                "INSERT INTO scraper_records VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (execution_id, index, source_url, acquired, method, json.dumps(record, default=str)),
            )
        for item in lineage:
            connection.execute(
                "INSERT INTO scraper_lineage VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    item["execution_id"], item["record_index"], item["source_url"],
                    item["acquired_at"], item["method"], item["field"],
                    json.dumps(item["value"], default=str), item["validation_status"],
                    json.dumps(item["transformations"]),
                ),
            )


def _save_mongodb(records: list[dict], lineage: list[dict], source_url: str, method: str, execution_id: str) -> None:
    """Guarda en MongoDB usando el URI de ``SCRAPER_MONGODB_URI``.

    Raises:
        RuntimeError: si falta la variable de entorno o el extra ``pymongo``.
    """
    uri = os.environ.get("SCRAPER_MONGODB_URI")
    if not uri:
        raise RuntimeError("Define SCRAPER_MONGODB_URI para guardar en MongoDB.")
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError("Instala el extra MongoDB: `pip install '.[mongodb]'`.") from exc
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        database = client["smart_scraper"]
        if records:
            database.records.insert_many(
                [
                    {
                        "execution_id": execution_id,
                        "record_index": index,
                        "source_url": source_url,
                        "acquired_at": datetime.now(timezone.utc),
                        "method": method,
                        "data": record,
                    }
                    for index, record in enumerate(records)
                ]
            )
        if lineage:
            database.lineage.insert_many(lineage)
