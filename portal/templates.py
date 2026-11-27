"""Construccion de grafos exclusivamente desde plantillas distribuidas con el codigo."""
import ast
import copy
import importlib.util
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


def qwen_template():
    # Lee solo el diccionario literal publicado; no ejecuta el generador CLI de workflows.
    tree=ast.parse((ROOT/'scripts/crear_flujo_qwen.py').read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='GRAFO' for t in node.targets):return ast.literal_eval(node.value)
    raise RuntimeError('Plantilla 2D ausente')


def build(job,references,prefix):
    options=job['opciones'];attempt=job['intento']
    seed=((options['semilla'] if options['semilla'] is not None else int(job['id'][:8],16))+attempt-1)%(2**32-2)
    if job['kind']=='2d':
        g=copy.deepcopy(qwen_template());size=options['resolucion']
        g['4']['inputs'].update(prompt=job['prompt'],negative_prompt=options['negativo'],resolution=size)
        g['5']['inputs'].update(width=size,height=size)
        g['6']['inputs'].update(seed=seed,steps=options['pasos'])
        g['9']['inputs']['filename_prefix']=prefix+'/imagen'
        if references:
            for i,name in enumerate(references):
                key=str(20+i);g[key]={'class_type':'LoadImage','inputs':{'image':name}}
                g['4']['inputs'][f'images.image_{i+1}']=[key,0]
            g['6']['inputs']['latent_image']=['4',2];del g['5']
        return g
    source=ROOT/'scripts/generar_3d.py'
    spec=importlib.util.spec_from_file_location('exo_worker_builder',source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    color=options['color']
    g=module.workflow('trellis2',references[0],prefix+'/malla',options['pasos'],7.5,0,seed,True,'#FFFFFF',color,1024)
    g.pop('82',None) # No escribir la malla en bruto de decenas de millones de caras.
    g['35']['inputs']['target_resolution']=str(options['resolucion_forma'])
    if color:
        for key in ('68','69','70','71','72'):g.pop(key,None) # Sin UV/bake costoso en el servicio inicial.
        g['73']={'class_type':'ExoTransferirColor','inputs':{'mesh':['64',0],'referencia':['37',0],'voxel_colors':['67',0]}}
        g['66']['inputs']['steps']=options['pasos']
        origin=['73',0]
    else:
        g['61']={'class_type':'GetMeshInfo','inputs':{'mesh':['37',0]}}
        g['62']={'class_type':'ExoSolidificar','inputs':{'mesh':['61',0],'resolucion':384,'cerrar_grietas':1,'suavizar_forma':2}}
        g['63']={'class_type':'DecimateMesh','inputs':{'mesh':['62',0],'target_face_count':700000,'placement_mode':'midpoint'}}
        g['64']={'class_type':'MeshSmoothNormals','inputs':{'mesh':['63',0],'crease_angle':180.0}}
        origin=['64',0]
    g['62']['inputs'].update(resolucion=options['resolucion_reparacion'],suavizar_forma=2)
    if color and options['paleta']:
        g['200']={'class_type':'ExoPaletaFilamentos','inputs':{'mesh':origin,'paleta':options['paleta'],'colores':options['filamentos'],'peso_luz':.25,'min_mancha':.01,'suavizar_bordes':2}}
        origin=['200',0]
    g['201']={'class_type':'ExoInformeImpresion','inputs':{'mesh':origin,'altura_mm':options['altura_mm'],'material':'PLA','relleno':15,'pared_mm':1.2}}
    if color:g['74']['inputs']['mesh']=['201',0]
    else:g['82']={'class_type':'SaveGLB','inputs':{'mesh':['201',0],'filename_prefix':prefix+'/malla'}}
    g['203']={'class_type':'ExoGuardarImpresion','inputs':{'mesh':['201',0],'nombre':prefix+'/pieza','guardar_obj':False,'guardar_3mf_experimental':color,'poner_de_pie':True,'max_colores':options['filamentos'],'paleta_impresion':options['paleta']}}
    g['230']={'class_type':'RenderMesh','inputs':{'mesh':['201',0],'mode':'auto','width':448,'height':448,'background':'#7a8290'}}
    g['231']={'class_type':'SaveImage','inputs':{'images':['230',0],'filename_prefix':prefix+'/vista'}}
    return g
