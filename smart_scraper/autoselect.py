"""Selección automática: detecta registros, campos y paginación sin selectores.

Rol en la arquitectura: apoyo del módulo de selección. Cuando el usuario deja
vacíos los campos, analiza el HTML (estático o ya renderizado por el navegador)
y propone:

* ``item_selector``: el grupo de elementos hermanos con la misma estructura que
  más información contiene (tarjetas, filas de tabla, artículos, ítems de lista);
* ``fields``: un campo por cada texto y atributo útil dentro de cada registro
  (texto, ``href``, ``src``, ``title``, ``alt``, ``datetime``), con nombres
  derivados de las clases CSS o de los encabezados de la tabla;
* ``pagination_selector``: el enlace de "siguiente página", si existe.

El resultado son selectores CSS normales (``FieldRule``), así que se aplican con
``selection.select_html``, se guardan en el perfil y el usuario puede editarlos.
No hace solicitudes de red.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Tag

from .config import FieldRule, format_field_rules

if TYPE_CHECKING:
    from .config import ScrapeConfig

# Etiquetas que nunca forman parte de un registro.
_IGNORADAS = {
    "script", "style", "noscript", "svg", "template", "head", "iframe", "link",
    "meta", "br", "hr", "select", "option", "input", "button", "path",
}
# Zonas de navegación: sus listas (menús) se penalizan.
_ZONAS_NAVEGACION = {"nav", "header", "footer", "aside"}
# Clases de utilidad o de estado que no describen el contenido.
_CLASES_RUIDO = {
    "active", "selected", "current", "odd", "even", "first", "last", "clearfix",
    "row", "col", "container", "hidden", "visible", "show", "fade", "in",
}
_CLASE_VALIDA = re.compile(r"^[A-Za-z_][A-Za-z_-]*$")
# Prefijos de clases utilitarias (Bootstrap, Tailwind...) que cambian entre registros.
_PREFIJO_UTILIDAD = re.compile(
    r"^(text|bg|btn|col|d|p[trblxy]?|m[trblxy]?|float|align|justify|flex|w|h|border|"
    r"rounded|shadow|font|fw|fs|is|has|js|ng|v|g|gap|order|offset|visually|sr)-",
    re.IGNORECASE,
)
# Selector que representa al propio registro (ver ``selection.select_html``).
SELECTOR_PROPIO = ":scope"
# Atributos que se extraen como campo propio, por etiqueta ("*" = cualquiera).
_ATRIBUTOS = {"a": ("href", "title"), "img": ("src", "alt"), "time": ("datetime",), "*": ("title",)}
_NOMBRE_ATRIBUTO = {"href": "url", "src": "imagen", "alt": "alt", "title": "titulo", "datetime": "fecha"}
_NOMBRE_ETIQUETA = {
    "h1": "titulo", "h2": "titulo", "h3": "titulo", "h4": "titulo", "h5": "titulo", "h6": "titulo",
    "a": "enlace", "img": "imagen", "p": "texto", "span": "texto", "div": "texto",
    "small": "detalle", "strong": "destacado", "b": "destacado", "em": "enfasis",
    "time": "fecha", "li": "elemento", "td": "columna", "th": "columna", "dd": "valor", "dt": "etiqueta",
}
_PAGINACION = (
    'a[rel~="next"]',
    "li.next > a",
    "a.next",
    ".pagination .next > a",
    ".pagination a.next",
    'a[aria-label="Next"]',
    'a[aria-label="Siguiente"]',
    "a.pagination-next",
    "a.next-page",
)
_TEXTOS_SIGUIENTE = ("next", "siguiente", "next page", "página siguiente", "older posts", "›", "»", "next ›", "next »")

MIN_REPETICIONES = 3
MAX_CAMPOS = 15
COBERTURA_MINIMA = 0.5  # fracción de registros donde el campo debe tener valor


@dataclass
class EstructuraDetectada:
    """Selectores propuestos por la detección automática.

    Atributos:
        item_selector: selector CSS de cada registro.
        fields: reglas de campos relativas al registro.
        pagination_selector: enlace de siguiente página ("" si no se detectó).
        total_registros: registros que el selector encuentra en la página analizada.
    """
    item_selector: str
    fields: list[FieldRule] = field(default_factory=list)
    pagination_selector: str = ""
    total_registros: int = 0

    def aplicar(self, config: "ScrapeConfig") -> "ScrapeConfig":
        """Devuelve una copia de ``config`` con los selectores detectados.

        La paginación detectada solo se usa si el usuario no indicó una.
        """
        return replace(
            config,
            item_selector=self.item_selector,
            fields=list(self.fields),
            pagination_selector=config.pagination_selector or self.pagination_selector,
        )

    def resumen(self) -> str:
        """Texto breve para el log y el panel de progreso."""
        nombres = ", ".join(rule.name for rule in self.fields)
        linea = f"Selección automática: {self.total_registros} registros con «{self.item_selector}»; campos: {nombres}"
        if self.pagination_selector:
            linea += f"; siguiente página: «{self.pagination_selector}»"
        return linea

    def to_dict(self) -> dict:
        """Forma serializable (para el informe JSON)."""
        return {
            "item_selector": self.item_selector,
            "fields": format_field_rules(self.fields).splitlines(),
            "pagination_selector": self.pagination_selector,
            "total_registros": self.total_registros,
        }


# ----------------------------------------------------------------- utilidades
def _clases(elemento: Tag) -> list[str]:
    """Clases estables del elemento (sin utilidades, estados ni números)."""
    clases = elemento.get("class") or []
    return [
        clase for clase in clases
        if _CLASE_VALIDA.match(clase)
        and clase.lower() not in _CLASES_RUIDO
        and not _PREFIJO_UTILIDAD.match(clase)
    ][:3]


def _paso(elemento: Tag) -> str:
    """Selector de un solo nivel: ``etiqueta.clase1.clase2``."""
    return elemento.name + "".join(f".{clase}" for clase in _clases(elemento))


def _hijos(elemento: Tag) -> list[Tag]:
    return [hijo for hijo in elemento.find_all(True, recursive=False) if hijo.name not in _IGNORADAS]


def _texto(elemento: Tag) -> str:
    return re.sub(r"\s+", " ", elemento.get_text(" ", strip=True)).strip()


def _texto_propio(elemento: Tag) -> str:
    """Texto que el elemento contiene directamente (no el de sus hijos)."""
    partes = [str(nodo) for nodo in elemento.find_all(string=True, recursive=False)]
    return re.sub(r"\s+", " ", " ".join(partes)).strip()


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^A-Za-z0-9]+", "_", texto).strip("_").lower()
    return texto[:40]


def _en_navegacion(elemento: Tag) -> bool:
    for ancestro in elemento.parents:
        if ancestro.name in _ZONAS_NAVEGACION or ancestro.get("role") == "navigation":
            return True
    return False


# ------------------------------------------------------------ grupos candidatos
def _grupos(soup: BeautifulSoup) -> list[list[Tag]]:
    """Grupos de elementos con la misma etiqueta, clases y contexto (al menos 3).

    Se agrupan por la firma del elemento y la de sus dos ancestros, de modo que
    las tarjetas repartidas en varias filas (``div.row > div.card`` × N) forman
    un único grupo.
    """
    por_firma: dict[tuple[str, str, str], list[Tag]] = defaultdict(list)
    for padre in soup.find_all(True):
        if padre.name in _IGNORADAS:
            continue
        abuelo = padre.parent
        contexto = _paso(abuelo) if isinstance(abuelo, Tag) else ""
        for hijo in _hijos(padre):
            por_firma[(contexto, _paso(padre), _paso(hijo))].append(hijo)
    return [
        _descender(elementos)
        for elementos in por_firma.values()
        if len(elementos) >= MIN_REPETICIONES
    ]


def _descender(elementos: list[Tag]) -> list[Tag]:
    """Si cada elemento solo envuelve a un hijo equivalente, usa ese hijo (``li > article``)."""
    while True:
        hijos = [_hijos(elemento) for elemento in elementos]
        if not all(len(lista) == 1 for lista in hijos):
            return elementos
        firmas = {_paso(lista[0]) for lista in hijos}
        hoja = not _hijos(hijos[0][0])
        if len(firmas) != 1 or hoja or not _texto(hijos[0][0]):
            return elementos
        elementos = [lista[0] for lista in hijos]


def _selector_de_grupo(soup: BeautifulSoup, elementos: list[Tag]) -> str:
    """Selector CSS que selecciona exactamente (o casi) los elementos del grupo."""
    objetivo = {id(elemento) for elemento in elementos}
    selector = _paso(elementos[0])
    mejor = selector
    nodo = elementos[0]
    for _ in range(5):
        try:
            encontrados = {id(elemento) for elemento in soup.select(selector)}
        except Exception:
            break
        if encontrados == objetivo:
            return selector
        if objetivo <= encontrados:
            mejor = selector
        nodo = nodo.parent
        if nodo is None or not isinstance(nodo, Tag) or nodo.name in {"[document]", "html"}:
            break
        if nodo.get("id") and _CLASE_VALIDA.match(nodo["id"]):
            candidato = f"#{nodo['id']} {selector}"
            try:
                if {id(e) for e in soup.select(candidato)} >= objetivo:
                    return candidato
            except Exception:
                pass
        selector = f"{_paso(nodo)} > {selector}"
    return mejor


# ------------------------------------------------------------------- campos
def _ruta(item: Tag, elemento: Tag) -> str:
    """Selector relativo de ``elemento`` dentro de ``item`` (``h3 > a``, ``td:nth-of-type(2)``)."""
    pasos: list[str] = []
    nodo = elemento
    while nodo is not None and nodo is not item:
        paso = _paso(nodo)
        padre = nodo.parent
        if padre is not None:
            mismos = [h for h in padre.find_all(nodo.name, recursive=False) if _paso(h) == paso]
            if len(mismos) > 1:
                mismo_tag = padre.find_all(nodo.name, recursive=False)
                paso += f":nth-of-type({mismo_tag.index(nodo) + 1})"
        pasos.append(paso)
        nodo = padre
    return " > ".join(reversed(pasos))


def _encabezados_tabla(item: Tag) -> list[str]:
    """Textos de los ``th`` de la tabla a la que pertenece una fila."""
    tabla = item.find_parent("table")
    if tabla is None:
        return []
    for fila in tabla.find_all("tr"):
        celdas = fila.find_all(["th", "td"], recursive=False)
        if celdas and all(celda.name == "th" for celda in celdas):
            return [_texto(celda) for celda in celdas]
    return []


def _nombre_base(item: Tag, elemento: Tag, encabezados: list[str]) -> str:
    if item.name == "tr" and elemento.name in {"td", "th"} and encabezados:
        posicion = elemento.parent.find_all(["td", "th"], recursive=False).index(elemento)
        if posicion < len(encabezados) and _slug(encabezados[posicion]):
            return _slug(encabezados[posicion])
    nodo = elemento
    while nodo is not None and nodo is not item:
        if _clases(nodo):
            return _slug(_clases(nodo)[0])
        if nodo.name in {"h1", "h2", "h3", "h4", "h5", "h6", "time", "td"}:
            break
        nodo = nodo.parent
    return _NOMBRE_ETIQUETA.get(elemento.name, elemento.name)


def _candidatos_de(item: Tag, encabezados: list[str]) -> list[tuple[str, str | None, str]]:
    """(ruta, atributo, nombre) de cada texto o atributo útil dentro de un registro."""
    salida: list[tuple[str, str | None, str]] = []
    elementos = [item, *item.find_all(True)]
    for elemento in elementos:
        if elemento.name in _IGNORADAS or any(p.name in _IGNORADAS for p in elemento.parents if p is not item):
            continue
        ruta = _ruta(item, elemento)
        base = _nombre_base(item, elemento, encabezados)
        propio = _texto_propio(elemento)
        completo = _texto(elemento)
        if any(char.isalnum() for char in propio) and len(propio) >= 0.5 * len(completo):
            salida.append((ruta or SELECTOR_PROPIO, None, base))
        atributos = _ATRIBUTOS.get(elemento.name, _ATRIBUTOS["*"])
        for atributo in atributos:
            valor = elemento.get(atributo)
            if not valor or not isinstance(valor, str) or valor.strip() in {"#", ""}:
                continue
            if valor.lower().startswith("javascript:"):
                continue
            if atributo == "title" and valor.strip() == completo:
                continue
            if not ruta:  # atributo del propio registro (p. ej. <a class="card" href>)
                continue
            salida.append((ruta, atributo, f"{base}_{_NOMBRE_ATRIBUTO[atributo]}"))
    return salida


def _valor(item: Tag, ruta: str, atributo: str | None) -> str | None:
    try:
        elegido = item if ruta == SELECTOR_PROPIO else item.select_one(ruta)
    except Exception:
        return None
    if elegido is None:
        return None
    valor = elegido.get(atributo) if atributo else _texto(elegido)
    if isinstance(valor, list):
        valor = " ".join(valor)
    return valor or None


def _es_relleno(clave: tuple[str, str | None], valor: str) -> bool:
    """Valor repetido en todos los registros que no aporta información."""
    ruta, atributo = clave
    if atributo is not None:
        return True
    ultimo = ruta.rsplit(">", 1)[-1].strip()
    es_enlace = re.match(r"^a(?:[.:]|$)", ultimo) is not None
    etiqueta = valor.rstrip().endswith(":")  # "Capital:", "Precio:"
    return (es_enlace and len(valor) <= 25) or etiqueta or len(valor) <= 1


def _detectar_campos(items: list[Tag]) -> list[FieldRule]:
    """Campos presentes en la mayoría de los registros, sin constantes ni duplicados."""
    muestra = items[:40]
    encabezados = _encabezados_tabla(items[0]) if items[0].name == "tr" else []
    orden: list[tuple[str, str | None]] = []
    nombres: dict[tuple[str, str | None], str] = {}
    for item in muestra:
        for ruta, atributo, nombre in _candidatos_de(item, encabezados):
            clave = (ruta, atributo)
            if clave not in nombres:
                nombres[clave] = nombre
                orden.append(clave)

    columnas: list[tuple[tuple[str, str | None], list[str | None], float]] = []
    vistas: set[tuple] = set()
    for clave in orden:
        valores = [_valor(item, *clave) for item in muestra]
        presentes = [valor for valor in valores if valor is not None]
        cobertura = len(presentes) / len(muestra)
        if cobertura < COBERTURA_MINIMA:
            continue
        if len(muestra) >= MIN_REPETICIONES and len(set(presentes)) == 1 and _es_relleno(clave, presentes[0]):
            continue  # constante: "Leer más", "(about)", un mismo enlace...
        firma = tuple(valores)
        if firma in vistas:
            continue  # misma información con otra ruta
        vistas.add(firma)
        columnas.append((clave, valores, cobertura))

    if len(columnas) > MAX_CAMPOS:
        mejores = sorted(columnas, key=lambda columna: -columna[2])[:MAX_CAMPOS]
        conservar = {id(columna) for columna in mejores}
        columnas = [columna for columna in columnas if id(columna) in conservar]

    reglas: list[FieldRule] = []
    usados: dict[str, int] = {}
    for (ruta, atributo), _valores, _cobertura in columnas:
        nombre = nombres[(ruta, atributo)] or "campo"
        usados[nombre] = usados.get(nombre, 0) + 1
        if usados[nombre] > 1:
            nombre = f"{nombre}_{usados[nombre]}"
        reglas.append(FieldRule(name=nombre, selector=ruta, attribute=atributo))
    return reglas


# --------------------------------------------------------------- paginación
def detectar_paginacion(soup: BeautifulSoup) -> str:
    """Selector CSS del enlace "siguiente página", o "" si no hay."""
    for selector in _PAGINACION:
        try:
            nodo = soup.select_one(selector)
        except Exception:
            continue
        if nodo is not None and (nodo.get("href") or "").strip() not in {"", "#"}:
            return selector
    for enlace in soup.find_all("a", href=True):
        texto = _texto(enlace).lower()
        if texto in _TEXTOS_SIGUIENTE and enlace["href"].strip() not in {"", "#"}:
            if _clases(enlace):
                return _paso(enlace)
            propio = _texto_propio(enlace) or _texto(enlace)
            return f'a:-soup-contains-own("{propio}")'
    return ""


# ------------------------------------------------------------------- entrada
def _puntaje(elementos: list[Tag], campos: list[FieldRule]) -> float:
    if not campos:
        return 0.0
    texto_medio = sum(len(_texto(elemento)) for elemento in elementos[:40]) / min(len(elementos), 40)
    puntaje = len(elementos) * min(len(campos), 8) * math.log1p(texto_medio)
    if _en_navegacion(elementos[0]):
        puntaje *= 0.2
    if len(campos) == 1:
        puntaje *= 0.5
    # Campos con ``:nth-of-type`` fuera de celdas de tabla indican que cada
    # elemento contiene varios registros (p. ej. una fila con 3 tarjetas).
    anidados = sum(
        1 for campo in campos
        if any(":nth-of-type" in paso and not paso.strip().startswith(("td", "th"))
               for paso in campo.selector.split(">"))
    )
    puntaje *= 1 - 0.7 * anidados / len(campos)
    return puntaje


def detectar_estructura(html: str | bytes, item_selector: str = "") -> EstructuraDetectada | None:
    """Detecta registros, campos y paginación en una página.

    Args:
        html: documento HTML (estático o renderizado por el navegador).
        item_selector: si el usuario ya indicó el selector de registros, solo se
            detectan los campos dentro de él; si no encuentra nada, se ignora.

    Returns:
        ``EstructuraDetectada`` o ``None`` si no se encontró ningún grupo
        repetido con información.
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for basura in soup.find_all(["script", "style", "noscript", "template"]):
        basura.decompose()
    paginacion = detectar_paginacion(soup)

    if item_selector:
        try:
            items = soup.select(item_selector)
        except Exception:
            items = []
        if items:
            campos = _detectar_campos(items)
            if campos:
                return EstructuraDetectada(item_selector, campos, paginacion, len(items))

    mejor: tuple[float, list[Tag], list[FieldRule]] | None = None
    vistos: set[tuple[int, ...]] = set()
    for elementos in _grupos(soup):
        clave = tuple(id(elemento) for elemento in elementos)
        if clave in vistos:
            continue
        vistos.add(clave)
        campos = _detectar_campos(elementos)
        puntaje = _puntaje(elementos, campos)
        if puntaje > 0 and (mejor is None or puntaje > mejor[0]):
            mejor = (puntaje, elementos, campos)
    if mejor is None:
        return None
    _, elementos, campos = mejor
    selector = _selector_de_grupo(soup, elementos)
    try:
        total = len(soup.select(selector))
    except Exception:
        total = len(elementos)
    return EstructuraDetectada(selector, campos, paginacion, total)
