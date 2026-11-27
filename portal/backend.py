"""Transporte privado a ComfyUI y directorios efimeros por intento."""
import io
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from PIL import Image


class MotorError(RuntimeError):
    def __init__(self,code):super().__init__(code);self.code=code


class Backend:
    def __init__(self,url,comfy_root):
        parsed=urlsplit(url)
        try:local=parsed.hostname=='localhost' or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:local=False
        if parsed.scheme not in ('http','https') or not local or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise ValueError('Esta etapa solo admite un ComfyUI local y sin credenciales en la URL')
        self.url=url.rstrip('/');self.root=Path(comfy_root).resolve();self.session=None
        if not (self.root/'main.py').is_file():raise ValueError('Indica la carpeta ComfyUI que contiene main.py')

    async def open(self):self.session=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
    async def close(self):
        if self.session:await self.session.close()
    async def request(self,path,data=None):
        async with self.session.request('POST' if data is not None else 'GET',self.url+path,json=data) as response:
            if response.status>=400:raise MotorError('solicitud_rechazada_por_motor')
            if response.content_length==0:return {}
            text=await response.text()
            if not text:return {}
            try:result=json.loads(text)
            except ValueError:raise MotorError('respuesta_invalida_del_motor')
            if not isinstance(result,dict):raise MotorError('respuesta_invalida_del_motor')
            return result

    async def queue(self):return await self.request('/queue')
    async def history(self,pid):return (await self.request('/history/'+pid)).get(pid)
    async def submit(self,graph,pid):
        result=await self.request('/prompt',{'prompt':graph,'prompt_id':pid,'client_id':pid})
        if result.get('node_errors') or result.get('error'):raise MotorError('plantilla_o_modelos_no_disponibles')
        if result.get('prompt_id')!=pid:raise MotorError('motor_no_admite_identificadores_estables')
    async def cancel(self,pid):
        await self.request('/queue',{'delete':[pid]})
        await self.request('/interrupt',{'prompt_id':pid})

    def scope(self,job,kind):
        if not re.fullmatch(r'[0-9a-f]{32}',job['id']) or not 1<=job['intento']<=3:raise MotorError('identificador_interno_invalido')
        base=(self.root/kind).resolve()
        scope=(base/'exo_portal'/job['id']/str(job['intento'])).resolve()
        if not scope.is_relative_to(base):raise MotorError('directorio_fuera_de_ambito')
        return scope

    def prepare(self,store,job):
        folder=self.scope(job,'input');folder.mkdir(parents=True,exist_ok=True)
        refs=[]
        for ident in job['referencias']:
            row=store.file(ident,{'id':job['owner'],'role':'cliente'})
            target=folder/(ident+'.png')
            if not target.resolve().is_relative_to(folder):raise MotorError('referencia_fuera_de_ambito')
            target.write_bytes(store.path(row).read_bytes())
            refs.append(target.relative_to(self.root/'input').as_posix())
        prefix=self.scope(job,'output').relative_to(self.root/'output').as_posix()
        return refs,prefix

    def artifacts(self,history,job):
        folder=self.scope(job,'output');paths=set()
        suffixes={'.png','.glb','.stl','.3mf'}
        def add(name):
            path=Path(name)
            if path.suffix.lower() not in suffixes:return
            path=(path if path.is_absolute() else self.root/'output'/path).resolve()
            if not path.is_relative_to(folder):raise MotorError('salida_fuera_de_ambito')
            if not path.is_file():raise MotorError('salida_ausente')
            paths.add(path)
        def collect(value):
            if isinstance(value,dict):
                if isinstance(value.get('filename'),str):
                    if value.get('type','output')!='output':return
                    add(str(Path(value.get('subfolder',''))/value['filename']))
                else:
                    for v in value.values():collect(v)
            elif isinstance(value,list):
                for v in value:collect(v)
            elif isinstance(value,str):
                for line in value.splitlines():add(line.strip())
        graph=history.get('prompt',[None,None,{}])[2]
        for node,output in history.get('outputs',{}).items():
            kind=graph.get(node,{}).get('class_type','')
            if kind.startswith('Save') or kind=='ExoGuardarImpresion':collect(output)
        if not paths:raise MotorError('sin_resultados')
        if job['kind']=='3d' and not any(p.suffix=='.stl' for p in paths):raise MotorError('sin_malla_imprimible')
        if job['kind']=='3d' and job['opciones']['color'] and not any(p.suffix=='.3mf' for p in paths):raise MotorError('sin_exportacion_multicolor')
        if any(p.stat().st_size>128*1024*1024 for p in paths) or sum(p.stat().st_size for p in paths)>256*1024*1024:
            raise MotorError('resultados_superan_el_limite')
        return sorted(paths)

    def import_artifacts(self,store,queue,history,job):
        queue.discard_results(job['id'])
        for path in self.artifacts(history,job):
            queue.heartbeat('importando')
            mime={'.png':'image/png','.glb':'model/gltf-binary','.stl':'model/stl','.3mf':'model/3mf'}[path.suffix.lower()]
            data=path.read_bytes()
            if mime=='image/png':
                try:
                    with Image.open(io.BytesIO(data)) as image:
                        mode='RGBA' if 'A' in image.getbands() else 'RGB'
                        clean=Image.new(mode,image.size);clean.paste(image.convert(mode))
                        out=io.BytesIO();clean.save(out,format='PNG');data=out.getvalue()
                except (OSError,ValueError):raise MotorError('resultado_imagen_invalido')
            store.save_file(job['owner'],data,mime,'resultado',job['id'],guard=queue.guard)

    def clean_files(self,job):
        for kind in ('input','output'):
            folder=self.scope(job,kind)
            if not folder.exists():continue
            paths=list(folder.rglob('*'))
            # Comprobar todas las rutas antes de eliminar cualquier archivo.
            if any(not p.resolve().is_relative_to(folder) for p in paths):raise MotorError('enlace_fuera_de_ambito')
            for p in sorted(paths,key=lambda p:len(p.parts),reverse=True):
                if p.is_symlink():p.unlink()
                elif p.is_file():p.unlink()
                elif p.is_dir():p.rmdir()
            folder.rmdir()

    async def clean(self,job):
        self.clean_files(job)
        await self.request('/history',{'delete':[job['runtime']['prompt_id']]})
