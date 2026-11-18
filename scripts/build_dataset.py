"""Construye el dataset books.toscrape.com usando la API de smart_scraper.

Flujo:
  1. Ejecuta `run_job` (smart_scraper.app) con ScrapeConfig, método `requests`
     y, opcionalmente, método `selenium` (headless). Máx. 5 páginas por corrida.
  2. Limpia los registros crudos de la corrida `requests` (principal).
  3. Guarda `datasets/books_toscrape.{sqlite,csv,xlsx}` (el xlsx incluye la hoja
     `lineage` generada por la herramienta) y deja report/log en
     `datasets/run_output/<método>/`.

Uso (desde la raíz del repositorio):
    python scripts/build_dataset.py              # requests + selenium
    python scripts/build_dataset.py --no-selenium

Solo contacta https://books.toscrape.com/ (sandbox público de práctica).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smart_scraper.app import RunFailure, run_job  # noqa: E402
from smart_scraper.config import AcquisitionMethod, ScrapeConfig, parse_field_rules  # noqa: E402

URL = "https://books.toscrape.com/"
DATASETS = ROOT / "datasets"
RUN_OUTPUT = DATASETS / "run_output"

FIELDS = """
titulo*=h3 a::title
precio*=p.price_color
disponibilidad=p.instock.availability
rating=p.star-rating::class
url*=h3 a::href
"""

RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def build_config(method: AcquisitionMethod) -> ScrapeConfig:
    return ScrapeConfig(
        url=URL,
        method=method,
        item_selector="article.product_pod",
        fields=parse_field_rules(FIELDS),
        pagination_selector="li.next a",
        max_pages=5,
        max_records=100,
        delay_seconds=1.5,
        timeout_seconds=20,
        headless=True,
    )


def run(method: AcquisitionMethod):
    """Ejecuta una corrida de la herramienta y devuelve (outcome | None, error | None)."""
    out = RUN_OUTPUT / method.value
    try:
        return run_job(build_config(method), out, "excel"), None
    except RunFailure as exc:
        print(f"[{method.value}] FALLÓ: {exc}")
        return exc.outcome, str(exc)


def parse_rating(value) -> int | None:
    match = re.search(r"One|Two|Three|Four|Five", str(value))
    return RATINGS[match.group(0)] if match else None


def parse_price(value) -> float | None:
    cleaned = re.sub(r"[^0-9.]", "", str(value))  # quita £, Â y otros caracteres raros
    return float(cleaned) if cleaned else None


def absolute_url(href: str) -> str:
    # La paginación cambia la URL base: la página 1 usa "catalogue/x/index.html"
    # y las siguientes "x/index.html" (relativas a /catalogue/).
    base = URL if href.startswith("catalogue/") else URL + "catalogue/"
    return urljoin(base, href)


def clean(raw: pd.DataFrame, method: str) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "titulo": raw["titulo"].astype(str).str.strip(),
            "precio_gbp": raw["precio"].map(parse_price).astype("float64"),
            "en_stock": raw["disponibilidad"].astype(str).str.contains("in stock", case=False),
            "rating": raw["rating"].map(parse_rating).astype("Int64"),
            "url": raw["url"].astype(str).map(absolute_url),
        }
    )
    df = df.dropna(subset=["titulo", "precio_gbp", "url"]).drop_duplicates(subset="url")
    df = df.reset_index(drop=True)
    df.insert(0, "id", range(1, len(df) + 1))
    df["fecha_extraccion"] = "2026-11-09"
    df["metodo"] = method
    df["fuente"] = URL
    return df


def save(df: pd.DataFrame, lineage: pd.DataFrame | None) -> None:
    DATASETS.mkdir(exist_ok=True)
    df.to_csv(DATASETS / "books_toscrape.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(DATASETS / "books_toscrape.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="books", index=False)
        if lineage is not None:
            lineage.to_excel(writer, sheet_name="lineage", index=False)
    db = DATASETS / "books_toscrape.sqlite"
    db.unlink(missing_ok=True)
    with sqlite3.connect(db) as con:
        con.execute(
            """CREATE TABLE books (
                id INTEGER PRIMARY KEY, titulo TEXT NOT NULL, precio_gbp REAL NOT NULL,
                en_stock INTEGER NOT NULL CHECK (en_stock IN (0, 1)),
                rating INTEGER CHECK (rating BETWEEN 1 AND 5),
                url TEXT NOT NULL UNIQUE, fecha_extraccion TEXT, metodo TEXT, fuente TEXT)"""
        )
        out = df.copy()
        out["en_stock"] = out["en_stock"].astype(int)
        out["rating"] = out["rating"].astype(object).where(out["rating"].notna(), None)
        out.to_sql("books", con, if_exists="append", index=False)
        if lineage is not None:
            lin = lineage.copy()
            lin["transformations"] = lin["transformations"].astype(str)
            lin.to_sql("lineage", con, if_exists="replace", index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-selenium", action="store_true", help="omite la corrida Selenium")
    args = parser.parse_args()

    outcome, error = run(AcquisitionMethod.REQUESTS)
    if error:
        return 1
    print(f"[requests] registros guardados: {outcome.report.records_saved}, "
          f"páginas: {outcome.report.pages_visited}")

    if not args.no_selenium:
        sel, sel_error = run(AcquisitionMethod.SELENIUM)
        if sel_error:
            print("[selenium] no disponible en este entorno; se continúa con requests.")
        else:
            print(f"[selenium] registros guardados: {sel.report.records_saved}")

    xlsx = next((RUN_OUTPUT / "requests").glob("records-*.xlsx"))
    raw = pd.read_excel(xlsx, sheet_name="records")
    lineage = pd.read_excel(xlsx, sheet_name="lineage")
    df = clean(raw, "requests")
    save(df, lineage)
    print(f"Dataset final: {len(df)} filas -> {DATASETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
