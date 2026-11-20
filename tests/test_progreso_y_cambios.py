"""Pruebas del progreso del flujo, la clasificación de escenarios y la detección de cambios.

Usan el servidor local de ``conftest.py``; no se hacen solicitudes a sitios públicos.
"""

from __future__ import annotations

import sqlite3

import pytest

from smart_scraper.app import STEP_TITLES, RunFailure, diagnose_config, run_job
from smart_scraper.config import AcquisitionMethod, FieldRule, ScrapeConfig
from smart_scraper.estrategia import classify_scenario
from smart_scraper.inspector import inspect_url
from smart_scraper.storage import compare_and_store_snapshot, json_structure_signature


# ---------------------------------------------------------------- progreso
def test_progress_reports_nine_steps_in_order(site, tmp_path):
    events = []
    config = ScrapeConfig(
        url=f"{site}/static", item_selector="article", fields=[FieldRule("title", "h2")]
    )
    run_job(config, tmp_path, "csv", progress=lambda *event: events.append(event))
    assert all(event[1] == 9 and event[4] in {"running", "done", "error", "blocked"} for event in events)
    done_steps = [event[0] for event in events if event[4] == "done"]
    assert sorted(set(done_steps)) == list(range(1, 10))
    # Cada paso se completa en orden ascendente.
    first_done = [done_steps.index(step) for step in range(1, 10)]
    assert first_done == sorted(first_done)
    assert [event[2] for event in events if event[0] == 9][-1] == STEP_TITLES[8]
    assert not any(event[4] in {"error", "blocked"} for event in events)
    scenario_event = next(event for event in events if event[0] == 3)
    assert "HTML estático" in scenario_event[3] and "requests" in scenario_event[3]


def test_progress_reports_page_by_page_in_engine_step(site, tmp_path):
    events = []
    config = ScrapeConfig(
        url=f"{site}/pagination", item_selector="article", fields=[FieldRule("title", "h2")],
        pagination_selector="a.next", max_pages=2, delay_seconds=1,
    )
    run_job(config, tmp_path, "csv", progress=lambda *event: events.append(event))
    pages = [event for event in events if event[0] == 6 and "visitada:" in event[3]]
    assert len(pages) == 2 and "2 registros acumulados" in pages[-1][3]


def test_progress_emits_blocked_event_for_captcha(site, tmp_path):
    events = []
    with pytest.raises(RunFailure):
        run_job(
            ScrapeConfig(f"{site}/captcha"), tmp_path, progress=lambda *event: events.append(event)
        )
    blocked = [event for event in events if event[4] == "blocked"]
    assert len(blocked) == 1 and blocked[0][0] == 3
    assert "CAPTCHA" in blocked[0][3]
    assert not any(event[0] in range(4, 9) for event in events)


def test_diagnose_config_drives_steps_one_to_three_and_callback_errors_are_ignored(site):
    events = []
    diagnose_config(ScrapeConfig(f"{site}/static"), progress=lambda *event: events.append(event))
    assert [event[0] for event in events if event[4] == "done"] == [1, 2, 3]

    def broken(*_):
        raise RuntimeError("fallo de interfaz")

    assert diagnose_config(ScrapeConfig(f"{site}/static"), progress=broken).report.status_code == 200


# ---------------------------------------------------------------- escenarios
@pytest.mark.parametrize(
    ("path", "label", "strategy"),
    [
        ("/static", "HTML estático", "requests"),
        ("/dynamic", "Scroll infinito", "selenium"),
        ("/loadmore", "Carga bajo demanda (botón)", "selenium"),
        ("/api/products", "API JSON", "api"),
        ("/pagination", "Paginación", "requests"),
        ("/table", "Tablas", "requests"),
        ("/auth", "Requiere autenticación", "detener"),
        ("/denied", "CAPTCHA/bloqueo → incidencia", "detener"),
        ("/captcha", "CAPTCHA/bloqueo → incidencia", "detener"),
    ],
)
def test_scenario_classifier_labels_fixtures(site, path, label, strategy):
    scenario = classify_scenario(inspect_url(f"{site}{path}").report)
    assert (scenario.label, scenario.strategy) == (label, strategy)
    assert scenario.blocked == (strategy == "detener")


def test_scenario_javascript_spa_without_other_signals():
    from smart_scraper.inspector import diagnose

    report = diagnose("https://x.test/", 200, "text/html", b"<html><script src='/app.js'></script></html>")
    scenario = classify_scenario(report)
    assert (scenario.label, scenario.strategy) == ("JavaScript/SPA", "selenium")
    assert "JavaScript/SPA" in scenario.signals


# ------------------------------------------------------------------- cambios
def test_legacy_call_keeps_original_change_keys(tmp_path):
    database = tmp_path / "h.sqlite3"
    compare_and_store_snapshot(database, "1", [{"a": 1}], [], "https://s.test")
    changes = compare_and_store_snapshot(database, "2", [{"a": 1}], [], "https://s.test")
    assert set(changes) == {
        "added_fields", "missing_fields", "new_endpoints", "removed_endpoints", "record_count_delta",
    }


def test_snapshot_detects_selectors_json_structure_columns_and_volume(tmp_path):
    database = tmp_path / "h.sqlite3"
    first = [{"name": "A", "price": 1}, {"name": "B", "price": 2}]
    compare_and_store_snapshot(
        database, "1", first, ["/api/v1"], "https://s.test",
        selectors={"_item_selector": "article", "name": "h2", "price": ".price"},
        json_structure=json_structure_signature({"items": [{"name": "A", "price": 1}]}),
    )
    second = [{"name": "A", "stock": 3}]
    changes = compare_and_store_snapshot(
        database, "2", second, ["/api/v1"], "https://s.test",
        selectors={"_item_selector": "div.card", "name": "h2", "stock": ".stock"},
        json_structure=json_structure_signature({"items": [{"name": "A", "stock": 3}], "meta": {"n": 1}}),
    )
    assert changes["new_columns"] == ["stock"] == changes["added_fields"]
    assert changes["missing_fields"] == ["price"]
    assert changes["selector_changes"] == {
        "_item_selector": {"before": "article", "after": "div.card"},
        "price": {"before": ".price", "after": None},
        "stock": {"before": None, "after": ".stock"},
    }
    assert changes["json_structure_added"] == ["items[].stock", "meta", "meta.n"]
    assert changes["json_structure_removed"] == ["items[].price"]
    assert changes["record_count_delta"] == -1
    assert changes["record_count_previous"] == 2
    assert changes["record_count_percent"] == -50.0
    assert changes["changes_detected"] is True
    # Una tercera ejecución idéntica no reporta cambios.
    same = compare_and_store_snapshot(
        database, "3", second, ["/api/v1"], "https://s.test",
        selectors={"_item_selector": "div.card", "name": "h2", "stock": ".stock"},
        json_structure=json_structure_signature({"items": [{"name": "A", "stock": 3}], "meta": {"n": 1}}),
    )
    assert same["changes_detected"] is False and same["selector_changes"] == {}


def test_snapshot_table_is_migrated_from_old_schema(tmp_path):
    database = tmp_path / "old.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE run_snapshots (
                host TEXT PRIMARY KEY, execution_id TEXT NOT NULL, field_names TEXT NOT NULL,
                endpoints TEXT NOT NULL, record_count INTEGER NOT NULL, captured_at TEXT NOT NULL)"""
        )
        connection.execute(
            "INSERT INTO run_snapshots VALUES ('s.test', 'old', '[\"a\"]', '[]', 4, 'ayer')"
        )
    changes = compare_and_store_snapshot(
        database, "new", [{"a": 1}], [], "https://s.test",
        selectors={"a": "h2"}, json_structure=["a"],
    )
    assert changes["record_count_delta"] == -3
    assert changes["selector_changes"] == {} and changes["json_structure_added"] == []
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(run_snapshots)")}
    assert {"selectors", "json_structure"} <= columns


def test_run_job_reports_selector_and_structure_changes_between_runs(site, tmp_path):
    base = dict(url=f"{site}/api/products", method=AcquisitionMethod.API, authorized_api=True,
                json_records_path="items")
    first = run_job(ScrapeConfig(**base, fields=[FieldRule("id", "id"), FieldRule("name", "name")]), tmp_path)
    assert first.report.changes == {"baseline_created": True}
    second = run_job(ScrapeConfig(**base, fields=[FieldRule("id", "id"), FieldRule("title", "name")]), tmp_path)
    changes = second.report.changes
    assert changes["new_columns"] == ["title"] and changes["missing_fields"] == ["name"]
    assert changes["selector_changes"]["title"] == {"before": None, "after": "name"}
    assert changes["json_structure_added"] == [] and changes["json_structure_removed"] == []
    assert changes["record_count_delta"] == 0
