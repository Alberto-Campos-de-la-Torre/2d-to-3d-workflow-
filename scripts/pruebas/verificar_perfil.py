import asyncio,importlib.util,json,sys,types
from pathlib import Path
from aiohttp import web

comfy=Path(sys.argv[1]);perfil=sys.argv[2]
sys.path.insert(0,sys.argv[3])
from comfy_api.latest import ComfyExtension,IO
if perfil=='2d':
    class BloquearMallas:
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0] in ('manifold3d','trimesh','skimage'):
                raise ImportError('El perfil 2D intento importar una libreria de mallas: '+fullname)
    sys.meta_path.insert(0,BloquearMallas())
folders=types.ModuleType('folder_paths');folders.base_path=str(comfy)
folders.get_output_directory=lambda:str(comfy/'output')
folders.get_input_directory=lambda:str(comfy/'input')
folders.get_user_directory=lambda:str(comfy/'user')
folders.get_filename_list=lambda *a:[]
sys.modules['folder_paths']=folders
server=types.ModuleType('server')
q=types.SimpleNamespace(get_history=lambda **k:{},get_current_queue=lambda:([],[]))
instance=types.SimpleNamespace(routes=web.RouteTableDef(),app=web.Application(),prompt_queue=q)
server.PromptServer=types.SimpleNamespace(instance=instance);sys.modules['server']=server
p=comfy/'custom_nodes/exo_filaments'
spec=importlib.util.spec_from_file_location('exo_qa',p/'__init__.py',submodule_search_locations=[str(p)])
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
extension=asyncio.run(mod.comfy_entrypoint());nodos=asyncio.run(extension.get_node_list())
names=[n.__name__ for n in nodos]
assert len(names)==len(set(names))
for n in nodos:n.define_schema()
paths=[r.path for r in instance.routes]
assert ('/exo/estudio' in paths)==(perfil in ('2d','ambos'))
assert ('/exo/pieza' in paths)==(perfil in ('3d','ambos'))
assert '/exo/resultados' in paths and '/exo/modulos' in paths
if perfil=='2d':
    assert len(nodos)==3
    assert not any(k.startswith('exo_qa.pieza') or k=='exo_qa.nodes' for k in sys.modules)
elif perfil=='3d':assert not any(n in names for n in ['ExoPromptIA','ExoRevisarImagen','ExoCorregirPrompt'])
if perfil in ('3d','ambos'):
    pieza=sys.modules['exo_qa.pieza']
    graph=pieza.construir('referencia.png',{'color':True,'color_frontal':True})
    assert graph['62']['inputs']['resolucion']==384 and graph['203']['inputs']['guardar_3mf_experimental']
print(json.dumps({'perfil':perfil,'nodos':len(nodos),'rutas':len(paths),'importacion':'correcta','esquemas':'correctos'}))
