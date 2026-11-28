"""Private Serve boundary. Local processes on the server are trusted operators.

The identity allowlist is deliberately separate from portal accounts and roles.
Read it on every request so revocation also affects existing portal sessions.
"""
import ipaddress
import json
from email.header import decode_header, make_header
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web
from .store_errors import ErrorPortal

PRIVATE=web.AppKey('private_access',object)


def identity(value):
    if not isinstance(value,str) or len(value)>512:raise ValueError('Identidad invalida')
    value=str(make_header(decode_header(value))).strip().casefold()
    if not value or any(ord(c)<32 for c in value):raise ValueError('Identidad invalida')
    return value


class PrivateAccess:
    def __init__(self,path):
        self.path=Path(path).resolve()
        self.origin,self.allowed=self.read()

    def read(self):
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data,dict):raise ValueError('Configuracion invalida')
        origin=data['origen']
        if not isinstance(origin,str):raise ValueError('Origen invalido')
        parsed=urlsplit(origin)
        if (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or parsed.port is None):
            raise ValueError('Origen HTTPS privado invalido; especifica el puerto')
        users=data['identidades_permitidas']
        if not isinstance(users,list):raise ValueError('Lista de identidades invalida')
        return origin,frozenset(identity(u) for u in users)

    def check(self,request):
        try:
            # Fail closed on deletion, corrupt config, or runtime origin change.
            origin,allowed=self.read()
            if origin!=self.origin:raise ValueError('Reinicia para cambiar el origen')
            if not ipaddress.ip_address(request.remote or '').is_loopback:raise ValueError('Proxy no local')
            if request.host.casefold()!=urlsplit(origin).netloc.casefold():raise ValueError('Host no permitido')
            values=request.headers.getall('Tailscale-User-Login',[])
            if len(values)!=1 or identity(values[0]) not in allowed:raise ValueError('Identidad no autorizada')
            if request.headers.get('Origin') not in (None,origin):raise ValueError('Origen no permitido')
        except (OSError,ValueError,KeyError,TypeError,LookupError):
            raise ErrorPortal(403,'Acceso privado no autorizado') from None


@web.middleware
async def private_boundary(request,handler):
    access=request.app.get(PRIVATE)
    if access is not None:access.check(request)
    return await handler(request)
