"""Selección configurable de campos HTML/JSON y extracción de tablas.

Rol en la arquitectura: módulo de selección. Aplica selectores CSS (BeautifulSoup)
o rutas con puntos (JSON) para convertir contenido ya adquirido en registros.
No realiza solicitudes de red.
"""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from .config import FieldRule


def select_html(
    html: str, item_selector: str = "", fields: list[FieldRule] | None = None, limit: int = 250
) -> list[dict[str, Any]]:
    """Extrae registros de HTML mediante selectores CSS.

    Con reglas de campos: selecciona cada elemento repetido (``item_selector``) y
    aplica ``select_one`` por campo (texto o atributo). Sin reglas: intenta leer la
    primera tabla y, si no hay, devuelve título y encabezados h1/h2.

    Args:
        html: documento HTML.
        item_selector: selector CSS de los elementos repetidos; vacío usa el documento.
        fields: reglas de campos.
        limit: máximo de registros.

    Returns:
        Lista de registros; los campos no encontrados valen ``None``.
    """
    soup = BeautifulSoup(html, "html.parser")
    rules = fields or []
    if not rules:
        table = soup.find("table")
        if table:
            rows = [
                [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                for row in table.find_all("tr")
            ]
            rows = [row for row in rows if row]
            if rows:
                headers = rows[0]
                if table.find("th") is None:
                    headers = [f"column_{index + 1}" for index in range(len(rows[0]))]
                    data_rows = rows
                else:
                    data_rows = rows[1:]
                return [
                    {headers[index] if index < len(headers) else f"column_{index + 1}": value
                     for index, value in enumerate(row)}
                    for row in data_rows[:limit]
                ]
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        headings = [tag.get_text(" ", strip=True) for tag in soup.select("h1, h2")[:limit]]
        if title or headings:
            return [{"title": title, "heading": heading} for heading in headings] or [{"title": title}]
        return []

    items = soup.select(item_selector)[:limit] if item_selector else [soup]
    results: list[dict[str, Any]] = []
    for item in items:
        record: dict[str, Any] = {}
        for rule in rules:
            selected = item.select_one(rule.selector)
            value = None
            if selected is not None:
                value = selected.get(rule.attribute) if rule.attribute else selected.get_text(" ", strip=True)
            record[rule.name] = value
        results.append(record)
    return results


def _json_path(value: Any, path: str) -> Any:
    """Recorre un valor JSON siguiendo una ruta con puntos (``a.b.0.c``).

    Soporta diccionarios (por clave) y listas (por índice).

    Returns:
        El valor encontrado, o ``None`` si la ruta no existe.
    """
    current = value
    for part in path.split(".") if path else []:
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def select_json(
    payload: Any,
    fields: list[FieldRule],
    records_path: str = "",
    limit: int = 250,
) -> list[dict[str, Any]]:
    """Extrae registros de un documento JSON usando rutas con puntos.

    Args:
        payload: JSON ya decodificado.
        fields: reglas; ``selector`` es la ruta dentro de cada elemento.
        records_path: ruta a la lista de registros; vacío usa la raíz.
        limit: máximo de registros.

    Returns:
        Lista de registros con los campos pedidos.

    Raises:
        ValueError: si la ruta no apunta a una lista u objeto JSON.
    """
    items = _json_path(payload, records_path) if records_path else payload
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise ValueError("La ruta de registros de la API no apunta a una lista u objeto JSON.")
    results = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            item = {"value": item}
        results.append({rule.name: _json_path(item, rule.selector) for rule in fields})
    return results


def parse_json_body(body: bytes, encoding: str | None = None) -> Any:
    """Decodifica bytes JSON de forma estricta.

    Args:
        body: cuerpo de la respuesta.
        encoding: codificación; por defecto UTF-8.

    Raises:
        UnicodeDecodeError: si los bytes no son válidos en esa codificación.
        ValueError: si el contenido no es JSON válido.
    """
    return json.loads(body.decode(encoding or "utf-8", errors="strict"))
