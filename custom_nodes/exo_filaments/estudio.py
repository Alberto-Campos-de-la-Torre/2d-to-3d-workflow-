"""Estudio de imagen: pagina propia dentro de ComfyUI para generar con Qwen-Image 2.1
(GGUF) y revisar los resultados.

  http://127.0.0.1:8188/exo/estudio

La generacion va por la API normal de ComfyUI (/prompt y el websocket); aqui solo
estan las rutas que la API no trae: listar lo generado con sus ajustes (leidos del
propio PNG, asi sobreviven a reinicios) y guardar la revision de cada imagen.
"""
import json
import os
import shutil
import threading
from pathlib import Path

from aiohttp import web
from PIL import Image

import folder_paths
from server import PromptServer

CARPETA = "qwen21"  # subcarpeta de output donde guarda el estudio
PAGINA = Path(__file__).parent / "estudio" / "estudio.html"
_bloqueo = threading.Lock()
_cache = {}  # ruta -> (mtime, ficha)


def _salida():
    return Path(folder_paths.get_output_directory()) / CARPETA


def _fichero_revisiones():
    ruta = Path(folder_paths.get_user_directory()) / "default" / "exo_estudio" / "revisiones.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


def _leer_revisiones():
    ruta = _fichero_revisiones()
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ajustes_del_grafo(grafo):
    """Saca del grafo en formato API (guardado en el PNG) lo que interesa revisar."""
    ajustes = {}
    for nodo in grafo.values():
        clase, e = nodo.get("class_type"), nodo.get("inputs", {})
        if clase == "TextEncodeQwenImage21":
            ajustes["prompt"] = e.get("prompt", "")
            ajustes["negativo"] = e.get("negative_prompt", "")
            ajustes["referencia"] = any(k.startswith("images.") for k in e)
        elif clase == "KSampler":
            for k in ("seed", "steps", "cfg", "sampler_name", "scheduler"):
                ajustes[k] = e.get(k)
        elif clase in ("UnetLoaderGGUF", "UNETLoader"):
            ajustes["modelo"] = e.get("unet_name")
        elif clase == "LoadImage":
            ajustes["imagen_ref"] = e.get("image")
    return ajustes


def _ficha(ruta):
    mtime = ruta.stat().st_mtime
    guardada = _cache.get(ruta)
    if guardada and guardada[0] == mtime:
        return guardada[1]
    ficha = {"archivo": ruta.name, "fecha": mtime}
    try:
        with Image.open(ruta) as img:
            ficha["ancho"], ficha["alto"] = img.size
            texto = getattr(img, "text", {}) or {}
        if "prompt" in texto:
            ficha.update(_ajustes_del_grafo(json.loads(texto["prompt"])))
    except (OSError, ValueError):
        pass
    _cache[ruta] = (mtime, ficha)
    return ficha


def _nombre_seguro(nombre):
    nombre = os.path.basename(str(nombre or ""))
    if not nombre or not (_salida() / nombre).is_file():
        raise web.HTTPNotFound(text="imagen no encontrada")
    return nombre


rutas = PromptServer.instance.routes


@rutas.get("/exo/estudio")
async def pagina(_):
    return web.FileResponse(PAGINA, headers={"Cache-Control": "no-store"})


@rutas.get("/exo/estudio/imagenes")
async def imagenes(_):
    carpeta = _salida()
    fichas = []
    if carpeta.exists():
        for ruta in carpeta.glob("*.png"):
            fichas.append(_ficha(ruta))
    fichas.sort(key=lambda f: f["fecha"], reverse=True)
    return web.json_response({"carpeta": CARPETA, "imagenes": fichas, "revisiones": _leer_revisiones()})


@rutas.post("/exo/estudio/revision")
async def revision(peticion):
    """Guarda la revision de una imagen. Solo toca los campos que llegan."""
    datos = await peticion.json()
    nombre = _nombre_seguro(datos.get("archivo"))
    permitidos = {"estado", "estrellas", "nota", "segundos"}
    with _bloqueo:
        todas = _leer_revisiones()
        actual = todas.get(nombre, {})
        actual.update({k: v for k, v in datos.items() if k in permitidos})
        todas[nombre] = actual
        _fichero_revisiones().write_text(json.dumps(todas, indent=1, ensure_ascii=False), encoding="utf-8")
    return web.json_response(actual)


@rutas.post("/exo/estudio/prompt")
async def escribir_prompt(peticion):
    """Convierte una idea corta en un prompt completo con la IA local.

    El modo lo decide la casilla 'pensada para pasar a 3D' del estudio: con ella puesta
    se imponen las reglas que necesita la conversion a modelo.
    """
    from .prompt_ia import mejorar

    datos = await peticion.json()
    prompt, aviso = mejorar(
        datos.get("idea", ""),
        "3d" if datos.get("para3d") else "imagen",
        semilla=datos.get("semilla") or None,
    )
    return web.json_response({"prompt": prompt, "aviso": aviso})


@rutas.post("/exo/estudio/a_entrada")
async def a_entrada(peticion):
    """Copia la imagen a input/ para usarla en el flujo imagen -> 3D."""
    datos = await peticion.json()
    nombre = _nombre_seguro(datos.get("archivo"))
    destino = Path(folder_paths.get_input_directory()) / f"qwen_{nombre}"
    shutil.copy2(_salida() / nombre, destino)
    return web.json_response({"entrada": destino.name})
