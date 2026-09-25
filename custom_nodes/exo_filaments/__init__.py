"""Exo filaments: nodos para llevar un modelo generado hasta la impresora."""
from .nodes import comfy_entrypoint  # noqa: F401  (ComfyUI lo busca en el modulo)
from . import estudio  # noqa: F401  (registra las rutas de /exo/estudio)

WEB_DIRECTORY = "./js"
