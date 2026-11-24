"""Sitio local para probar a mano la pausa por CAPTCHA con intervención humana.

Levanta un servidor en http://127.0.0.1:8765 con tres páginas paginadas:

* ``/``         página 1, sin CAPTCHA (3 registros).
* ``/pagina2``  muestra un CAPTCHA simulado hasta que la persona pulsa
  "Verificar"; eso guarda la cookie ``captcha_ok`` y recarga la página.
* ``/pagina3``  exige la misma cookie: si la sesión del navegador se conservó,
  ya no vuelve a aparecer el CAPTCHA.

El "CAPTCHA" es un widget falso (``<div id="captcha" data-captcha-demo>``) que
solo sirve para ejercitar el flujo de pausa y reanudación; no hay ningún
proveedor real involucrado. Uso:

    python scripts/sitio_captcha_local.py

y en la GUI: método selenium o playwright, URL http://127.0.0.1:8765/,
selector de registros ``article.item``, campo ``titulo=h2``, siguiente página
``a.next``, páginas máx. 3.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = 8765

_PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{titulo}</title>
<style>body{{font-family:sans-serif;max-width:640px;margin:2rem auto}}
#captcha{{border:2px solid #d97706;padding:1rem;border-radius:8px;background:#fff7ed}}</style>
</head><body><h1>{titulo}</h1>{contenido}</body></html>"""

_CAPTCHA = """<div id="captcha" data-captcha-demo>
  <p><strong>CAPTCHA de prueba (local).</strong> Marca la casilla y pulsa Verificar.</p>
  <label><input type="checkbox" id="no-robot"> No soy un robot</label>
  <button id="verificar" type="button">Verificar</button>
  <p id="aviso" style="color:#b91c1c"></p>
</div>
<script>
document.getElementById("verificar").addEventListener("click", function () {
  if (!document.getElementById("no-robot").checked) {
    document.getElementById("aviso").textContent = "Marca la casilla primero.";
    return;
  }
  document.cookie = "captcha_ok=1; path=/";
  location.reload();
});
</script>"""


def _registros(pagina: int) -> str:
    return "".join(
        f'<article class="item"><h2>Registro {pagina}.{n}</h2></article>' for n in range(1, 4)
    )


class Manejador(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (nombre impuesto por http.server)
        ruta = self.path.split("?", 1)[0]
        resuelto = "captcha_ok=1" in (self.headers.get("Cookie") or "")
        if ruta == "/":
            contenido = _registros(1) + '<a class="next" href="/pagina2">Siguiente</a>'
            pagina = _PLANTILLA.format(titulo="Página 1", contenido=contenido)
        elif ruta in {"/pagina2", "/pagina3"}:
            numero = int(ruta[-1])
            if resuelto:
                siguiente = '<a class="next" href="/pagina3">Siguiente</a>' if numero == 2 else ""
                contenido = _registros(numero) + siguiente
            else:
                contenido = _CAPTCHA
            pagina = _PLANTILLA.format(titulo=f"Página {numero}", contenido=contenido)
        else:
            self.send_error(404)
            return
        cuerpo = pagina.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)


def main() -> None:
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    print(f"Sitio de prueba con CAPTCHA en http://127.0.0.1:{PUERTO}/  (Ctrl+C para salir)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
