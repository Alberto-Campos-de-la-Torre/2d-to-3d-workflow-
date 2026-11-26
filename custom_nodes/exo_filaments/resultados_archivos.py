"""Inventario persistente y borrado de resultados, limitado a los medios de Exo."""
import hashlib
import filecmp
import json
from pathlib import Path

from PIL import Image

from .archivos import dependencias

IMAGENES={'.png','.jpg','.jpeg','.webp','.bmp'}
MODELOS={'.obj','.stl','.glb','.gltf','.3mf','.ply'}
MEDIOS=IMAGENES|MODELOS|{'.mtl','.bin','.json','.txt'}


class Catalogo:
    def __init__(self, salida, entrada, fichero):
        self.salida=Path(salida).resolve()
        self.entrada=Path(entrada).resolve()
        self.fichero=Path(fichero)
        self.registros=json.loads(self.fichero.read_text(encoding='utf-8')) if self.fichero.exists() else {}
        self._png={}

    def ruta(self, clave):
        tipo, separador, nombre=str(clave).partition(':')
        if not separador or tipo not in ('input','output') or not nombre or '\\' in nombre:
            raise ValueError('Archivo no permitido')
        relativo=Path(nombre)
        if relativo.is_absolute() or '..' in relativo.parts or ':' in nombre:
            raise ValueError('Archivo fuera de las carpetas de resultados')
        raiz=self.entrada if tipo=='input' else self.salida
        p=(raiz/relativo).resolve()
        if not p.is_relative_to(raiz) or p==raiz:
            raise ValueError('Archivo fuera de las carpetas de resultados')
        if tipo=='input':
            permitido=p.suffix.lower() in IMAGENES
        else:
            r=p.relative_to(raiz).parts
            permitido=(r[0]=='qwen21' or r[:2]==('3d','exo')) and p.suffix.lower() in MEDIOS
        if not permitido:raise ValueError('Solo se pueden borrar medios de Exo')
        return p

    def clave(self, ruta, tipo='output'):
        raiz=self.entrada if tipo=='input' else self.salida
        key=tipo+':'+Path(ruta).resolve().relative_to(raiz).as_posix()
        self.ruta(key)
        return key

    def guardar(self):
        self.fichero.parent.mkdir(parents=True,exist_ok=True)
        temporal=self.fichero.with_suffix('.tmp')
        temporal.write_text(json.dumps(self.registros,ensure_ascii=False),encoding='utf-8')
        temporal.replace(self.fichero)

    def grafo_png(self, p):
        if not p.is_file() or p.suffix.lower()!='.png':return {}
        stamp=p.stat().st_mtime_ns
        if p in self._png and self._png[p][0]==stamp:return self._png[p][1]
        try:
            with Image.open(p) as image:graph=json.loads(image.info.get('prompt','{}'))
        except (OSError,ValueError):graph={}
        if not isinstance(graph,dict):graph={}
        self._png[p]=(stamp,graph)
        return graph

    def referencias(self, grafo, existentes=True):
        claves=set()
        for node in grafo.values():
            if not isinstance(node,dict):continue
            inputs=node.get('inputs',{})
            if node.get('class_type') in ('LoadImage','LoadImageMask'):
                name=inputs.get('image')
                if not isinstance(name,str):continue
                tipo='input'
                for suffix,t in [(' [input]','input'),(' [output]','output')]:
                    if name.endswith(suffix):name=name[:-len(suffix)];tipo=t
                key=tipo+':'+name.replace('\\','/')
            elif node.get('class_type')=='ExoCargarMallaSalida':
                tipo='output'
                key='output:'+str(inputs.get('archivo','')).replace('\\','/')
            else:continue
            try:
                p=self.ruta(key)
                if not existentes or p.is_file():claves.add(self.clave(p,tipo))
            except ValueError:continue
        return claves

    def ampliar_referencias(self, claves):
        pendientes=list(claves);vistas=set()
        while pendientes:
            key=pendientes.pop()
            if key in vistas:continue
            vistas.add(key)
            # Las copias PNG de referencias pueden contener a su vez otras referencias.
            pendientes.extend(self.referencias(self.grafo_png(self.ruta(key)))-vistas)
        return vistas

    def ampliar_archivos(self, claves):
        pendientes=list(claves);vistos=set()
        while pendientes:
            key=pendientes.pop()
            if key in vistos:continue
            p=self.ruta(key)
            if not p.is_file():continue
            vistos.add(key)
            if p.suffix.lower() in ('.obj','.mtl'):
                try:
                    pendientes.extend(self.clave(d) for d in dependencias(p,self.salida))
                except ValueError:
                    # Un OBJ roto sigue pudiendo borrarse; nunca seguir rutas externas.
                    pass
            if p.suffix.lower()=='.gltf':
                document=json.loads(p.read_text(encoding='utf-8'))
                for item in document.get('buffers',[])+document.get('images',[]):
                    uri=item.get('uri','')
                    if uri and not uri.startswith('data:'):
                        pendientes.append(self.clave(p.parent/uri))
        return vistos

    def registrar_historia(self, pid, trabajo):
        if pid in self.registros:return
        graph=trabajo.get('prompt',[None,None,{}])[2]
        archivos=set()
        def recoger(valor):
            if isinstance(valor,dict):
                if isinstance(valor.get('filename'),str) and valor.get('type','output')=='output':
                    agregar(str(Path(valor.get('subfolder',''))/valor['filename']))
                for v in valor.values():recoger(v)
            elif isinstance(valor,list):
                for v in valor:recoger(v)
            elif isinstance(valor,str):
                for linea in valor.splitlines():agregar(linea.strip())
        def agregar(nombre):
            try:
                p=Path(nombre)
                key=self.clave(p) if p.is_absolute() else 'output:'+nombre.replace('\\','/')
                if self.ruta(key).is_file():archivos.add(self.clave(self.ruta(key)))
            except (ValueError,OSError):pass
        for node_id,output in trabajo.get('outputs',{}).items():
            clase=graph.get(node_id,{}).get('class_type','')
            if clase.startswith('Save') or clase in ('ExoGuardarImpresion','ExoPlanImpresion'):
                recoger(output)
        if not archivos:return
        archivos=self.ampliar_archivos(archivos)
        refs=self.ampliar_referencias(self.referencias(graph))-archivos
        # Sustituir entradas antiguas de esos archivos por su procedencia exacta.
        for ident,record in list(self.registros.items()):
            if record.get('antiguo') and set(record['archivos'])<=archivos:
                del self.registros[ident]
        self.registros[pid]={'archivos':sorted(archivos),'referencias':sorted(refs),'historial':[pid],'antiguo':False}

    def explorar(self):
        conocidos={k for r in self.registros.values() for k in r['archivos']}
        for carpeta in [self.salida/'qwen21',self.salida/'3d/exo']:
            if not carpeta.is_dir():continue
            for p in sorted(carpeta.rglob('*')):
                if not p.is_file() or p.suffix.lower() not in IMAGENES|MODELOS:continue
                try:key=self.clave(p)
                except ValueError:continue
                if key in conocidos:continue
                # Una textura es dependencia del OBJ, no otro resultado.
                if p.suffix.lower() in IMAGENES and carpeta.name=='exo' and not p.name.startswith('vistas'):
                    continue
                archivos={key}
                if p.suffix.lower() in MODELOS:
                    for ext in MODELOS|{'.mtl'}:
                        sibling=p.with_suffix(ext)
                        if sibling.is_file():archivos.add(self.clave(sibling))
                archivos=self.ampliar_archivos(archivos)
                refs=self.ampliar_referencias(self.referencias(self.grafo_png(p)))-archivos
                ident='archivo-'+hashlib.sha256(key.encode()).hexdigest()[:24]
                self.registros[ident]={'archivos':sorted(archivos),'referencias':sorted(refs),'historial':[],'antiguo':True}
                conocidos.update(archivos)

    def listar(self):
        result=[]
        for ident,r in self.registros.items():
            files=[k for k in r['archivos'] if self.ruta(k).is_file()]
            if not files:continue
            model=next((k for k in files if self.ruta(k).suffix.lower() in MODELOS),None)
            imagen=next((k for k in files if self.ruta(k).suffix.lower() in IMAGENES),None)
            result.append({'id':ident,'nombre':Path((model or imagen or files[0]).split(':',1)[1]).name,
                'tipo':'3d' if model else 'imagen','miniatura':imagen,'archivos':files,
                'antiguo':r['antiguo'],'fecha':max(self.ruta(k).stat().st_mtime for k in files)})
        return sorted(result,key=lambda r:r['fecha'],reverse=True)

    def buscar(self, clave):
        clave=self.clave(self.ruta(clave),clave.split(':',1)[0])
        return next((ident for ident,r in self.registros.items() if clave in r['archivos']),None)

    def plan(self, ident):
        record=self.registros[ident]
        otros=set()
        for i,r in self.registros.items():
            if i!=ident and any(self.ruta(k).is_file() for k in r['archivos']):
                otros.update(r['archivos']);otros.update(r['referencias'])
        archivos=set(record['archivos']);refs=self.ampliar_referencias(record['referencias'])-archivos
        for key in archivos:
            if key.startswith('output:qwen21/'):
                copia='input:qwen_'+Path(key.split(':',1)[1]).name
                if self.ruta(copia).is_file() and self.ruta(key).is_file() and filecmp.cmp(self.ruta(copia),self.ruta(key),shallow=False):
                    refs.add(copia)
        compartidos=(archivos|refs)&otros
        if archivos and not (archivos-otros):
            raise ValueError('Este resultado esta compartido; borra primero los resultados que lo usan')
        borrar=(archivos|refs)-otros
        existentes=[k for k in sorted(borrar) if self.ruta(k).is_file()]
        if not existentes:raise ValueError('Este resultado esta compartido; borra primero los resultados que lo usan')
        version=[(k,self.ruta(k).stat().st_size,self.ruta(k).stat().st_mtime_ns) for k in existentes]
        token=hashlib.sha256(json.dumps([ident,version,sorted(compartidos),record['historial']]).encode()).hexdigest()
        return {'id':ident,'token':token,'archivos':existentes,'referencias':[k for k in existentes if k in refs],
            'conservados':sorted(compartidos),'historial':record['historial'],
            'bytes':sum(s[1] for s in version),'antiguo':record['antiguo']}

    def borrar(self, ident, token):
        plan=self.plan(ident)
        if token!=plan['token']:raise ValueError('Los archivos cambiaron; revisa de nuevo el borrado')
        eliminados=[]
        for key in plan['archivos']:
            self.ruta(key).unlink()
            eliminados.append(key)
        del self.registros[ident]
        self.guardar()
        return {**plan,'eliminados':eliminados}
