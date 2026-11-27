import argparse
import getpass
import os
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
    args=ap.parse_args()
    try:
        if args.command=='crear-usuario':
            first=getpass.getpass('Contraseña (no se muestra): ');second=getpass.getpass('Repite la contraseña: ')
            if first!=second:raise ErrorPortal(400,'Las contraseñas no coinciden')
            user=Store(args.datos).create_user(args.usuario,first,args.rol);print('Usuario creado:',user['login'],user['role']);return
        if args.local_http and args.host!='localhost':raise ErrorPortal(400,'HTTP de desarrollo solo se permite en localhost')
        web.run_app(create_app(args.datos,secure_cookies=not args.local_http,origin=args.origen),host=args.host,port=args.puerto)
    except ErrorPortal as exc:ap.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
