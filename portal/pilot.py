"""Prepare an isolated Serve pilot without changing global tailnet policy.

No account password, real hostname, identity or runtime file belongs in Git.
"""
import json
import socket
import subprocess
from pathlib import Path

from .private_access import PrivateAccess,identity
from .store_errors import ErrorPortal


def tailscale(executable,*args):
    result=subprocess.run([str(executable),*args],capture_output=True,text=True,timeout=40)
    if result.returncode:raise ErrorPortal(503,'Tailscale no pudo completar la operacion; revisa su consola local')
    return result.stdout


def save(path,data):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)


def port_free(port):
    try:
        # Connection refusal can take seconds on Windows. Bind instead, and
        # check both loopback families rather than treating timeouts as free.
        addresses={(f,a) for f,_,_,_,a in socket.getaddrinfo('localhost',port,type=socket.SOCK_STREAM)}
        for family,address in addresses:
            with socket.socket(family,socket.SOCK_STREAM) as sock:
                if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
                    sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
                sock.bind(address)
        return True
    except OSError:return False


def prepare(data_dir,executable,https_port=10000,backend_port=8090):
    root=Path(data_dir).resolve()
    # Generated network data must never enter the checkout (including subdirs).
    if any((p/'.git').exists() for p in (root,*root.parents)):
        raise ErrorPortal(400,'Los datos privados deben estar fuera del repositorio')
    if not 1024<=https_port<=65535 or not 1024<=backend_port<=65535 or https_port==backend_port:
        raise ErrorPortal(400,'Puertos invalidos')
    root.mkdir(parents=True,exist_ok=True)
    config=root/'acceso-privado.json'
    if config.exists():raise ErrorPortal(409,'El piloto ya esta preparado; conserva su configuracion local')
    status=json.loads(tailscale(executable,'status','--json'))
    before=json.loads(tailscale(executable,'serve','status','--json') or '{}')
    if status.get('BackendState')!='Running' or not status.get('Self',{}).get('Online'):
        raise ErrorPortal(503,'Tailscale debe estar conectado')
    if str(https_port) in before.get('TCP',{}) or not port_free(https_port) or not port_free(backend_port):
        raise ErrorPortal(409,'Puerto ocupado; no se reemplazo ningun servicio')
    node=status['Self'];owner=status.get('User',{}).get(str(node.get('UserID')),{}).get('LoginName')
    dns=node.get('DNSName','').rstrip('.')
    if not owner or not dns or any(c in dns for c in '/:@'):
        raise ErrorPortal(400,'Se requiere un dispositivo personal con identidad y DNS privado')
    data={'origen':f'https://{dns}:{https_port}','identidades_permitidas':[identity(owner)],
          'puerto_local':backend_port,'puerto_https':https_port}
    save(root/'serve-anterior.json',before);save(config,data)
    PrivateAccess(config)
    return config


def publish(data_dir,executable):
    root=Path(data_dir).resolve();config=root/'acceso-privado.json';access=PrivateAccess(config)
    data=json.loads(config.read_text(encoding='utf-8'));port=str(data['puerto_https'])
    before=json.loads(tailscale(executable,'serve','status','--json') or '{}')
    if port in before.get('TCP',{}) or not port_free(int(port)):
        raise ErrorPortal(409,'Puerto HTTPS ocupado; no se reemplazo ningun servicio')
    # A healthy portal must be running and enforcing the identity boundary first.
    import urllib.request,urllib.error
    try:
        urllib.request.urlopen(f"http://localhost:{data['puerto_local']}/api/me",timeout=3)
        raise ErrorPortal(409,'El backend no esta protegido')
    except urllib.error.HTTPError as exc:
        if exc.code!=403:raise ErrorPortal(409,'No se verifico el cierre del backend') from None
    except OSError:raise ErrorPortal(503,'Primero inicia el portal privado') from None
    tailscale(executable,'serve','--bg',f'--https={port}',f"http://localhost:{data['puerto_local']}")
    after=json.loads(tailscale(executable,'serve','status','--json') or '{}')
    # Record ownership only if all previous ports survived and our route is private.
    for key,value in before.get('TCP',{}).items():
        if after.get('TCP',{}).get(key)!=value:raise ErrorPortal(503,'Verifica Serve: un servicio previo cambio')
    for key,value in before.get('Web',{}).items():
        if after.get('Web',{}).get(key)!=value:raise ErrorPortal(503,'Verifica Serve: una ruta previa cambio')
    host=access.origin.removeprefix('https://')
    if after.get('AllowFunnel',{}).get(host) or not after.get('TCP',{}).get(port,{}).get('HTTPS'):
        raise ErrorPortal(503,'No se verifico el acceso privado HTTPS')
    handlers=after.get('Web',{}).get(host,{}).get('Handlers',{})
    if handlers!={'/':{'Proxy':f"http://localhost:{data['puerto_local']}"}}:
        raise ErrorPortal(503,'No se verifico la ruta exclusiva del portal')
    save(root/'serve-piloto.json',{'puerto':port,'web':after.get('Web',{}).get(host),'tcp':after['TCP'][port]})
    (root/'ABRIR_PORTAL.txt').write_text(access.origin+'\n',encoding='utf-8')
    return access.origin


def unpublish(data_dir,executable):
    root=Path(data_dir).resolve();receipt=root/'serve-piloto.json'
    own=json.loads(receipt.read_text(encoding='utf-8'))
    access=PrivateAccess(root/'acceso-privado.json');host=access.origin.removeprefix('https://')
    current=json.loads(tailscale(executable,'serve','status','--json') or '{}')
    if current.get('TCP',{}).get(own['puerto'])!=own['tcp'] or current.get('Web',{}).get(host)!=own['web']:
        raise ErrorPortal(409,'La ruta cambio; no se elimina un servicio ajeno')
    tailscale(executable,'serve','--bg',f"--https={own['puerto']}",'off')
    receipt.unlink()
