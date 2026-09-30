"""Convertir una imagen en pieza imprimible, desde el movil.

El grafo de ComfyUI no se puede manejar con el dedo: nodos diminutos, cables y zoom. Esta
pagina hace lo mismo que el flujo "Exo - imagen a pieza imprimible" pero con cuatro
controles, y devuelve lo que hace falta para decidir: los informes, las cuatro vistas de la
pieza y los archivos para el laminador.

  http://<la IP de este PC>:8188/exo/pieza

El grafo se arma aqui, reutilizando el constructor de scripts/generar_3d.py para que no haya
dos versiones del mismo flujo que se separen con el tiempo.
"""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

from aiohttp import web

import folder_paths
from server import PromptServer

RAIZ = Path(r"D:\AI3D")
PAGINA = Path(__file__).parent / "pieza" / "pieza.html"
CARPETA_SALIDA = "3d/exo"          # dentro de output/
MATERIALES = ("PLA", "PETG", "ABS", "TPU", "ASA")
PALETA_POR_DEFECTO = "#1a1a1a,#f2f2f2,#8a8d8c,#ffd500"

_trabajos = {}   # id -> estado de una conversion en curso


def _constructor():
    """El constructor de grafos vive en scripts/: se importa, no se copia."""
    ruta = str(RAIZ / "scripts")
    if ruta not in sys.path:
        sys.path.insert(0, ruta)
    from generar_3d import workflow
    return workflow


def _salida():
    return Path(folder_paths.get_output_directory())


def construir(imagen, opciones):
    """Grafo completo: imagen -> malla -> solidificada -> informes -> archivos.

    Con color se usa la rama de textura de TRELLIS.2, que ademas es la que trae la
    solidificacion; sin color hay que anadirla a mano, porque la malla en bruto del
    generador no es imprimible (cascara hueca, agujeros).
    """
    color = bool(opciones.get("color", True))
    semilla = int(opciones.get("semilla") or 42)
    grafo = _constructor()("trellis2", imagen, CARPETA_SALIDA + "/malla", 20, 7.5, 0,
                           semilla, True, "#FFFFFF", color, 2048)

    if color:
        origen = ["73", 0]          # PaintMesh: la malla limpia con color por vertice
    else:
        # Mismos valores que la rama de textura: lo unico que sobra ahi es el color.
        grafo["61"] = {"class_type": "GetMeshInfo", "inputs": {"mesh": ["37", 0]}}
        grafo["62"] = {"class_type": "ExoSolidificar", "inputs": {
            "mesh": ["61", 0], "resolucion": 320, "cerrar_grietas": 1, "suavizar_forma": 5}}
        grafo["63"] = {"class_type": "DecimateMesh", "inputs": {
            "mesh": ["62", 0], "target_face_count": 700000, "placement_mode": "midpoint"}}
        grafo["64"] = {"class_type": "MeshSmoothNormals", "inputs": {
            "mesh": ["63", 0], "crease_angle": 180.0}}
        origen = ["64", 0]

    if color and opciones.get("paleta"):
        grafo["200"] = {"class_type": "ExoPaletaFilamentos", "inputs": {
            "mesh": origen, "paleta": str(opciones["paleta"]),
            "colores": int(opciones.get("colores") or 4),
            "peso_luz": 0.25, "min_mancha": 0.3, "suavizar_bordes": 3}}
        origen = ["200", 0]

    pared = float(opciones.get("pared") or 1.2)
    grafo["201"] = {"class_type": "ExoInformeImpresion", "inputs": {
        "mesh": origen, "altura_mm": float(opciones.get("altura") or 80.0),
        "material": str(opciones.get("material") or "PLA"),
        "relleno": float(opciones.get("relleno") or 15.0), "pared_mm": pared}}
    grafo["202"] = {"class_type": "ExoRevisarGrosor", "inputs": {
        "mesh": ["201", 0], "grosor_min_mm": pared, "aviso_pct": 5.0, "muestras": 4000}}
    grafo["206"] = {"class_type": "ExoRevisarImprimible", "inputs": {
        "mesh": ["202", 0],
        "cama_x_mm": float(opciones.get("cama_x") or 350.0),
        "cama_y_mm": float(opciones.get("cama_y") or 350.0),
        "cama_z_mm": float(opciones.get("cama_z") or 350.0),
        "angulo_voladizo": float(opciones.get("angulo_voladizo") or 45.0),
        "poner_de_pie": True}}
    grafo["204"] = {"class_type": "ExoRevisarPieza", "inputs": {
        "mesh": ["202", 0], "descripcion": str(opciones.get("descripcion") or ""),
        "resolucion_vista": 448}}
    # Las cuatro vistas se guardan para poder mirarlas en el movil.
    grafo["205"] = {"class_type": "SaveImage", "inputs": {
        "images": ["204", 0], "filename_prefix": CARPETA_SALIDA + "/vistas"}}
    grafo["203"] = {"class_type": "ExoGuardarImpresion", "inputs": {
        "mesh": ["202", 0], "nombre": CARPETA_SALIDA + "/pieza",
        "guardar_obj": color, "poner_de_pie": True}}
    return grafo


ETIQUETAS = {"201": "Informe de impresion", "202": "Grosor de paredes",
             "206": "Se puede imprimir", "204": "Revision de la pieza",
             "203": "Archivos guardados"}


async def _convertir(id_trabajo, grafo):
    """Encola el grafo y va recogiendo informes, vistas y archivos."""
    import aiohttp

    estado = _trabajos[id_trabajo]
    try:
        async with aiohttp.ClientSession() as sesion:
            async with sesion.post("http://127.0.0.1:8188/prompt",
                                   json={"prompt": grafo}) as r:
                respuesta = await r.json()
            if respuesta.get("node_errors"):
                raise RuntimeError(json.dumps(respuesta["node_errors"])[:400])
            pid = respuesta["prompt_id"]
            estado["prompt_id"] = pid

            # Una pieza con color son varios minutos: media hora de margen y a mirar cada
            # tres segundos, que es mas que suficiente para una barra de progreso.
            limite = time.time() + 1800
            while time.time() < limite:
                await asyncio.sleep(3)
                async with sesion.get("http://127.0.0.1:8188/history/" + pid) as r:
                    historial = await r.json()
                if pid not in historial:
                    continue
                situacion = historial[pid].get("status", {})
                if situacion.get("status_str") != "success":
                    raise RuntimeError(json.dumps(situacion.get("messages", []))[:400])
                _recoger(estado, historial[pid].get("outputs", {}))
                estado["terminado"] = True
                return
            raise RuntimeError("se agoto el tiempo; mira la cola de ComfyUI")
    except Exception as e:
        estado.update(terminado=True, error=str(e)[:400])


def _recoger(estado, salidas):
    """Saca de la respuesta los informes en texto, las vistas y los archivos."""
    for nodo, salida in salidas.items():
        textos = [t for t in (salida.get("text") or []) if str(t).strip()]
        if textos:
            estado["informes"].append({"nodo": nodo,
                                       "titulo": ETIQUETAS.get(nodo, "Informe " + nodo),
                                       "texto": "\n".join(str(t) for t in textos)})
        for imagen in (salida.get("images") or []):
            estado["vistas"].append({"archivo": imagen.get("filename"),
                                     "subcarpeta": imagen.get("subfolder", "")})
    # Los archivos para el laminador los escribe el nodo de guardado, que devuelve sus
    # rutas como texto; se convierten en algo descargable desde el movil.
    for informe in estado["informes"]:
        if informe["nodo"] != "203":
            continue
        for linea in informe["texto"].splitlines():
            ruta = Path(linea.strip())
            if not ruta.name:
                continue
            try:
                relativa = ruta.relative_to(_salida())
            except ValueError:
                relativa = Path(ruta.name)
            estado["archivos"].append({"nombre": ruta.name, "ruta": relativa.as_posix()})
    estado["informes"] = [i for i in estado["informes"] if i["nodo"] != "203"]


rutas = PromptServer.instance.routes


@rutas.get("/exo/pieza")
async def pagina_pieza(_):
    return web.FileResponse(PAGINA, headers={"Cache-Control": "no-store"})


@rutas.get("/exo/pieza/imagenes")
async def imagenes_disponibles(_):
    """Lo generado en el Estudio y lo que haya en input/, que es de donde se parte."""
    fichas = []
    estudio = _salida() / "qwen21"
    if estudio.exists():
        for ruta in estudio.glob("*.png"):
            fichas.append({"nombre": ruta.name, "origen": "estudio",
                           "fecha": ruta.stat().st_mtime,
                           "url": "/view?filename=%s&subfolder=qwen21&type=output&preview=webp;70"
                                  % ruta.name})
    entrada = Path(folder_paths.get_input_directory())
    for patron in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for ruta in entrada.glob(patron):
            fichas.append({"nombre": ruta.name, "origen": "entrada",
                           "fecha": ruta.stat().st_mtime,
                           "url": "/view?filename=%s&type=input&preview=webp;70" % ruta.name})
    fichas.sort(key=lambda f: f["fecha"], reverse=True)
    return web.json_response({"imagenes": fichas[:200], "materiales": list(MATERIALES),
                              "paleta": PALETA_POR_DEFECTO})


@rutas.post("/exo/pieza/convertir")
async def convertir(peticion):
    datos = await peticion.json()
    imagen = str(datos.get("imagen") or "").strip()
    if not imagen:
        return web.json_response({"error": "falta la imagen"}, status=400)

    # La imagen tiene que estar en input/ para que LoadImage la encuentre.
    entrada = Path(folder_paths.get_input_directory())
    if not (entrada / imagen).exists():
        origen = _salida() / "qwen21" / imagen
        if not origen.exists():
            return web.json_response({"error": "no encuentro esa imagen"}, status=404)
        destino = entrada / ("qwen_" + imagen)
        if not destino.exists():
            destino.write_bytes(origen.read_bytes())
        imagen = destino.name

    id_trabajo = uuid.uuid4().hex[:12]
    _trabajos[id_trabajo] = {"terminado": False, "error": "", "informes": [], "vistas": [],
                             "archivos": [], "imagen": imagen, "inicio": time.time()}
    try:
        grafo = construir(imagen, datos)
    except Exception as e:
        _trabajos[id_trabajo].update(terminado=True, error=str(e)[:300])
        return web.json_response({"id": id_trabajo, "error": str(e)[:300]}, status=400)

    asyncio.create_task(_convertir(id_trabajo, grafo))
    return web.json_response({"id": id_trabajo})


@rutas.get("/exo/pieza/estado/{id}")
async def estado_pieza(peticion):
    estado = _trabajos.get(peticion.match_info["id"])
    if estado is None:
        return web.json_response({"error": "no existe ese trabajo"}, status=404)
    return web.json_response({**estado, "segundos": round(time.time() - estado["inicio"])})


@rutas.get("/exo/pieza/descargar")
async def descargar(peticion):
    """Sirve un STL o un OBJ de la carpeta de salida. Solo de ahi dentro."""
    relativa = (peticion.query.get("ruta") or "").strip()
    if not relativa:
        return web.json_response({"error": "falta la ruta"}, status=400)
    base = _salida().resolve()
    destino = (base / relativa).resolve()
    # Sin esta comprobacion, un "../.." serviria cualquier archivo del disco a quien
    # este en la red.
    if base not in destino.parents or not destino.is_file():
        return web.json_response({"error": "ruta no permitida"}, status=403)
    if destino.suffix.lower() not in (".stl", ".obj", ".glb", ".mtl", ".png", ".txt", ".json"):
        return web.json_response({"error": "tipo de archivo no permitido"}, status=403)
    return web.FileResponse(destino, headers={
        "Content-Disposition": 'attachment; filename="%s"' % destino.name})
