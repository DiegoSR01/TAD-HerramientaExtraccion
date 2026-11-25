"""Fixtures compartidas: servidor HTTP local con sitios de prueba (sin red pública)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


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
            "/catalogo": (
                200, "text/html",
                (
                    "<html><title>Catálogo</title><main>"
                    + "".join(
                        f'<div class="card"><h2 class="nombre">Producto {n}</h2>'
                        f'<span class="precio">${n}0</span><a href="/p/{n}">Ver</a></div>'
                        for n in range(1, 5)
                    )
                    + '</main><a rel="next" href="/catalogo?p=2">Siguiente</a></html>'
                ).encode("utf-8"),
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
