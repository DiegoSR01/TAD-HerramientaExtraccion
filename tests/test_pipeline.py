from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from smart_scraper.app import RunFailure, run_job
from smart_scraper.config import AcquisitionMethod, FieldRule, ScrapeConfig, load_profile
from smart_scraper.extractor import _acquire_playwright, _acquire_selenium, scrape
from smart_scraper.inspector import InspectionError, inspect_url
from smart_scraper.selection import select_html
from smart_scraper.storage import compare_and_store_snapshot, save_results
from smart_scraper.transform import transform_records


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/static": (200, "text/html", b"<html><title>Catalog</title><article><h2> Alpha </h2></article><article><h2>Beta</h2></article></html>"),
            "/dynamic": (200, "text/html", b"<html><script>fetch('/api/products'); new IntersectionObserver(() => {})</script><h1>Client rendered</h1></html>"),
            "/loadmore": (200, "text/html", b"<button>Load more</button><script>button.addEventListener('click', loadMore)</script>"),
            "/api/products": (200, "application/json", b'{"items":[{"id":1,"name":"Alpha"},{"id":2,"name":"Beta"}]}'),
            "/graphql": (200, "application/json", b'{"data":{"products":[{"id":3,"name":"Gamma"}]}}'),
            "/pagination": (
                200, "text/html",
                b'<article><h2>Page 1</h2></article><a class="next" href="/pagination?page=2">Next</a>',
            ),
            "/table": (
                200, "text/html",
                b"<table><thead><tr><th>SKU</th><th>Price</th></tr></thead><tbody><tr><td>A-1</td><td>12</td></tr></tbody></table>",
            ),
            "/auth": (401, "text/html", b'<form><input type="password" name="password"></form>'),
            "/denied": (403, "text/html", b"<html><title>Access Denied</title></html>"),
            "/captcha": (200, "text/html", b"<html><body>Verify you are human - captcha</body></html>"),
        }
        if self.path == "/authorized":
            body = b"<article><h2>Authorized result</h2></article>"
            status, content_type = (
                (200, "text/html") if self.headers.get("Authorization") == "Bearer local-test"
                else (401, "text/html")
            )
            routes[self.path] = (status, content_type, body)
        status, content_type, body = routes.get(
            self.path.split("?", 1)[0],
            (404, "text/plain", b"missing"),
        )
        if self.path.startswith("/pagination?"):
            status, content_type, body = (
                200, "text/html", b"<article><h2>Page 2</h2></article><a class='next' href='/pagination'>Next</a>"
            )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


@pytest.fixture(scope="module")
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()


def test_inspection_recognizes_static_and_dynamic_sites(site):
    static = inspect_url(f"{site}/static").report
    dynamic = inspect_url(f"{site}/dynamic").report
    assert static.rendering == "HTML estático"
    assert static.title == "Catalog"
    assert dynamic.rendering == "dinámico o mixto"
    assert dynamic.infinite_scroll_suspected
    assert dynamic.api_hints
    assert inspect_url(f"{site}/loadmore").report.load_more_detected


def test_inspection_stops_for_auth_and_captcha(site):
    auth = inspect_url(f"{site}/auth").report
    denied = inspect_url(f"{site}/denied").report
    captcha = inspect_url(f"{site}/captcha").report
    assert auth.blocked and auth.authentication_detected
    assert denied.blocked and not denied.authentication_detected
    assert captcha.blocked and captcha.captcha_detected


def test_requests_extraction_and_pagination_are_bounded(site):
    config = ScrapeConfig(
        url=f"{site}/pagination",
        fields=[FieldRule("title", "h2")],
        item_selector="article",
        pagination_selector="a.next",
        max_pages=2,
        delay_seconds=1,
    )
    result = scrape(config)
    assert result.records == [{"title": "Page 1"}, {"title": "Page 2"}]
    assert result.pages_visited == 2


def test_api_json_extraction_requires_authorization_ack(site):
    config = ScrapeConfig(
        url=f"{site}/api/products",
        method=AcquisitionMethod.API,
        authorized_api=True,
        json_records_path="items",
        fields=[FieldRule("id", "id"), FieldRule("name", "name")],
    )
    assert scrape(config).records == [
        {"id": 1, "name": "Alpha"},
        {"id": 2, "name": "Beta"},
    ]
    config.authorized_api = False
    with pytest.raises(ValueError, match="autorizado"):
        config.validate()


def test_graphql_api_and_remote_table_fixtures(site):
    graphql = ScrapeConfig(
        url=f"{site}/graphql",
        method=AcquisitionMethod.API,
        authorized_api=True,
        json_records_path="data.products",
        fields=[FieldRule("id", "id"), FieldRule("name", "name")],
    )
    assert scrape(graphql).records == [{"id": 3, "name": "Gamma"}]
    table = scrape(ScrapeConfig(url=f"{site}/table"))
    assert table.records == [{"SKU": "A-1", "Price": "12"}]


def test_authorized_authentication_is_supported_without_automation(site):
    config = ScrapeConfig(
        url=f"{site}/authorized",
        headers={"Authorization": "Bearer local-test"},
        item_selector="article",
        fields=[FieldRule("title", "h2")],
    )
    assert scrape(config).records == [{"title": "Authorized result"}]


def test_secret_query_parameters_are_rejected():
    with pytest.raises(ValueError, match="tokens"):
        ScrapeConfig("https://example.test/items?access_token=secret").validate()


def test_blocked_sites_and_http_errors_do_not_report_success(site, tmp_path):
    blocked = ScrapeConfig(f"{site}/captcha")
    with pytest.raises(RunFailure) as error:
        run_job(blocked, tmp_path / "captcha-output")
    assert "CAPTCHA" in error.value.outcome.report.error
    with pytest.raises(InspectionError) as error:
        scrape(ScrapeConfig(f"{site}/missing"))
    assert "HTTP 404" in str(error.value)


def test_html_table_selection_and_data_lineage():
    records = select_html(
        "<table><tr><th>SKU</th><th>Price</th></tr><tr><td>A-1</td><td>12</td></tr></table>"
    )
    assert records == [{"SKU": "A-1", "Price": "12"}]
    cleaned, lineage, execution_id = transform_records(
        [{"name": "  Ada   Lovelace ", "email": None}, {"name": "Ada Lovelace", "email": None}],
        [FieldRule("email", "span", required=True)],
        "https://example.invalid",
        "requests",
        "test-run",
    )
    assert execution_id == "test-run"
    assert cleaned == [{"name": "Ada Lovelace", "email": None}]
    assert any(item["validation_status"] == "missing_required" for item in lineage)
    assert all(item["source_url"] == "https://example.invalid" for item in lineage)


def test_run_persists_sqlite_csv_lineage_profile_and_change_report(site, tmp_path):
    config = ScrapeConfig(
        url=f"{site}/static",
        method=AcquisitionMethod.REQUESTS,
        item_selector="article",
        fields=[FieldRule("title", "h2")],
        headers={"Authorization": "never-persist-this"},
    )
    outcome = run_job(config, tmp_path, "csv")
    assert outcome.report.status == "completed"
    assert outcome.report.records_saved == 2
    assert outcome.report.changes == {"baseline_created": True}
    assert any(path.endswith(".csv") for path in outcome.report.output_paths)
    profile = load_profile(tmp_path / "profiles", config.url)
    assert profile and profile.headers == {}
    profile_text = (tmp_path / "profiles" / "127.0.0.1.json").read_text(encoding="utf-8")
    assert "never-persist-this" not in profile_text


def test_snapshot_detects_fields_endpoints_and_volume(tmp_path):
    database = tmp_path / "history.sqlite3"
    compare_and_store_snapshot(database, "one", [{"name": "A"}], ["/api/old"], "https://site.test")
    changes = compare_and_store_snapshot(
        database, "two", [{"name": "A", "price": 1}, {"name": "B", "price": 2}],
        ["/api/new"], "https://site.test",
    )
    assert changes == {
        "added_fields": ["price"],
        "missing_fields": [],
        "new_endpoints": ["/api/new"],
        "removed_endpoints": ["/api/old"],
        "record_count_delta": 1,
    }


def test_json_excel_and_sqlite_exports_include_lineage(tmp_path):
    records, lineage, execution_id = transform_records(
        [{"name": "Example"}],
        [FieldRule("name", "h1", required=True)],
        "https://example.test",
        "requests",
        "export-test",
    )
    json_file = save_results(
        records, lineage, tmp_path / "json", "json", "https://example.test",
        "requests", execution_id,
    )[0]
    json_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert json_data[0]["_lineage"][0]["source_url"] == "https://example.test"
    excel_file = save_results(
        records, lineage, tmp_path / "excel", "excel", "https://example.test",
        "requests", execution_id,
    )[0]
    assert excel_file.exists()
    sqlite_file = save_results(
        records, lineage, tmp_path / "sqlite", "sqlite", "https://example.test",
        "requests", execution_id,
    )[0]
    import sqlite3

    with sqlite3.connect(sqlite_file) as connection:
        assert connection.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM lineage").fetchone()[0] == 1


def test_selenium_adapter_with_local_fixture_and_mocked_driver(site):
    html = "<article><h2>Browser</h2></article>"
    scroll_calls = []
    click_calls = []

    class Driver:
        page_source = html

        def set_page_load_timeout(self, _):
            pass

        def get(self, _):
            pass

        def execute_script(self, script):
            if "readyState" in script:
                return "complete"
            scroll_calls.append(script)
            return None

        def find_elements(self, *_):
            return [SimpleNamespace(click=lambda: click_calls.append("click"))] if len(click_calls) < 2 else []

        def quit(self):
            pass

    class Wait:
        def __init__(self, *_):
            pass

        def until(self, condition):
            return condition(Driver())

    selenium = ModuleType("selenium")
    webdriver = ModuleType("selenium.webdriver")
    webdriver.ChromeOptions = type("ChromeOptions", (), {"add_argument": lambda *_: None})
    webdriver.Chrome = lambda **_: Driver()
    support = ModuleType("selenium.webdriver.support")
    ui = ModuleType("selenium.webdriver.support.ui")
    ui.WebDriverWait = Wait
    selenium.webdriver = webdriver
    with patch.dict(
        "sys.modules",
        {
            "selenium": selenium,
            "selenium.webdriver": webdriver,
            "selenium.webdriver.support": support,
            "selenium.webdriver.support.ui": ui,
        },
    ):
        config = ScrapeConfig(
            f"{site}/static",
            method=AcquisitionMethod.SELENIUM,
            scroll_steps=2,
            load_more_selector="button.more",
            load_more_clicks=2,
        )
        with patch("smart_scraper.extractor.time.sleep"):
            result = _acquire_selenium(config)
        assert "Browser" in result
        assert len(scroll_calls) == 2
        assert len(click_calls) == 2


def test_playwright_adapter_with_local_fixture_and_mocked_browser(site):
    html = "<article><h2>Browser</h2></article>"

    class Page:
        def __init__(self):
            self.click_count = 0

        def goto(self, *_args, **_kwargs):
            return SimpleNamespace(status=200)

        def content(self):
            return html

        def locator(self, _):
            page = self
            return SimpleNamespace(
                count=lambda: 1 if page.click_count < 2 else 0,
                first=SimpleNamespace(click=lambda **_: setattr(page, "click_count", page.click_count + 1)),
            )

        def wait_for_timeout(self, _):
            pass

    class Browser:
        def new_page(self, **_):
            self.page = Page()
            return self.page

        def close(self):
            pass

    class Playwright:
        chromium = SimpleNamespace(launch=lambda **_: Browser())

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    api = ModuleType("playwright.sync_api")
    api.sync_playwright = Playwright
    package = ModuleType("playwright")
    package.sync_api = api
    with patch.dict("sys.modules", {"playwright": package, "playwright.sync_api": api}):
        config = ScrapeConfig(
            f"{site}/dynamic",
            method=AcquisitionMethod.PLAYWRIGHT,
            load_more_selector="button.more",
            load_more_clicks=2,
        )
        assert "Browser" in _acquire_playwright(config)
