"""Configuración, validación y perfiles reutilizables de scraping.

Rol en la arquitectura: módulo de configuración. Define el método de
adquisición, las reglas de campos y los límites de seguridad (tiempo, registros,
páginas, clics, desplazamientos y pausa mínima). Los perfiles guardados excluyen
encabezados, credenciales y la confirmación de autorización API.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlparse


class AcquisitionMethod(str, Enum):
    """Método de adquisición de contenido: Requests, Selenium, Playwright o API."""
    REQUESTS = "requests"
    SELENIUM = "selenium"
    PLAYWRIGHT = "playwright"
    API = "api"


@dataclass(frozen=True)
class FieldRule:
    """Regla de extracción de un campo.

    Atributos:
        name: nombre de la columna resultante.
        selector: selector CSS (HTML) o ruta con puntos (JSON).
        attribute: atributo HTML a leer en lugar del texto, si aplica.
        required: si es ``True``, un valor ausente se marca en el linaje.
    """
    name: str
    selector: str
    attribute: str | None = None
    required: bool = False


@dataclass
class ScrapeConfig:
    """Parámetros completos de una ejecución de scraping.

    Incluye URL, método, selectores, límites de seguridad y encabezados
    autorizados (excluidos del ``repr`` y de los perfiles guardados).
    Use ``validate`` antes de ejecutar.
    """
    url: str
    method: AcquisitionMethod = AcquisitionMethod.REQUESTS
    item_selector: str = ""
    fields: list[FieldRule] = field(default_factory=list)
    json_records_path: str = ""
    timeout_seconds: int = 15
    max_records: int = 250
    max_pages: int = 1
    pagination_selector: str = ""
    load_more_selector: str = ""
    load_more_clicks: int = 0
    delay_seconds: float = 1.5
    scroll_steps: int = 0
    headless: bool = True
    authorized_api: bool = False
    headers: dict[str, str] = field(default_factory=dict, repr=False)

    def validate(self) -> None:
        """Verifica que la configuración sea segura y coherente.

        Comprueba esquema http/https, ausencia de credenciales o tokens en la URL,
        y los límites: tiempo 1-30 s, registros 1-1000, páginas 1-10, clics 0-5,
        desplazamientos 0-5, pausa mínima de 1 s, autorización explícita para API,
        campos únicos y encabezados sin saltos de línea.

        Raises:
            ValueError: ante cualquier regla incumplida.
        """
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("La URL debe usar http o https y contener un host.")
        if parsed.username or parsed.password:
            raise ValueError("No incluyas credenciales en la URL; usa un mecanismo autorizado.")
        sensitive_query_keys = {
            "access_token", "apikey", "api_key", "auth", "authorization",
            "client_secret", "password", "secret", "signature", "token",
        }
        if any(key.lower().replace("-", "_") in sensitive_query_keys for key, _ in parse_qsl(parsed.query)):
            raise ValueError("No incluyas tokens ni secretos en la URL; usa encabezados autorizados.")
        if not 1 <= self.timeout_seconds <= 30:
            raise ValueError("El tiempo límite debe estar entre 1 y 30 segundos.")
        if not 1 <= self.max_records <= 1000:
            raise ValueError("El máximo de registros debe estar entre 1 y 1000.")
        if not 1 <= self.max_pages <= 10:
            raise ValueError("El máximo de páginas debe estar entre 1 y 10.")
        if not 0 <= self.load_more_clicks <= 5:
            raise ValueError("El máximo de clics de carga debe estar entre 0 y 5.")
        if self.load_more_clicks and (
            not self.load_more_selector
            or self.method not in {AcquisitionMethod.SELENIUM, AcquisitionMethod.PLAYWRIGHT}
        ):
            raise ValueError("La carga bajo demanda requiere un selector y Selenium o Playwright.")
        if self.delay_seconds < 1:
            raise ValueError("El intervalo entre páginas debe ser de al menos 1 segundo.")
        if not 0 <= self.scroll_steps <= 5:
            raise ValueError("El número de desplazamientos debe estar entre 0 y 5.")
        if self.method == AcquisitionMethod.API and not self.authorized_api:
            raise ValueError("La extracción API requiere confirmar que el endpoint está autorizado.")
        if self.method == AcquisitionMethod.API and not self.fields:
            raise ValueError("Define al menos un campo para extraer JSON de una API.")
        if any(not rule.name.strip() or not rule.selector.strip() for rule in self.fields):
            raise ValueError("Cada campo necesita un nombre y un selector/ruta.")
        if len({rule.name for rule in self.fields}) != len(self.fields):
            raise ValueError("Los nombres de campos deben ser únicos.")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or not key
            or any(char in key + value for char in "\r\n")
            for key, value in self.headers.items()
        ):
            raise ValueError("Se encontró un nombre de encabezado no válido.")


def parse_field_rules(text: str) -> list[FieldRule]:
    """Convierte líneas `nombre=selector` o `nombre=selector::atributo` en reglas.

    Ignora líneas vacías y comentarios (`#`). Un nombre terminado en `*` marca
    el campo como requerido.

    Args:
        text: contenido del área de campos de la interfaz.

    Returns:
        Lista de ``FieldRule``.

    Raises:
        ValueError: si una línea no tiene `=` o tiene nombre/selector vacío.
    """
    rules: list[FieldRule] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Línea {line_number}: se esperaba nombre=selector.")
        name, expression = line.split("=", 1)
        selector, separator, attribute = expression.partition("::")
        name = name.strip()
        selector = selector.strip()
        attribute = attribute.strip() if separator else None
        required = name.endswith("*")
        name = name.removesuffix("*").strip()
        if not name or not selector:
            raise ValueError(f"Línea {line_number}: nombre y selector no pueden estar vacíos.")
        rules.append(FieldRule(name=name, selector=selector, attribute=attribute, required=required))
    return rules


def profile_path(directory: Path, url: str) -> Path:
    """Calcula la ruta del perfil JSON para el host de ``url``.

    El nombre del host se sanea para que sea un nombre de archivo seguro.

    Raises:
        ValueError: si la URL no contiene un host válido.
    """
    host = urlparse(url).hostname
    if not host:
        raise ValueError("No se puede crear un perfil sin un host válido.")
    safe_host = "".join(char if char.isalnum() or char in ".-_" else "_" for char in host)
    return directory / f"{safe_host}.json"


def save_profile(config: ScrapeConfig, directory: Path) -> Path:
    """Guarda reglas técnicas, nunca encabezados de autenticación ni secretos.

    Args:
        config: configuración a guardar (se valida primero).
        directory: carpeta de perfiles; se crea si no existe.

    Returns:
        Ruta del archivo JSON escrito.

    Raises:
        ValueError: si la configuración no es válida.
    """
    config.validate()
    path = profile_path(directory, config.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = asdict(config)
    profile.pop("headers", None)
    profile["method"] = config.method.value
    profile["fields"] = [asdict(rule) for rule in config.fields]
    profile["authorized_api"] = False
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_profile(directory: Path, url: str) -> ScrapeConfig | None:
    """Reconstruye una configuración desde el perfil guardado del host.

    Se descartan encabezados y la autorización API (``authorized_api=False``);
    el usuario debe confirmarlos de nuevo. La validación se hace con una
    autorización temporal solo para perfiles API.

    Returns:
        La configuración, o ``None`` si no existe perfil para ese host.

    Raises:
        ValueError: si el perfil guardado ya no es válido.
    """
    path = profile_path(directory, url)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["url"] = url
    raw["method"] = AcquisitionMethod(raw["method"])
    raw["fields"] = [FieldRule(**item) for item in raw.get("fields", [])]
    raw["headers"] = {}
    raw["authorized_api"] = False
    config = ScrapeConfig(**raw)
    requires_confirmation = config.method == AcquisitionMethod.API
    config.authorized_api = True if requires_confirmation else False
    config.validate()
    config.authorized_api = False
    return config
