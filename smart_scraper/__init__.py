"""Paquete ``smart_scraper``: scraper web modular, configurable y respetuoso.

La herramienta se organiza en siete responsabilidades (ver README.md):
inspección (``inspector``), configuración (``config``), adquisición
(``extractor``), selección (``selection``), transformación (``transform``),
almacenamiento (``storage``) y monitoreo (``monitoring``). ``app`` coordina el
flujo completo y ``gui`` ofrece la interfaz Tkinter.

El paquete se detiene ante CAPTCHA, autenticación o respuestas 401/403/429 y
nunca intenta evadir esas restricciones.
"""

__version__ = "1.0.0"
