"""Pausa con intervención humana cuando el navegador encuentra un CAPTCHA.

Rol en la arquitectura: puente entre el hilo del scraper y la interfaz. Cuando
``extractor`` detecta un CAPTCHA en un navegador real (Selenium o Playwright),
no lo resuelve: deja el navegador abierto (con su sesión, cookies y página),
lo hace visible si estaba en modo headless y pide a una persona que lo resuelva
a mano. La espera tiene un tiempo límite; al agotarse se trata como "omitir".

Comunicación entre hilos (nunca se tocan widgets desde el hilo del scraper):

* El hilo del scraper llama a ``CanalIntervencion.solicitar``: deja una
  ``SolicitudCaptcha`` en una ``queue.Queue`` y se bloquea en un
  ``threading.Event`` hasta que haya respuesta o venza el plazo.
* El hilo de la interfaz consulta ``CanalIntervencion.siguiente`` de forma
  periódica (``root.after``), muestra el aviso modal y llama a
  ``SolicitudCaptcha.responder`` con la decisión del usuario.

Este módulo no implementa ninguna resolución automática del CAPTCHA (ni OCR,
ni servicios de terceros, ni clics simulados): quien lo resuelve es la persona.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable

DEFAULT_CAPTCHA_TIMEOUT_SECONDS = 300


class Decision(str, Enum):
    """Botón pulsado por el usuario en el aviso de CAPTCHA."""
    CONTINUAR = "continuar"
    OMITIR = "omitir"
    CANCELAR = "cancelar"


class Resultado(str, Enum):
    """Cómo terminó una espera de intervención humana."""
    RESUELTO = "resuelto"
    OMITIDO = "omitido"
    EXPIRADO = "expirado"
    CANCELADO = "cancelado"


class PaginaOmitida(RuntimeError):
    """La página con CAPTCHA se omite (por decisión del usuario o por tiempo agotado)."""

    def __init__(self, url: str, resultado: Resultado):
        super().__init__(f"Página omitida ({resultado.value}) por CAPTCHA: {url}")
        self.url = url
        self.resultado = resultado


class ExtraccionCancelada(RuntimeError):
    """El usuario canceló la extracción desde el aviso de CAPTCHA."""

    def __init__(self, url: str):
        super().__init__(f"Extracción cancelada por el usuario en {url}")
        self.url = url


@dataclass
class SolicitudCaptcha:
    """Petición de intervención que el hilo del scraper envía a la interfaz.

    Atributos:
        url: página donde está el CAPTCHA.
        intento: 1 en el primer aviso; >1 si al pulsar Continuar seguía presente.
        plazo: instante (``time.monotonic``) en que vence la espera.
    """
    url: str
    intento: int
    plazo: float
    decision: Decision | None = None
    _respondida: threading.Event = field(default_factory=threading.Event, repr=False)
    _cerrada: threading.Event = field(default_factory=threading.Event, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def mensaje(self) -> str:
        """Texto del aviso modal."""
        texto = (
            f"Se detectó un CAPTCHA en {self.url}. Resuélvelo manualmente en la ventana "
            "del navegador y presiona Continuar."
        )
        if self.intento > 1:
            texto = "El CAPTCHA sigue presente en la página.\n\n" + texto
        return texto

    def segundos_restantes(self) -> int:
        """Segundos que faltan para que venza la espera (nunca negativo)."""
        return max(0, int(self.plazo - time.monotonic()))

    @property
    def cerrada(self) -> bool:
        """``True`` si el hilo del scraper ya no espera esta respuesta (venció el plazo)."""
        return self._cerrada.is_set()

    def responder(self, decision: Decision) -> bool:
        """Entrega la decisión del usuario (se llama desde el hilo de la interfaz).

        Returns:
            ``False`` si la solicitud ya había vencido y la decisión se ignora.
        """
        with self._lock:
            if self._cerrada.is_set() or self._respondida.is_set():
                return False
            self.decision = decision
            self._respondida.set()
            return True

    def _esperar(self) -> Decision | None:
        """Bloquea el hilo del scraper hasta la respuesta o el vencimiento del plazo."""
        self._respondida.wait(max(0.0, self.plazo - time.monotonic()))
        with self._lock:
            if self._respondida.is_set():
                return self.decision
            self._cerrada.set()
            return None


class CanalIntervencion:
    """Cola de solicitudes de CAPTCHA entre el hilo del scraper y la interfaz."""

    def __init__(self) -> None:
        self._pendientes: queue.Queue[SolicitudCaptcha] = queue.Queue()

    def solicitar(self, url: str, intento: int, plazo: float) -> Decision | None:
        """Publica una solicitud y espera la decisión (hilo del scraper).

        Returns:
            La decisión del usuario, o ``None`` si venció el plazo.
        """
        solicitud = SolicitudCaptcha(url, intento, plazo)
        self._pendientes.put(solicitud)
        return solicitud._esperar()

    def siguiente(self) -> SolicitudCaptcha | None:
        """Devuelve la siguiente solicitud pendiente sin bloquear (hilo de la interfaz)."""
        try:
            return self._pendientes.get_nowait()
        except queue.Empty:
            return None


Notificador = Callable[[str, str], None]


class IntervencionHumana:
    """Encapsula el flujo de pausa y reanudación ante un CAPTCHA.

    La sesión de navegador se vincula con ``vincular``: aporta la función que
    revisa si el CAPTCHA sigue en la página y la que hace visible el navegador.
    """

    def __init__(
        self,
        canal: CanalIntervencion,
        timeout_seconds: int = DEFAULT_CAPTCHA_TIMEOUT_SECONDS,
        logger: logging.Logger | None = None,
        notificar: Notificador | None = None,
    ):
        """Crea el controlador.

        Args:
            canal: canal hacia la interfaz.
            timeout_seconds: tiempo máximo total de espera por CAPTCHA.
            logger: logger de la ejecución (``smart_scraper.log``).
            notificar: callback opcional ``notificar(texto, estado)`` para el
                registro de eventos de la interfaz (estado: running/blocked/done).
        """
        self.canal = canal
        self.timeout_seconds = timeout_seconds
        self.logger = logger or logging.getLogger("smart_scraper")
        self.notificar = notificar
        self.eventos: list[dict[str, str]] = []
        self._verificar: Callable[[], bool] | None = None
        self._asegurar_visible: Callable[[], bool] | None = None

    def vincular(self, verificar: Callable[[], bool], asegurar_visible: Callable[[], bool]) -> None:
        """Asocia la sesión de navegador actual.

        Args:
            verificar: devuelve ``True`` si la página actual sigue mostrando un CAPTCHA.
            asegurar_visible: hace visible el navegador; devuelve ``True`` si lo relanzó.
        """
        self._verificar = verificar
        self._asegurar_visible = asegurar_visible

    def _registrar(self, evento: str, url: str, detalle: str = "", estado: str = "blocked") -> None:
        """Escribe el evento en el log, en el informe y en la interfaz."""
        hora = datetime.now().isoformat(timespec="seconds")
        self.eventos.append({"hora": hora, "evento": evento, "url": url, "detalle": detalle})
        texto = f"CAPTCHA {evento} | {url}" + (f" | {detalle}" if detalle else "")
        log = self.logger.warning if evento in {"detectado", "omitido", "expirado", "cancelado"} else self.logger.info
        log(texto)
        if self.notificar:
            try:
                self.notificar(texto, estado)
            except Exception:  # la interfaz nunca debe interrumpir el scraping
                pass

    def esperar_intervencion_humana(self, url: str) -> Resultado:
        """Pausa la extracción hasta que una persona resuelva el CAPTCHA de ``url``.

        Flujo: registrar la detección, hacer visible el navegador (sin cerrarlo
        si ya era visible), mostrar el aviso y esperar. Con *Continuar* se
        revisa la página: si el CAPTCHA sigue, se vuelve a avisar; si no, se
        reanuda. *Omitir*, *Cancelar* y el vencimiento del plazo terminan la espera.

        Args:
            url: página donde apareció el CAPTCHA.

        Returns:
            ``Resultado.RESUELTO``, ``OMITIDO``, ``EXPIRADO`` o ``CANCELADO``.
        """
        if self._verificar is None or self._asegurar_visible is None:
            raise RuntimeError("IntervencionHumana necesita una sesión de navegador vinculada.")
        self._registrar("detectado", url, f"espera máxima {self.timeout_seconds} s")
        try:
            if self._asegurar_visible():
                self._registrar("navegador relanzado en modo visible", url, estado="running")
        except Exception as exc:
            self._registrar("cancelado", url, f"no se pudo mostrar el navegador: {exc}")
            return Resultado.CANCELADO
        plazo = time.monotonic() + self.timeout_seconds
        intento = 1
        while True:
            decision = self.canal.solicitar(url, intento, plazo)
            if decision is None:
                self._registrar("expirado", url, "tiempo de espera agotado; se omite la página")
                return Resultado.EXPIRADO
            if decision == Decision.OMITIR:
                self._registrar("omitido", url, "omitido por el usuario")
                return Resultado.OMITIDO
            if decision == Decision.CANCELAR:
                self._registrar("cancelado", url, "extracción cancelada por el usuario")
                return Resultado.CANCELADO
            try:
                sigue = self._verificar()
            except Exception as exc:  # p. ej. el usuario cerró la ventana del navegador
                self._registrar("cancelado", url, f"no se pudo revisar el navegador: {exc}")
                return Resultado.CANCELADO
            if not sigue:
                self._registrar("resuelto", url, "se reanuda la extracción", estado="running")
                return Resultado.RESUELTO
            intento += 1
            self._registrar("sigue presente", url, f"aviso n.º {intento}")
