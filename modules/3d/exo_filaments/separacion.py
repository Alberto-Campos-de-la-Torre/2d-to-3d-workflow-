"""Cortes planos cerrados. Worker aislado para limitar tiempo y memoria retenida."""
import json, math, sys
from pathlib import Path
import numpy as np


def cortar(vertices, caras, colores=None, eje="y", porcentaje=50):
    import trimesh
    from manifold3d import Manifold, Mesh
    if eje not in ("x","y","z") or not math.isfinite(porcentaje) or not 1<=porcentaje<=99:
        raise ValueError("Eje o posicion de corte invalido (1 a 99 %)")
    v=np.asarray(vertices,dtype=float);f=np.asarray(caras,dtype=np.int64)
    if v.ndim!=2 or v.shape[1]!=3 or f.ndim!=2 or f.shape[1]!=3 or not len(f) or len(f)>800000:
        raise ValueError("Se requiere una malla triangular simplificada")
    if not np.isfinite(v).all() or f.min()<0 or f.max()>=len(v):raise ValueError("Geometria invalida")
    axis="xyz".index(eje);pos=float(v[:,axis].min()+np.ptp(v[:,axis])*porcentaje/100)
    # Soldado relativo para OBJ con vertices duplicados. No se rellenan agujeros.
    tol=max(np.linalg.norm(np.ptp(v,axis=0))*1e-7,1e-9)
    _,first,inv=np.unique(np.round(v/tol).astype(np.int64),axis=0,return_index=True,return_inverse=True)
    v=v[first];f=inv[f]
    mesh=trimesh.Trimesh(vertices=v,faces=f,process=False)
    if not mesh.is_watertight:
        cuentas=np.bincount(mesh.edges_unique_inverse)
        raise ValueError("Reparar topologia antes de cortar: %d aristas abiertas y %d no manifold" % (np.count_nonzero(cuentas==1),np.count_nonzero(cuentas>2)))
    # No orientar cada componente hacia afuera: las paredes de cavidades deben
    # mirar hacia adentro. Conservar winding correcto y solo reparar incoherencias.
    if not mesh.is_winding_consistent:
        trimesh.repair.fix_winding(mesh)
    if mesh.volume < 0:
        mesh.invert()
    if not mesh.is_winding_consistent or mesh.volume<=0:raise ValueError("No se pudo orientar un solido valido")
    props=v if colores is None else np.c_[v,np.asarray(colores)[first]]
    solid=Manifold(Mesh(vert_properties=np.asarray(props,dtype=np.float32),tri_verts=np.asarray(mesh.faces,dtype=np.uint32)))
    if solid.is_empty():raise ValueError("El motor de solidos rechazo la malla")
    normal=np.eye(3)[axis]
    partes=solid.split_by_plane(normal,pos)
    if any(p.is_empty() for p in partes):raise ValueError("El plano no divide el solido en dos partes")
    original=solid.volume();vols=[p.volume() for p in partes]
    error=abs(sum(vols)-original)/original
    if error>0.001:raise ValueError("El corte no conserva el volumen (tolerancia 0.1 %)")
    result=[]
    for i,part in enumerate(partes):
        out=part.to_mesh();vv=np.asarray(out.vert_properties[:,:3],dtype=float);ff=np.asarray(out.tri_verts,dtype=np.int64)
        check=trimesh.Trimesh(vv,ff,process=False)
        # Propiedades distintas pueden duplicar vertices; soldar solo para validar topologia.
        check.merge_vertices()
        if not check.is_watertight or not check.is_winding_consistent:raise ValueError("La pieza cortada no es un solido cerrado")
        cc=np.clip(np.asarray(out.vert_properties[:,3:6]),0,1) if props.shape[1]>=6 else None
        if cc is not None:
            # Evitar miles de materiales nuevos por interpolacion en la superficie cortada.
            palette=np.unique(np.round(np.asarray(colores),4),axis=0)
            if len(palette)>16:
                raise ValueError("Reducir la paleta a 16 colores o menos antes de separar")
            cc=palette[np.argmin(((cc[:,None,:]-palette[None,:,:])**2).sum(axis=2),axis=1)]
        # Vista de montaje conserva coordenadas originales. STL apoya la cara de corte.
        arriba=normal if i==0 else -normal
        referencia=np.array([1,0,0]) if axis!=0 else np.array([0,1,0])
        derecha=np.cross(referencia,arriba);derecha/=np.linalg.norm(derecha)
        frente=np.cross(arriba,derecha)
        rot=np.stack([derecha,frente,arriba]);puesta=vv@rot.T
        trans=-puesta.min(axis=0);puesta+=trans
        result.append({"vertices":vv,"caras":ff,"colores":cc,"stl_vertices":puesta,
            "volumen_mm3":float(vols[i]),"rotacion":rot.tolist(),"traslacion":trans.tolist(),
            "dimensiones_mm":np.ptp(puesta,axis=0).tolist(),"componentes":int(check.body_count)})
    return result,{"eje":eje,"porcentaje":porcentaje,"posicion_mm":pos,"volumen_original_mm3":original,
        "error_volumen_pct":error*100,"cerradas":True,
        "avisos":["Corte plano, sin encajes: verificar montaje y adhesivo.",
                   "Un corte puede atravesar varias zonas; revisar componentes separados y superficies visibles.",
                   "STL monocolor: elegir bobina en Creality Print. OBJ conserva paleta aproximada y posicion de montaje; revisar color de caras internas.",
                   "Orientacion propuesta sobre el plano de corte; laminar y revisar soportes, estabilidad y paredes."]}


def ejecutar(ruta,destino,eje,porcentaje):
    # Importacion sin registrar las rutas de ComfyUI en el worker.
    import types,importlib
    paquete=types.ModuleType("exo_worker");paquete.__path__=[str(Path(__file__).parent)];sys.modules[paquete.__name__]=paquete
    leer=importlib.import_module("exo_worker.plan_impresion").leer_obj
    v,f,c=leer(Path(ruta));parts,informe=cortar(v,f,c,eje,porcentaje)
    # Exportadores existentes, cargados por AST para evitar iniciar ComfyUI.
    import ast,os,struct
    tree=ast.parse((Path(__file__).parent/"nodes.py").read_text(encoding="utf-8-sig"))
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ("_malla_exportable","_escribir_stl","_escribir_obj")]
    paleta=importlib.import_module("exo_worker.paleta")
    agrupar,leer_paleta,color_por_vertice=paleta.agrupar,paleta.leer_paleta,paleta.color_por_vertice
    from manifold3d import Manifold, Mesh as MeshManifold
    env={"__name__":"exo_worker.nodes","__package__":"exo_worker","Manifold":Manifold,"MeshManifold":MeshManifold,"np":np,"os":os,"struct":struct,"agrupar":agrupar,"leer_paleta":leer_paleta,"color_por_vertice":color_por_vertice}
    exec(compile(ast.Module(body=functions,type_ignores=[]),"exportadores", "exec"),env)
    destino=Path(destino);destino.mkdir(parents=True,exist_ok=False)
    archivos=[];informe["piezas"]=[]
    for i,p in enumerate(parts,1):
        name="parte_%d"%i
        env['_escribir_stl'](str(destino/(name+'.stl')),p['stl_vertices'],p['caras']);archivos.append(name+'.stl')
        if p['colores'] is not None:
            env['_escribir_obj'](str(destino/(name+'.obj')),p['vertices'],p['caras'],p['colores']);archivos += [name+'.obj',name+'.mtl']
        informe['piezas'].append({k:p[k] for k in ['volumen_mm3','rotacion','traslacion','dimensiones_mm','componentes']})
    (destino/'montaje.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
    archivos.append('montaje.json')
    return {"archivos":archivos,"informe":informe}

if __name__=='__main__':
    try:
        result=ejecutar(sys.argv[1],sys.argv[2],sys.argv[3],float(sys.argv[4]));print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error":str(exc)},ensure_ascii=False));sys.exit(1)
