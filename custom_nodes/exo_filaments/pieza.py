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
PALETA_POR_DEFECTO = ""

_grafos_color = {}
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
        pasos_color=int(opciones.get("pasos_textura",24))
        semilla_color=int(opciones.get("semilla_textura",semilla+1))
        if not 12<=pasos_color<=40 or not 0<=semilla_color<2**64:
            raise ValueError("Parametros de textura fuera de rango")
        grafo["66"]["inputs"].update(seed=semilla_color,steps=pasos_color)
        grafo["73"]["class_type"] = "ExoTransferirColor"
        grafo["73"]["inputs"]["referencia"] = ["37", 0]
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

    resolucion = int(opciones.get("resolucion_reparacion", 384))
    if not 64 <= resolucion <= 768:
        raise ValueError("Resolucion de reparacion invalida")
    grafo["62"]["inputs"].update(resolucion=resolucion, suavizar_forma=2)
    if color and bool(opciones.get("color_frontal", False)):
        grafo["76"] = {"class_type": "MaskToImage", "inputs": {"mask": ["91", 0]}}
        grafo["77"] = {"class_type": "ImageCropToMask", "inputs": {
            "images": ["76", 0], "masks": ["91", 0], "width": 1024, "height": 1024,
            "pad_factor": 1.05, "grow_mask": 0, "background": "#000000"}}
        grafo["78"] = {"class_type": "ImageToMask", "inputs": {"image": ["77", 0], "channel": "red"}}
        grafo["79"] = {"class_type": "ExoProyectarColorFrontal", "inputs": {
            "mesh": ["73", 0], "imagen": ["92", 0], "mascara": ["78", 0],
            "completar_oscuras": bool(opciones.get("completar_oscuras", True))}}
        origen = ["79", 0]
        grafo["74"]["inputs"]["mesh"] = origen
        # La vista previa coloreada usa el GLB por vertice corregido.
        for k in ("68", "69", "70", "71", "72"):
            grafo.pop(k, None)
    paleta = str(opciones.get("paleta") or "").strip()
    if color and paleta:
        grafo["200"] = {"class_type": "ExoPaletaFilamentos", "inputs": {
            "mesh": origen, "paleta": paleta, "colores": int(opciones.get("plazas", 4)),
            "peso_luz": .25, "min_mancha": .01, "suavizar_bordes": 2}}
        origen = ["200", 0]

    pared = float(opciones.get("pared") or 1.2)
    grafo["201"] = {"class_type": "ExoInformeImpresion", "inputs": {
        "mesh": origen, "altura_mm": float(opciones.get("altura") or 80.0),
        "material": str(opciones.get("material") or "PLA"),
        "relleno": float(opciones.get("relleno") or 15.0), "pared_mm": pared}}
    grafo["202"] = {"class_type": "ExoRevisarGrosor", "inputs": {
        "mesh": ["201", 0], "grosor_min_mm": pared, "aviso_pct": 5.0, "muestras": 4000}}
    # El presupuesto va enchufado al peso que calcula el informe, no lo recalcula.
    grafo["207"] = {"class_type": "ExoPresupuesto", "inputs": {
        "peso_g": ["201", 2], "soportes_pct": float(opciones.get("soportes_pct") or 0.0)}}
    grafo["206"] = {"class_type": "ExoRevisarImprimible", "inputs": {
        "mesh": ["202", 0],
        "cama_x_mm": float(opciones.get("cama_x") or 350.0),
        "cama_y_mm": float(opciones.get("cama_y") or 350.0),
        "cama_z_mm": float(opciones.get("cama_z") or 350.0),
        "angulo_voladizo": float(opciones.get("angulo_voladizo") or 45.0),
        "poner_de_pie": True}}
    grafo["204"] = {"class_type": "ExoRevisarPieza", "inputs": {
        "mesh": ["202", 0], "descripcion": str(opciones.get("descripcion") or ""),
        "resolucion_vista": 448, "imagen_referencia": ["56", 0]}}
    if not color:
        grafo["204"]["inputs"].pop("imagen_referencia",None)
    # Las cuatro vistas se guardan para poder mirarlas en el movil.
    grafo["205"] = {"class_type": "SaveImage", "inputs": {
        "images": ["204", 0], "filename_prefix": CARPETA_SALIDA + "/vistas"}}
    grafo["203"] = {"class_type": "ExoGuardarImpresion", "inputs": {
        "mesh": ["202", 0], "nombre": CARPETA_SALIDA + "/pieza",
        "guardar_obj": color, "guardar_3mf_experimental": color, "poner_de_pie": True,
        "max_colores": int(opciones.get("plazas",4)),
        "paleta_impresion": str(opciones.get("paleta") or "")}}
    grafo["208"] = {"class_type": "ExoPlanImpresion", "inputs": {
        "mesh": ["201", 0], "capa_mm": float(opciones.get("capa_mm", 0.2)),
        "sistema": str(opciones.get("sistema", "cfs")), "plazas": int(opciones.get("plazas",4)), "material": str(opciones.get("material", "PLA")),
        "cama_x": float(opciones.get("cama_x",350)), "cama_y": float(opciones.get("cama_y",350)),
        "cama_z": float(opciones.get("cama_z",350))}}
    return grafo


ETIQUETAS = {"201": "Informe de impresion", "202": "Grosor de paredes",
             "208": "Plan de impresion", "206": "Se puede imprimir", "207": "Presupuesto",
             "204": "Revision de la pieza", "203": "Archivos guardados"}


async def _convertir(id_trabajo, grafo):
    """Encola el grafo y va recogiendo informes, vistas y archivos."""
    import aiohttp

    estado = _trabajos[id_trabajo]
    _grafos_color[id_trabajo] = grafo
    try:
        async with aiohttp.ClientSession() as sesion:
            async with sesion.post("http://localhost:8188/prompt",
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
                async with sesion.get("http://localhost:8188/history/" + pid) as r:
                    historial = await r.json()
                if pid not in historial:
                    continue
                situacion = historial[pid].get("status", {})
                if situacion.get("status_str") != "success":
                    raise RuntimeError(json.dumps(situacion.get("messages", []))[:400])
                salidas=historial[pid].get("outputs", {})
                revision=(salidas.get("204",{}).get("revision_pieza") or [{}])[0]
                color_mal=any(revision.get("revision_color",{}).get(k) is True for k in ("color_no_coincide","textura_corrupta")) if isinstance(revision.get("revision_color"),dict) else False
                intento=int(estado.get("reintentos_color",0))
                if color_mal and "66" in grafo and intento<2:
                    import copy
                    nuevo=copy.deepcopy(grafo)
                    nuevo["66"]["inputs"]["seed"]=(int(nuevo["66"]["inputs"]["seed"])+1)%(2**64)
                    nuevo.pop("82",None) # La geometria ya existe; no guardar otra copia enorme.
                    estado["reintentos_color"]=intento+1
                    estado.setdefault("revision_color_intentos",[]).append(revision)
                    await _convertir(id_trabajo,nuevo)
                    return
                _recoger(estado, salidas)
                estado["color_requiere_revision"]=color_mal
                qc=revision.get("revision_color")
                estado["color_sin_verificar"]="66" in grafo and (not isinstance(qc,dict) or any(not isinstance(qc.get(k),bool) for k in ("color_no_coincide","textura_corrupta")))
                estado["terminado"] = True
                return
            raise RuntimeError("se agoto el tiempo; mira la cola de ComfyUI")
    except Exception as e:
        estado.update(terminado=True, error=str(e)[:400])


def _recoger(estado, salidas):
    """Saca de la respuesta los informes en texto, las vistas y los archivos."""
    for nodo, salida in salidas.items():
        for relativa in salida.get("plan_archivo", []):
            estado["archivos"].append({"nombre":Path(relativa).name,"ruta":relativa})
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


@rutas.post("/exo/pieza/paleta")
async def analizar_paleta(peticion):
    import aiohttp
    datos=await peticion.json()
    nombre=str(datos.get("imagen") or "")
    if not nombre or Path(nombre).name!=nombre or "/" in nombre or "\\" in nombre:
        return web.json_response({"error":"Elegir una imagen de la galeria"},status=400)
    try:
        plazas=int(datos.get("plazas",4))
        if not 1<=plazas<=16:raise ValueError()
    except (TypeError,ValueError):
        return web.json_response({"error":"Elegir entre 1 y 16 filamentos"},status=400)
    entrada=Path(folder_paths.get_input_directory()).resolve()
    imagen=(entrada/nombre).resolve()
    if not imagen.is_relative_to(entrada):
        return web.json_response({"error":"Imagen fuera de input"},status=400)
    if not imagen.is_file():
        origen=(_salida()/"qwen21"/nombre).resolve()
        if not origen.is_relative_to((_salida()/"qwen21").resolve()) or not origen.is_file():
            return web.json_response({"error":"No encuentro esa imagen"},status=404)
        imagen=entrada/("qwen_"+nombre)
        imagen.write_bytes(origen.read_bytes())
    grafo={"56":{"class_type":"LoadImage","inputs":{"image":imagen.name}},
        "90":{"class_type":"LoadBackgroundRemovalModel","inputs":{"bg_removal_name":"birefnet.safetensors"}},
        "91":{"class_type":"RemoveBackground","inputs":{"bg_removal_model":["90",0],"image":["56",0]}},
        "95":{"class_type":"ExoSegmentarColoresImagen","inputs":{"imagen":["56",0],"mascara":["91",0],"plazas":plazas}}}
    async with aiohttp.ClientSession() as sesion:
        async with sesion.post("http://localhost:8188/prompt",json={"prompt":grafo}) as r:
            respuesta=await r.json()
    if respuesta.get("node_errors") or not respuesta.get("prompt_id"):
        return web.json_response({"error":"No se pudo encolar el analisis de colores","detalle":respuesta},status=400)
    return web.json_response({"id":respuesta["prompt_id"]})


@rutas.get("/exo/pieza/paleta/{id}")
async def estado_paleta(peticion):
    import aiohttp
    try:pid=str(uuid.UUID(peticion.match_info["id"]))
    except ValueError:return web.json_response({"error":"Analisis invalido"},status=400)
    async with aiohttp.ClientSession() as sesion:
        async with sesion.get("http://localhost:8188/history/"+pid) as r:historial=await r.json()
    if pid not in historial:return web.json_response({"terminado":False})
    trabajo=historial[pid]
    datos=trabajo.get("outputs",{}).get("95",{}).get("segmentacion",[])
    if trabajo.get("status",{}).get("status_str")!="success" or not datos:
        return web.json_response({"terminado":True,"error":"Fallo la segmentacion del sujeto; revisa la cola de ComfyUI"})
    return web.json_response({"terminado":True,**datos[0]})


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


@rutas.post("/exo/pieza/retexturizar")
async def retexturizar(peticion):
    import copy
    datos=await peticion.json(); anterior=str(datos.get("id") or "")
    estado=_trabajos.get(anterior); base=_grafos_color.get(anterior)
    if not estado or not base or "66" not in base:
        return web.json_response({"error":"No hay un trabajo con textura disponible en esta sesion"},status=404)
    if not estado.get("terminado") or any(not t.get("terminado") for t in _trabajos.values()):
        return web.json_response({"error":"Espera a que termine el trabajo actual"},status=409)
    g=copy.deepcopy(base);g.pop("82",None)
    g["66"]["inputs"]["seed"]=(int(g["66"]["inputs"]["seed"])+1)%(2**64)
    nuevo=uuid.uuid4().hex[:12]
    _trabajos[nuevo]={"terminado":False,"error":"","informes":[],"vistas":[],"archivos":[],
        "imagen":estado["imagen"],"inicio":time.time(),"reintentos_color":0}
    asyncio.create_task(_convertir(nuevo,g))
    return web.json_response({"id":nuevo})


@rutas.get("/exo/pieza/estado/{id}")
async def estado_pieza(peticion):
    estado = _trabajos.get(peticion.match_info["id"])
    if estado is None:
        return web.json_response({"error": "no existe ese trabajo"}, status=404)
    return web.json_response({**estado, "retexturizable": peticion.match_info["id"] in _grafos_color and "66" in _grafos_color[peticion.match_info["id"]], "segundos": round(time.time() - estado["inicio"])})


@rutas.post("/exo/pieza/encargo")
async def guardar_encargo(peticion):
    """Recoge todo lo de un trabajo terminado en una carpeta con el nombre del cliente.

    Hasta ahora los archivos de cada pieza se quedaban mezclados en output/3d/exo con los
    de todas las demas. Aqui se copian a encargos\\<fecha>-<nombre>, junto con los
    informes y el presupuesto, que es lo que hay que tener a mano cuando el cliente
    pregunta por su pedido tres semanas despues.
    """
    import datetime
    import re
    import shutil

    datos = await peticion.json()
    estado = _trabajos.get(str(datos.get("id") or ""))
    if estado is None:
        return web.json_response({"error": "no existe ese trabajo"}, status=404)
    if not estado.get("terminado") or estado.get("error"):
        return web.json_response({"error": "el trabajo no ha terminado bien"}, status=400)

    nombre = re.sub(r"[^\w\s-]", "", str(datos.get("nombre") or "sin nombre")).strip()[:60]
    nombre = re.sub(r"\s+", "_", nombre) or "sin_nombre"
    from .archivos import reunir
    base = _salida().resolve()
    try:
        fuentes = reunir([base / a["ruta"] for a in estado.get("archivos", [])], base)
    except (ValueError, OSError) as exc:
        return web.json_response({"error": str(exc)}, status=400)
    # mkdir exclusivo evita colisiones incluso con peticiones simultaneas.
    encargos = RAIZ / "encargos"
    encargos.mkdir(parents=True, exist_ok=True)
    while True:
        carpeta = encargos / ("%s-%s-%s" % (datetime.date.today().isoformat(), nombre, uuid.uuid4().hex))
        try:
            carpeta.mkdir(exist_ok=False)
            break
        except FileExistsError:
            continue
    copiados = []
    for origen in fuentes:
        relativa = origen.relative_to(base)
        destino = carpeta / "archivos" / relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)
        copiados.append((Path("archivos") / relativa).as_posix())
    for vista in estado.get("vistas", []):
        origen = _salida() / vista.get("subcarpeta", "") / vista["archivo"]
        if origen.exists():
            shutil.copy2(origen, carpeta / ("vistas_" + origen.name))
            copiados.append("vistas_" + origen.name)
    origen = Path(folder_paths.get_input_directory()) / estado.get("imagen", "")
    if origen.is_file():
        shutil.copy2(origen, carpeta / ("origen" + origen.suffix))
        copiados.append("origen" + origen.suffix)

    partes = ["ENCARGO: %s" % nombre, "fecha: %s" % datetime.date.today().isoformat(),
              "imagen de partida: %s" % estado.get("imagen", ""), ""]
    for informe in estado.get("informes", []):
        partes += ["== %s ==" % informe["titulo"], informe["texto"], ""]
    (carpeta / "informe.txt").write_text("\n".join(partes), encoding="utf-8")
    copiados.append("informe.txt")

    return web.json_response({"carpeta": str(carpeta), "archivos": copiados})


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
    if destino.suffix.lower() not in (".stl", ".obj", ".3mf", ".glb", ".mtl", ".png", ".txt", ".json"):
        return web.json_response({"error": "tipo de archivo no permitido"}, status=403)
    return web.FileResponse(destino, headers={
        "Content-Disposition": 'attachment; filename="%s"' % destino.name})


_plan_lock = asyncio.Lock()

@rutas.get("/exo/pieza/modelos-plan")
async def modelos_plan(_):
    base = _salida().resolve()
    modelos = sorted((base / CARPETA_SALIDA).rglob("*.obj"), key=lambda p:p.stat().st_mtime, reverse=True)
    return web.json_response({"modelos":[{"ruta":p.relative_to(base).as_posix(),"nombre":p.name} for p in modelos[:40]]})

@rutas.post("/exo/pieza/plan")
async def plan_existente(peticion):
    from .plan_impresion import leer_obj, analizar, resumen
    datos = await peticion.json()
    base = _salida().resolve()
    ruta = (base / str(datos.get("ruta", ""))).resolve()
    if not ruta.is_relative_to(base / CARPETA_SALIDA) or ruta.suffix.lower() != ".obj" or not ruta.is_file():
        return web.json_response({"error":"Modelo no permitido"},status=403)
    if _plan_lock.locked():
        return web.json_response({"error":"Ya hay un analisis en curso; espera a que termine"},status=409)
    try:
        async with _plan_lock:
            def calcular():
                v,f,c=leer_obj(ruta)
                return analizar(v,f,c,float(datos.get("capa_mm",0.2)),int(datos.get("plazas",4)),
                    str(datos.get("sistema","cfs")),
                    (float(datos.get("cama_x",350)),float(datos.get("cama_y",350)),float(datos.get("cama_z",350))),str(datos.get("material","PLA")))
            plan=await asyncio.to_thread(calcular)
        return web.json_response({"plan":plan,"texto":resumen(plan)})
    except (ValueError, OSError, TypeError) as exc:
        return web.json_response({"error":str(exc)},status=400)


@rutas.post("/exo/pieza/corte-vista")
async def corte_vista(peticion):
    from .plan_impresion import leer_obj
    import numpy as np
    datos=await peticion.json();base=_salida().resolve()
    ruta=(base/str(datos.get("ruta",""))).resolve()
    if not ruta.is_relative_to(base/CARPETA_SALIDA) or ruta.suffix.lower()!=".obj" or not ruta.is_file():
        return web.json_response({"error":"Modelo no permitido"},status=403)
    if _plan_lock.locked():return web.json_response({"error":"Espera a que termine el analisis"},status=409)
    try:
        async with _plan_lock:
            v,f,c=await asyncio.to_thread(leer_obj,ruta)
        muestra=np.arange(0,len(v),max(1,int(np.ceil(len(v)/5000))))
        return web.json_response({"min":v.min(axis=0).tolist(),"max":v.max(axis=0).tolist(),
            "puntos":v[muestra].round(3).tolist(),"colores":None if c is None else c[muestra].round(3).tolist()})
    except (ValueError,OSError) as exc:return web.json_response({"error":str(exc)},status=400)


@rutas.post("/exo/pieza/cortar")
async def separar_pieza(peticion):
    datos=await peticion.json();base=_salida().resolve();ruta=(base/str(datos.get("ruta",""))).resolve()
    if not ruta.is_relative_to(base/CARPETA_SALIDA) or ruta.suffix.lower()!=".obj" or not ruta.is_file():
        return web.json_response({"error":"Modelo no permitido"},status=403)
    eje=str(datos.get("eje","y"))
    try:
        porcentaje=float(datos.get("porcentaje",50))
        if eje not in ("x","y","z") or not 1<=porcentaje<=99:raise ValueError("Corte invalido")
    except (ValueError,TypeError):return web.json_response({"error":"Corte invalido"},status=400)
    if _plan_lock.locked():return web.json_response({"error":"Ya hay un analisis o corte en curso"},status=409)
    async with _plan_lock:
        identificador=uuid.uuid4().hex
        relativa=Path(CARPETA_SALIDA)/("corte_"+identificador)
        destino=base/relativa
        proc=await asyncio.create_subprocess_exec(sys.executable,"-B",str(Path(__file__).parent/"separacion.py"),
            str(ruta),str(destino),eje,str(porcentaje),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            out,err=await asyncio.wait_for(proc.communicate(),timeout=120)
        except asyncio.TimeoutError:
            proc.kill();await proc.communicate()
            return web.json_response({"error":"El corte excedio 120 segundos; el modelo original se conserva"},status=408)
        try:resultado=json.loads(out.decode('utf-8').strip())
        except (ValueError,UnicodeError):return web.json_response({"error":"Fallo del motor de corte; revisar dependencias"},status=500)
        if proc.returncode!=0 or resultado.get("error"):
            return web.json_response({"error":resultado.get("error","Fallo de corte")},status=400)
        archivos=[{"nombre":n,"ruta":(relativa/n).as_posix()} for n in resultado["archivos"]]
        _trabajos[identificador]={"terminado":True,"error":"","informes":[{"nodo":"corte","titulo":"Corte plano","texto":json.dumps(resultado['informe'],ensure_ascii=False,indent=2)}],
            "vistas":[],"archivos":archivos,"imagen":"","inicio":time.time()}
        return web.json_response({"id":identificador,"archivos":archivos,"informe":resultado['informe']})
