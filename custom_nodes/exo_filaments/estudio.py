"""Estudio de imagen: pagina propia dentro de ComfyUI para generar con Qwen-Image 2.1
(GGUF) y revisar los resultados.

  http://127.0.0.1:8188/exo/estudio

La generacion va por la API normal de ComfyUI (/prompt y el websocket); aqui solo
estan las rutas que la API no trae: listar lo generado con sus ajustes (leidos del
propio PNG, asi sobreviven a reinicios) y guardar la revision de cada imagen.
"""
import asyncio
import json
import os
import shutil
import threading
import uuid
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
            # Puede haber varias referencias; se guardan todas en orden.
            ajustes.setdefault("imagenes_ref", []).append(e.get("image"))
            ajustes["imagen_ref"] = e.get("image")   # compatibilidad con fichas antiguas
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


_bucles = {}   # id -> estado del bucle en curso


async def _generar_y_esperar(grafo, tiempo_max=600):
    """Encola un grafo en ComfyUI y espera a que acabe. Devuelve el nombre del PNG."""
    import aiohttp

    async with aiohttp.ClientSession() as sesion:
        async with sesion.post("http://127.0.0.1:8188/prompt", json={"prompt": grafo}) as r:
            respuesta = await r.json()
        if respuesta.get("node_errors"):
            raise RuntimeError(json.dumps(respuesta["node_errors"])[:400])
        pid = respuesta["prompt_id"]

        limite = asyncio.get_event_loop().time() + tiempo_max
        while asyncio.get_event_loop().time() < limite:
            await asyncio.sleep(2)
            async with sesion.get(f"http://127.0.0.1:8188/history/{pid}") as r:
                historial = await r.json()
            if pid not in historial:
                continue
            estado = historial[pid].get("status", {})
            if estado.get("status_str") != "success":
                raise RuntimeError(json.dumps(estado.get("messages", []))[:400])
            for salida in historial[pid]["outputs"].values():
                for imagen in salida.get("images", []):
                    return imagen["filename"]
            raise RuntimeError("el trabajo no devolvio ninguna imagen")
    raise RuntimeError("se agoto el tiempo esperando a ComfyUI")


def _anotar(estado, texto):
    """Suma una nota al ultimo intento sin pisar la que hubiera."""
    if not estado.get("historial"):
        return
    intento = estado["historial"][-1]
    intento["nota"] = (intento.get("nota") + " · " + texto) if intento.get("nota") else texto


def _rutas_referencias(grafo, nodo_texto):
    """Rutas en input/ de las referencias colgadas del nodo de texto, en orden."""
    entrada = Path(folder_paths.get_input_directory())
    rutas = []
    for clave in sorted(k for k in grafo[nodo_texto]["inputs"] if k.startswith("images.image_")):
        enlace = grafo[nodo_texto]["inputs"][clave]
        if not isinstance(enlace, list):
            continue
        cargador = grafo.get(enlace[0], {})
        nombre = (cargador.get("inputs") or {}).get("image")
        if nombre and (entrada / nombre).exists():
            rutas.append(entrada / nombre)
    return rutas


async def _correr_bucle(id_bucle, grafo, intentos, para3d=True, ciclos=2,
                        observaciones=""):
    """Generar -> criticar -> corregir, hasta que salga limpia o se agoten los intentos."""
    from PIL import Image

    from .critica import (CONDICIONES_CON_CUERPO, corregir, corregir_con_usuario,
                          criticar, resumen)
    from .prompt_ia import mejorar

    estado = _bucles[id_bucle]
    nodo_texto = next((n for n, d in grafo.items() if d.get("class_type") == "TextEncodeQwenImage21"), None)
    nodo_muestreo = next((n for n, d in grafo.items() if d.get("class_type") == "KSampler"), None)
    if not nodo_texto or not nodo_muestreo:
        estado.update(terminado=True, error="el grafo no trae los nodos esperados")
        return

    # Cuantas referencias lleva el grafo: cambia que se considera defecto y como se corrige.
    referencias = sum(1 for k in grafo[nodo_texto]["inputs"] if k.startswith("images.image_"))
    estado["referencias"] = referencias

    sin_mejora = 0
    for vuelta in range(int(intentos)):
        estado["intento"] = vuelta + 1
        # Todo el intento va dentro del try: si algo revienta al revisar (la imagen no esta
        # donde se espera, la IA no contesta) hay que marcar la tarea como terminada igual,
        # o la interfaz se queda preguntando por un bucle que ya no avanza.
        try:
            archivo = await _generar_y_esperar(grafo)
            ruta = _salida() / archivo
            informe = await asyncio.get_event_loop().run_in_executor(
                None, lambda: criticar(Image.open(ruta), referencias=referencias,
                                       para3d=para3d, ciclos=ciclos))
        except Exception as e:
            estado.update(terminado=True, error=str(e)[:300])
            return

        prompt_usado = grafo[nodo_texto]["inputs"].get("prompt", "")
        estado["historial"].append({
            "archivo": archivo,
            "puntuacion": informe.get("puntuacion"),
            "defectos": informe.get("defectos", []),
            "detalle": informe.get("detalle", []),
            "resumen": resumen(informe),
            "prompt": prompt_usado,
        })

        mejor = estado.get("mejor")
        if mejor is None or (informe.get("puntuacion") or 0) > (mejor.get("puntuacion") or 0):
            estado["mejor"] = estado["historial"][-1]
            sin_mejora = 0
        else:
            sin_mejora += 1

        if informe.get("apto"):
            break
        # Dos vueltas sin mejorar: se para para no gastar GPU de balde.
        if sin_mejora >= 2 or vuelta == int(intentos) - 1:
            break

        nuevo, negativo, cambios = corregir(
            prompt_usado, grafo[nodo_texto]["inputs"].get("negative_prompt", ""),
            informe, grafo[nodo_muestreo]["inputs"].get("seed", 0), referencias, para3d)
        if observaciones:
            # Lo que vio el usuario manda sobre lo que vio el critico, y se arrastra en
            # todas las vueltas: si no, la vuelta siguiente deshace lo que el pidio.
            nuevo_u, negativo_u, cambios_u, _, aviso_u = await asyncio.get_event_loop(
                ).run_in_executor(None, lambda: corregir_con_usuario(
                    Image.open(ruta), nuevo, negativo, observaciones, informe,
                    referencias, para3d))
            if aviso_u:
                _anotar(estado, "no se pudo aplicar tu observacion: " + aviso_u)
            else:
                nuevo, negativo = nuevo_u, negativo_u
                _anotar(estado, "con lo que dijiste: " + (cambios_u or "prompt reescrito"))
                cambios["quitar_referencia_2"] = bool(
                    referencias >= 2
                    and any(c in nuevo.lower() for c in CONDICIONES_CON_CUERPO))

        grafo[nodo_texto]["inputs"]["prompt"] = nuevo
        grafo[nodo_texto]["inputs"]["negative_prompt"] = negativo
        grafo[nodo_muestreo]["inputs"]["seed"] = cambios["seed"]
        if "steps" in cambios:
            grafo[nodo_muestreo]["inputs"]["steps"] = cambios["steps"]
        if cambios.get("quitar_referencia_2") and "images.image_2" in grafo[nodo_texto]["inputs"]:
            # Soltar la imagen a secas dejaria el prompt hablando de una referencia que ya
            # no esta ("same pose as the girl in the second image"), y entonces se pierde la
            # condicion. Antes de soltarla se le pide a la IA que la traduzca a palabras,
            # con las dos imagenes delante para que describa la pose que hay de verdad.
            nota = cambios["motivo_referencia"]
            try:
                en_palabras, aviso_ia = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: mejorar(nuevo, "3d" if para3d else "imagen", referencias=2, tiempo=240,
                                          imagenes=_rutas_referencias(grafo, nodo_texto)))
                if not aviso_ia and "second image" not in en_palabras.lower():
                    grafo[nodo_texto]["inputs"]["prompt"] = en_palabras
                    nota += " La condicion se ha reescrito con palabras."
                else:
                    nota += " No se pudo reescribir con palabras, puede perderse la condicion."
            except Exception as e:
                nota += f" No se pudo reescribir con palabras ({str(e)[:80]})."
            del grafo[nodo_texto]["inputs"]["images.image_2"]
            referencias = 1
            _anotar(estado, nota)

    estado["terminado"] = True


@rutas.post("/exo/estudio/bucle")
async def bucle(peticion):
    """Arranca el bucle de correccion y devuelve un id para seguirlo."""
    datos = await peticion.json()
    id_bucle = uuid.uuid4().hex[:12]
    _bucles[id_bucle] = {"intento": 0, "historial": [], "mejor": None, "terminado": False,
                         "error": "", "para3d": bool(datos.get("para3d"))}
    # 'para3d' decide con que criterio se revisa: con el puesto se exige lo que necesita
    # la conversion a pieza; sin el solo se buscan los fallos de cualquier imagen.
    # 'observaciones' es lo que el usuario ha visto mal en una imagen anterior: se tiene
    # en cuenta en cada correccion, no solo en la primera.
    asyncio.create_task(_correr_bucle(id_bucle, datos["grafo"], datos.get("intentos", 3),
                                      bool(datos.get("para3d")),
                                      int(datos.get("ciclos") or 2),
                                      str(datos.get("observaciones") or "")))
    return web.json_response({"id": id_bucle})


@rutas.get("/exo/estudio/bucle/{id_bucle}")
async def bucle_estado(peticion):
    estado = _bucles.get(peticion.match_info["id_bucle"])
    if estado is None:
        raise web.HTTPNotFound(text="ese bucle no existe")
    return web.json_response(estado)


@rutas.post("/exo/estudio/prompt")
async def escribir_prompt(peticion):
    """Convierte una idea corta en un prompt completo con la IA local.

    El modo lo decide la casilla 'pensada para pasar a 3D' del estudio: con ella puesta
    se imponen las reglas que necesita la conversion a modelo.
    """
    from .prompt_ia import mejorar

    datos = await peticion.json()
    # Las referencias se le adjuntan al modelo, que es multimodal: sin verlas se inventa
    # lo que hay en la segunda, y para una pose o una escena —que hay que describir con
    # palabras— inventarsela es justo el fallo que se quiere evitar.
    entrada = Path(folder_paths.get_input_directory())
    rutas = [entrada / n for n in (datos.get("imagenes_ref") or []) if n]
    rutas = [r for r in rutas if r.exists()]

    prompt, aviso = mejorar(
        datos.get("idea", ""),
        "3d" if datos.get("para3d") else "imagen",
        semilla=datos.get("semilla") or None,
        # Con referencias cargadas el prompt describe un cambio, no una escena entera.
        referencias=int(datos.get("referencias") or 0),
        imagenes=rutas,
        tiempo=240 if rutas else 120,
    )
    # Si con dos referencias el prompt no cita la segunda, es que lo pedido era una pose,
    # una accion o una sustitucion: la IA las redacta con palabras a proposito. En ese caso
    # dejar la referencia 2 cargada estropea el resultado, asi que se avisa.
    soltar = int(datos.get("referencias") or 0) >= 2 and "second image" not in prompt.lower()
    return web.json_response({"prompt": prompt, "aviso": aviso, "soltar_referencia_2": soltar})


@rutas.post("/exo/estudio/observacion")
async def observacion(peticion):
    """Reescribe el prompt con lo que el usuario dice que falla en una imagen generada.

    Es el modo de una sola pasada: se mira la imagen, se escribe lo que no cuadra y la IA
    traduce eso a cambios de prompt y de negativo. En el bucle, lo mismo se arrastra en
    todas las vueltas.
    """
    from .critica import corregir_con_usuario

    datos = await peticion.json()
    ruta = _salida() / str(datos.get("archivo") or "")
    if not ruta.exists():
        return web.json_response({"aviso": "no encuentro esa imagen"}, status=404)

    prompt, negativo, cambios, otra_semilla, aviso = await asyncio.get_event_loop(
        ).run_in_executor(None, lambda: corregir_con_usuario(
            Image.open(ruta), str(datos.get("prompt") or ""),
            str(datos.get("negativo") or ""), str(datos.get("observaciones") or ""),
            None, int(datos.get("referencias") or 0), bool(datos.get("para3d"))))
    return web.json_response({"prompt": prompt, "negativo": negativo, "cambios": cambios,
                              "cambiar_semilla": otra_semilla, "aviso": aviso})


@rutas.post("/exo/estudio/a_entrada")
async def a_entrada(peticion):
    """Copia la imagen a input/ para usarla en el flujo imagen -> 3D."""
    datos = await peticion.json()
    nombre = _nombre_seguro(datos.get("archivo"))
    destino = Path(folder_paths.get_input_directory()) / f"qwen_{nombre}"
    shutil.copy2(_salida() / nombre, destino)
    return web.json_response({"entrada": destino.name})
