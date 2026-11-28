import asyncio
import hmac
import io
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from PIL import Image,ImageOps,UnidentifiedImageError

from .store import Store,ErrorPortal
from .queue import retry
from .private_access import PRIVATE,PrivateAccess,private_boundary

STORE=web.AppKey('store',Store)
COOKIE=web.AppKey('secure_cookie',bool)
ORIGIN=web.AppKey('origin',str)
FLOWS=web.AppKey('flows',tuple)
PUBLIC=Path(__file__).parent/'web'
SESSION_COOKIE='exo_session'
MAX_UPLOAD=12*1024*1024


@web.middleware
async def errors(request,handler):
    try:response=await handler(request)
    except ErrorPortal as exc:response=web.json_response({'error':str(exc)},status=exc.status)
    except (json.JSONDecodeError,UnicodeError,ValueError):response=web.json_response({'error':'Solicitud invalida'},status=400)
    except web.HTTPException as exc:response=web.json_response({'error':exc.reason},status=exc.status)
    except OSError:
        logging.exception('Portal: fallo de almacenamiento')
        response=web.json_response({'error':'No se pudo completar la operacion de almacenamiento; vuelve a consultar el estado'},status=503)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


def same_origin(request):
    value=request.headers.get('Origin')
    if not value:return
    expected=request.app[ORIGIN]
    parsed=urlsplit(value)
    if expected:
        if value.rstrip('/')!=expected.rstrip('/'):raise ErrorPortal(403,'Origen no permitido')
    elif parsed.scheme not in ('https','http') or parsed.netloc.lower()!=request.host.lower():
        raise ErrorPortal(403,'Origen no permitido')


async def body(request):
    if request.content_type!='application/json':raise ErrorPortal(415,'Se requiere JSON')
    data=await request.json()
    if not isinstance(data,dict):raise ErrorPortal(400,'Se requiere un objeto JSON')
    return data


@web.middleware
async def auth(request,handler):
    if not request.path.startswith('/api/') or request.path=='/api/login':return await handler(request)
    user=request.app[STORE].session(request.cookies.get(SESSION_COOKIE,''))
    if not user:raise ErrorPortal(401,'Inicia sesion')
    request['user']=user
    if request.method not in ('GET','HEAD','OPTIONS'):
        same_origin(request)
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),user['csrf']):
            raise ErrorPortal(403,'Token de formulario invalido')
    return await handler(request)


def admin(request):
    if request['user']['role']!='administrador':raise ErrorPortal(403,'Se requiere administrador')


async def index(_):return web.FileResponse(PUBLIC/'index.html')
async def asset(request):
    name=request.match_info['name']
    if name not in ('app.js','style.css'):raise ErrorPortal(404,'Archivo no encontrado')
    return web.FileResponse(PUBLIC/name)


async def login(request):
    same_origin(request);data=await body(request)
    token,user=await asyncio.to_thread(request.app[STORE].login,data.get('usuario',''),data.get('password',''),request.remote or 'local')
    response=web.json_response(user)
    response.set_cookie(SESSION_COOKIE,token,httponly=True,secure=request.app[COOKIE],samesite='Strict',
        max_age=request.app[STORE].session_seconds,path='/')
    return response


async def logout(request):
    request.app[STORE].logout(request.cookies.get(SESSION_COOKIE,''))
    response=web.json_response({'ok':True});response.del_cookie(SESSION_COOKIE,path='/');return response
async def me(request):return web.json_response(request['user'])


async def users(request):
    admin(request)
    if request.method=='GET':return web.json_response({'usuarios':request.app[STORE].users()})
    data=await body(request)
    user=await asyncio.to_thread(request.app[STORE].create_user,data.get('usuario'),data.get('password'),data.get('rol','cliente'))
    return web.json_response(user,status=201)


async def set_user(request):
    admin(request);data=await body(request)
    request.app[STORE].set_active(request.match_info['id'],data.get('activo'))
    return web.json_response({'ok':True})


async def upload(request):
    if request.content_type!='multipart/form-data':raise ErrorPortal(415,'Se requiere una imagen adjunta')
    reader=await request.multipart();part=await reader.next()
    if part is None or part.name!='imagen':raise ErrorPortal(400,'Falta la imagen')
    data=bytearray()
    while True:
        chunk=await part.read_chunk()
        if not chunk:break
        data.extend(chunk)
        if len(data)>MAX_UPLOAD:raise ErrorPortal(413,'La imagen supera el limite de 12 MB')
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width*image.height>16_000_000:raise ErrorPortal(413,'La imagen supera el limite de 16 megapixeles')
            if image.format not in ('PNG','JPEG','WEBP'):raise ErrorPortal(400,'Usa PNG, JPEG o WebP')
            image=ImageOps.exif_transpose(image)
            mode='RGBA' if 'A' in image.getbands() or 'transparency' in image.info else 'RGB'
            image=image.convert(mode)
            # Imagen nueva: no conservar prompt, EXIF ni otra metadata de la referencia.
            clean=Image.new(mode,image.size);clean.paste(image);out=io.BytesIO();clean.save(out,format='PNG')
    except (OSError,UnidentifiedImageError,Image.DecompressionBombError):raise ErrorPortal(400,'Imagen invalida')
    saved=request.app[STORE].save_file(request['user']['id'],out.getvalue(),'image/png')
    return web.json_response(saved,status=201)


async def files(request):return web.json_response({'archivos':request.app[STORE].files(request['user'])})
async def file_download(request):
    row=request.app[STORE].file(request.match_info['id'],request['user']);path=request.app[STORE].path(row)
    if not path.is_file():raise ErrorPortal(404,'Archivo no disponible')
    response=web.FileResponse(path);response.content_type=row['mime']
    if request.match_info.get('action')!='vista':response.headers['Content-Disposition']=f'attachment; filename="{path.name}"'
    elif row['mime']!='image/png':raise ErrorPortal(400,'Este archivo no tiene vista de imagen')
    return response
async def delete_file(request):
    request.app[STORE].delete_file(request.match_info['id'],request['user']);return web.json_response({'eliminado':True})


async def jobs(request):
    if request.method=='GET':return web.json_response({'trabajos':request.app[STORE].jobs(request['user'])})
    data=await body(request)
    if data.get('tipo') not in request.app[FLOWS]:raise ErrorPortal(400,'Este flujo no esta habilitado en el servicio')
    job=request.app[STORE].create_job(request['user'],data);return web.json_response(job,status=201)
async def job(request):return web.json_response(request.app[STORE].job(request.match_info['id'],request['user']))
async def cancel(request):return web.json_response(request.app[STORE].cancel(request.match_info['id'],request['user']))
async def delete_job(request):return web.json_response(request.app[STORE].delete_job(request.match_info['id'],request['user']))
async def retry_job(request):
    job=request.app[STORE].job(request.match_info['id'],request['user'])
    if job['kind'] not in request.app[FLOWS]:raise ErrorPortal(400,'Este flujo no esta habilitado en el servicio')
    return web.json_response(retry(request.app[STORE],request.match_info['id'],request['user']))
async def motor(request):
    import time
    with request.app[STORE].connect() as db:row=db.execute("SELECT expires,status FROM worker_lease WHERE resource='gpu'").fetchone()
    return web.json_response({'trabajador_activo':bool(row and row['expires']>time.time()),'estado':row['status'] if row and row['expires']>time.time() else 'trabajador_desconectado'})
async def capabilities(request):return web.json_response({'flujos':list(request.app[FLOWS])})


def create_app(data_dir,secure_cookies=True,origin='',flows=('2d','3d'),private_config=None):
    app=web.Application(middlewares=[errors,private_boundary,auth],client_max_size=MAX_UPLOAD+65536)
    if private_config is not None:
        if not secure_cookies:raise ValueError('El piloto privado requiere cookies HTTPS')
        access=PrivateAccess(private_config)
        if origin and origin!=access.origin:raise ValueError('Origen distinto al piloto')
        origin=access.origin;app[PRIVATE]=access
    app[STORE]=Store(data_dir);app[COOKIE]=secure_cookies;app[ORIGIN]=origin
    if not flows or any(f not in ('2d','3d') for f in flows):raise ValueError('Flujos invalidos')
    app[FLOWS]=tuple(flows)
    app.add_routes([web.get('/',index),web.get('/assets/{name}',asset),
        web.post('/api/login',login),web.post('/api/logout',logout),web.get('/api/me',me),
        web.get('/api/usuarios',users),web.post('/api/usuarios',users),web.patch('/api/usuarios/{id}',set_user),
        web.get('/api/archivos',files),web.post('/api/referencias',upload),
        web.get('/api/archivos/{id}/{action:vista|descargar}',file_download),web.delete('/api/archivos/{id}',delete_file),
        web.get('/api/trabajos',jobs),web.post('/api/trabajos',jobs),web.get('/api/trabajos/{id}',job),
        web.post('/api/trabajos/{id}/cancelar',cancel),web.delete('/api/trabajos/{id}',delete_job)])
    app.add_routes([web.post('/api/trabajos/{id}/reintentar',retry_job),web.get('/api/motor',motor),web.get('/api/capacidades',capabilities)])
    return app
