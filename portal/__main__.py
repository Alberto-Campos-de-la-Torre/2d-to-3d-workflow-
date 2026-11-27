import argparse
import getpass
import os
import asyncio
from pathlib import Path
from aiohttp import web
from .app import create_app
from .store import Store,ROLES,ErrorPortal


def main():
    ap=argparse.ArgumentParser(description='Portal Exo independiente: cuentas y datos privados')
    ap.add_argument('--datos',type=Path,default=Path(os.environ.get('EXO_PORTAL_DATA',Path.home()/'.exo-portal')))
    commands=ap.add_subparsers(dest='command',required=True)
    user=commands.add_parser('crear-usuario');user.add_argument('usuario');user.add_argument('--rol',choices=sorted(ROLES),default='cliente')
    serve=commands.add_parser('servir');serve.add_argument('--host',default='localhost');serve.add_argument('--puerto',type=int,default=8090)
    serve.add_argument('--local-http',action='store_true');serve.add_argument('--origen',default='')
    serve.add_argument('--perfil',choices=('2d','3d','ambos'),default='ambos')
    worker=commands.add_parser('trabajador');worker.add_argument('--comfyui',type=Path,required=True)
    worker.add_argument('--comfy-url',default=os.environ.get('EXO_COMFY_URL','http://localhost:8188'))
    worker.add_argument('--tiempo-maximo',type=int,default=1800)
    resolve=commands.add_parser('resolver-perdida');resolve.add_argument('trabajo')
    resolve.add_argument('--comfyui',type=Path,required=True)
    resolve.add_argument('--comfy-url',default=os.environ.get('EXO_COMFY_URL','http://localhost:8188'))
    resolve.add_argument('--confirmar-perdida',action='store_true')
    args=ap.parse_args()
    try:
        if args.command=='crear-usuario':
            first=getpass.getpass('Contraseña (no se muestra): ');second=getpass.getpass('Repite la contraseña: ')
            if first!=second:raise ErrorPortal(400,'Las contraseñas no coinciden')
            user=Store(args.datos).create_user(args.usuario,first,args.rol);print('Usuario creado:',user['login'],user['role']);return
        if args.command in ('trabajador','resolver-perdida'):
            from .worker import Worker,resolve_lost
            from .backend import Backend
            store=Store(args.datos);backend=Backend(args.comfy_url,args.comfyui)
            if args.command=='resolver-perdida':
                if not args.confirmar_perdida:raise ErrorPortal(400,'Verifica el motor y confirma la perdida con --confirmar-perdida; no se reenviara automaticamente')
                asyncio.run(resolve_lost(store,backend,args.trabajo));return
            if not 60<=args.tiempo_maximo<=7200:raise ErrorPortal(400,'Tiempo maximo del trabajador: entre 60 y 7200 segundos')
            asyncio.run(Worker(store,backend,max_seconds=args.tiempo_maximo).run());return
        if args.local_http and args.host!='localhost':raise ErrorPortal(400,'HTTP de desarrollo solo se permite en localhost')
        flows=('2d','3d') if args.perfil=='ambos' else (args.perfil,)
        web.run_app(create_app(args.datos,secure_cookies=not args.local_http,origin=args.origen,flows=flows),host=args.host,port=args.puerto)
    except ErrorPortal as exc:ap.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
