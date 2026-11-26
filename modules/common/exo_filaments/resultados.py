"""API local de resultados y borrado de archivos con confirmacion del alcance."""
import asyncio
import contextlib
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
import folder_paths
from server import PromptServer

from .perfil import MODULOS
if "2d" in MODULOS:
    from . import estudio
else:
    estudio=None
if "3d" in MODULOS:
    from . import pieza
else:
    pieza=None
from .resultados_archivos import Catalogo

_catalogo=None
_lock=asyncio.Lock()
_observador=None
rutas=PromptServer.instance.routes


def catalogo():
    global _catalogo
    if _catalogo is None:
        _catalogo=Catalogo(folder_paths.get_output_directory(),folder_paths.get_input_directory(),
            Path(folder_paths.get_user_directory())/'default/exo_resultados/catalogo.json')
    return _catalogo


def actualizar():
    c=catalogo()
    antes=json.dumps(c.registros,sort_keys=True)
    for pid,historia in PromptServer.instance.prompt_queue.get_history(max_items=100).items():
        c.registrar_historia(pid,historia)
    c.explorar()
    if json.dumps(c.registros,sort_keys=True)!=antes:c.guardar()
    return c


def ocupado():
    running,pending=PromptServer.instance.prompt_queue.get_current_queue()
    return bool(running or pending or (estudio is not None and any(not b.get('terminado') for b in estudio._bucles.values()))
        or (pieza is not None and (any(not b.get('terminado') for b in pieza._trabajos.values()) or pieza._plan_lock.locked())))


def validar_peticion(request):
    origen=request.headers.get('Origin')
    if origen and urlsplit(origen).netloc.lower()!=request.host.lower():
        raise web.HTTPForbidden(text='Origen de borrado no permitido')
    if request.content_type!='application/json':raise web.HTTPUnsupportedMediaType()


@rutas.get('/exo/modulos')
async def modulos_instalados(_):
    return web.json_response({"modulos":list(MODULOS)})


@rutas.get('/exo/resultados')
async def listar_resultados(request):
    async with _lock:
        c=actualizar()
        return web.json_response({'resultados':c.listar()})


@rutas.post('/exo/resultados/preparar-borrado')
async def preparar_borrado(request):
    validar_peticion(request)
    datos=await request.json()
    async with _lock:
        if ocupado():return web.json_response({'error':'Espera a que terminen los trabajos antes de borrar'},status=409)
        try:
            c=actualizar()
            ident=datos.get('id') or c.buscar(str(datos.get('archivo','')))
            if not ident or ident not in c.registros:raise ValueError('No se encuentra el resultado')
            return web.json_response(c.plan(ident))
        except (ValueError,OSError) as exc:
            return web.json_response({'error':str(exc)},status=400)


def limpiar_historial(plan):
    c=catalogo();eliminados=set(plan['eliminados'])
    # Quitar tambien intentos fallidos o revisiones que solo leian un archivo borrado.
    for pid,h in PromptServer.instance.prompt_queue.get_history().items():
        refs=c.referencias(h.get('prompt',[None,None,{}])[2],existentes=False)
        if pid in plan['historial'] or refs&eliminados:
            PromptServer.instance.prompt_queue.delete_history_item(pid)
    fichero=Path(folder_paths.get_user_directory())/'default/exo_estudio/revisiones.json'
    if fichero.exists():
        revisiones=json.loads(fichero.read_text(encoding='utf-8'))
        for key in eliminados:
            if key.startswith('output:qwen21/'):
                revisiones.pop(Path(key.split(':',1)[1]).name,None)
        temporal=fichero.with_suffix('.tmp')
        temporal.write_text(json.dumps(revisiones,ensure_ascii=False),encoding='utf-8')
        temporal.replace(fichero)
    if estudio is not None:
        for p in list(estudio._cache):
            if not p.exists():estudio._cache.pop(p,None)
        for ident,estado in list(estudio._bucles.items()):
            if any('output:qwen21/'+a.get('archivo','') in eliminados for a in estado.get('historial',[])):
                estudio._bucles.pop(ident,None)
    if pieza is not None:
        for ident,estado in list(pieza._trabajos.items()):
            archivos={'output:'+a['ruta'].replace("\\","/") for a in estado.get('archivos',[])}
            if estado.get('prompt_id') in plan['historial'] or archivos&eliminados:
                pieza._trabajos.pop(ident,None);pieza._grafos_color.pop(ident,None)
    # Evitar que los nodos de guardado reutilicen salidas en cache ya eliminadas.
    PromptServer.instance.prompt_queue.set_flag('free_memory',True)
    PromptServer.instance.prompt_queue.set_flag('unload_models',False)


@rutas.post('/exo/resultados/borrar')
async def borrar_resultado(request):
    validar_peticion(request)
    datos=await request.json()
    async with _lock:
        if ocupado():return web.json_response({'error':'Hay trabajos activos; no se borro ningun archivo'},status=409)
        try:
            c=actualizar()
            ident=str(datos.get('id',''))
            if ident not in c.registros:raise ValueError('El resultado ya no existe')
            plan=c.borrar(ident,str(datos.get('token','')))
            limpiar_historial(plan)
            return web.json_response(plan)
        except (ValueError,OSError) as exc:
            return web.json_response({'error':str(exc)+'; actualiza la lista para comprobar los archivos restantes'},status=400)


@rutas.get('/exo/resultados.js')
async def script_resultados(_):
    return web.FileResponse(Path(__file__).parent/'js/resultados.js',headers={'Cache-Control':'no-store'})


async def observar():
    while True:
        try:
            async with _lock:actualizar()
        except (OSError,ValueError,KeyError) as exc:
            logging.error('Exo: no se pudo actualizar el catalogo de resultados: %s',exc)
        await asyncio.sleep(5)


async def iniciar(_):
    global _observador
    _observador=asyncio.create_task(observar())


async def detener(_):
    if _observador:
        _observador.cancel()
        with contextlib.suppress(asyncio.CancelledError):await _observador


PromptServer.instance.app.on_startup.append(iniciar)
PromptServer.instance.app.on_cleanup.append(detener)
