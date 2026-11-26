"""Diagnostico de superficies de color; no corta ni lamina el modelo."""
import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from .paleta import agrupar, vecindad, rgb_a_hex

FUENTES = [
    {"titulo": "Creality: pintado multicolor", "url": "https://www.creality.com/help/help-introduction-to-the-color-painting-feature"},
    {"titulo": "K2 Plus y CFS: compatibilidad", "url": "https://forum.creality.com/t/creality-k2-plus-cfs-frequently-asked-questions-you-should-know/21698"},
    {"titulo": "Creality Print: versiones y purga", "url": "https://github.com/CrealityOfficial/CrealityPrint/releases"},
]

def analizar(vertices, caras, colores=None, capa_mm=0.2, plazas=4, sistema="cfs", cama=(350,350,350), material="PLA"):
    v = np.asarray(vertices, dtype=float)
    f = np.asarray(caras, dtype=np.int64)
    if v.ndim != 2 or v.shape[1] != 3 or f.ndim != 2 or f.shape[1] != 3 or not len(f):
        raise ValueError("Se requiere una malla triangular no vacia")
    if len(f) > 800000 or len(v) > 2400000:
        raise ValueError("Demasiada geometria: usar la malla reparada y simplificada")
    if not np.isfinite(v).all() or f.min() < 0 or f.max() >= len(v):
        raise ValueError("Geometria invalida")
    if not math.isfinite(capa_mm) or not 0.05 <= capa_mm <= 1:
        raise ValueError("Altura de capa fuera de 0.05 a 1 mm")
    if sistema not in ("sin_confirmar", "cfs", "manual") or not 1 <= plazas <= 16:
        raise ValueError("Sistema o capacidad de filamentos invalido")
    cama = np.asarray(cama, dtype=float)
    if cama.shape != (3,) or not np.isfinite(cama).all() or (cama <= 0).any():
        raise ValueError("Cama invalida")
    # Entrada en mm y Y arriba, misma convencion del informe de impresion.
    size = np.ptp(v, axis=0)
    area = np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]], v[f[:,2]]-v[f[:,0]]),axis=1)/2
    valido = area > 1e-12
    f, area = f[valido], area[valido]
    if not len(f):
        raise ValueError("La malla no tiene superficie")
    advertencias = ["Regiones de superficie, no piezas solidas ni partes anatomicas identificadas.",
                   "Purga, soportes, tiempo, coste y ahorro requieren laminar con el perfil real de Creality Print.",
                   "La orientacion actual afecta el indicador de colores por capa; no es un numero de cambios del G-code."]
    advertencias.append("Colores aproximados por agrupacion perceptual (hasta 8); confirmar asignacion de bobinas en Creality Print.")
    if material not in ("PLA", "PETG", "ABS", "ASA", "TPU"):
        raise ValueError("Material no reconocido")
    if sistema == "cfs" and material == "TPU":
        advertencias.append("TPU no compatible con alimentacion CFS segun Creality: usar bobina externa y revisar estrategia.")
    if colores is None:
        return {"version":1, "recomendacion":"Color no disponible: revisar geometria", "regiones":[],
                "estrategias":[], "advertencias":advertencias, "fuentes":FUENTES, "colores":None}
    c = np.asarray(colores,dtype=float)
    if c.shape != v.shape or not np.isfinite(c).all() or (c<0).any() or (c>1).any():
        raise ValueError("Colores RGB invalidos")
    labels, centers = agrupar(c[f[:,0]], n_colores=8, min_porcentaje=0, min_distancia=10)
    # Soldar solo para estudiar conectividad, sin modificar la malla de entrada.
    tol = max(float(np.linalg.norm(size))*1e-6,1e-9)
    _, inv = np.unique(np.round(v/tol).astype(np.int64), axis=0, return_inverse=True)
    vecinos = vecindad(inv[f])
    same = vecinos[labels[vecinos[:,0]] == labels[vecinos[:,1]]]
    graph = coo_matrix((np.ones(len(same)),(same[:,0],same[:,1])),shape=(len(f),len(f))).tocsr()
    n, componentes = connected_components(graph, directed=False)
    areas = np.bincount(componentes, weights=area)
    orden = np.argsort(componentes,kind="stable")
    bordes = np.r_[0,np.flatnonzero(np.diff(componentes[orden]))+1,len(f)]
    total = float(area.sum())
    regiones=[]
    for inicio,fin in zip(bordes[:-1],bordes[1:]):
        ix=orden[inicio:fin];comp=componentes[ix[0]];pct=float(areas[comp]/total*100)
        if pct < 0.1: continue
        puntos=v[f[ix].ravel()];bbox=np.ptp(puntos,axis=0)
        candidata=pct>=3 and np.sort(bbox)[1]>=2
        regiones.append({"id":int(comp),"color":rgb_a_hex(centers[labels[ix[0]]]),"area_pct":round(pct,2),
                         "dimensiones_mm":np.round(bbox,2).tolist(),"candidata":bool(candidata),
                         "motivo":"Region amplia: revisar junta y espesor" if candidata else "Detalle: conservar unido o revisar pintado"})
    regiones.sort(key=lambda x:x['area_pct'],reverse=True)
    height=float(size[1]);layers=max(1,math.ceil(height/capa_mm))
    if layers>20000:raise ValueError("Demasiadas capas para este diagnostico")
    y=v[f,1]-v[:,1].min()
    lo=np.clip(np.floor(y.min(axis=1)/capa_mm).astype(int),0,layers-1)
    hi=np.clip(np.floor(y.max(axis=1)/capa_mm).astype(int),0,layers-1)
    d=np.zeros((len(centers),layers+1),dtype=np.int32)
    np.add.at(d,(labels,lo),1);np.add.at(d,(labels,hi+1),-1)
    active=np.cumsum(d[:,:-1],axis=1)>0;count=active.sum(axis=0)
    multi=int((count>1).sum());coexist=round(multi/layers*100,1)
    indicator=int(np.maximum(count-1,0).sum())
    candidatos=sum(x['candidata'] for x in regiones)
    if len(centers)==1:rec='Entero monocolor'
    elif candidatos>=2 and coexist>=20:rec='Evaluar hibrido: separar regiones amplias, conservar detalles'
    elif candidatos>=2:rec='Comparar entero y separado: revisar juntas'
    else:rec='Evaluar entero multicolor: predominan detalles o regiones pequenas'
    entero_ok=sistema=='cfs' and material!='TPU' and len(centers)<=plazas
    if sistema=='sin_confirmar':advertencias.append('Impresora, version de Creality Print y disponibilidad de CFS pendientes de confirmar.')
    if sistema=='manual':advertencias.append('Los colores simultaneos en una capa no se resuelven solo con una pausa por altura.')
    if sistema=='cfs' and len(centers)>plazas:advertencias.append('Mas colores detectados que filamentos configurados: reducir paleta o separar.')
    return {"version":1,"recomendacion":rec,"colores":len(centers),"regiones_total":int(n),
        "regiones":regiones[:60],"candidatas":candidatos,"capa_mm":capa_mm,"capas":layers,
        "capas_multicolor":multi,"coexistencia_pct":coexist,"indicador_coexistencia":indicator,
        "dimensiones_mm":np.round(size,2).tolist(),"cabe":bool(np.all(size[[0,2,1]]<=cama)),
        "impresora":"Creality K2 Plus", "version_creality_print":"pendiente de confirmar", "material":material, "sistema":sistema,"plazas":plazas,"purga_g":None,"tiempo_h":None,"ahorro":None,
        "estrategias":[
            {"nombre":"Entero multicolor","estado":"Compatible en cantidad de filamentos; validar perfil" if entero_ok else "Pendiente o incompatible con el sistema configurado","montaje":"Sin juntas nuevas","purga":"Pendiente de laminado"},
            {"nombre":"Separado por color","estado":"Cortes y encajes pendientes de validar","montaje":"Mas piezas y juntas; medir espesor y accesibilidad","purga":"Podria reducirse agrupando trabajos monocolor"},
            {"nombre":"Hibrido","estado":"Evaluar regiones amplias y mantener detalles unidos","montaje":"Intermedio; aun no hay piezas separadas","purga":"Pendiente de laminado de cada conjunto"}],
        "advertencias":advertencias,"fuentes":FUENTES}

def resumen(p):
    lineas=[p['recomendacion'], 'Diagnostico previo al laminado; recomendacion heuristica.']
    if p['colores'] is not None:
        lineas += [f"Colores: {p['colores']} | regiones: {p['regiones_total']} | candidatas a revision: {p['candidatas']}",
                   f"Capas con varios colores de superficie: {p['coexistencia_pct']} % (capa {p['capa_mm']} mm)",
                   f"Cabe en la cama: {'si' if p['cabe'] else 'no'}"]
        for e in p['estrategias']:lineas.append(e['nombre']+': '+e['estado']+'; '+e['purga'])
        lineas.append('Regiones principales (sin identificar anatomia):')
        for x in p['regiones'][:12]:lineas.append(f"{x['color']} | {x['area_pct']} % | {x['dimensiones_mm']} mm | {x['motivo']}")
    return '\n'.join(lineas+['']+p['advertencias'])

def leer_obj(ruta):
    v=[];f=[];c=[]
    if ruta.stat().st_size>160*1024*1024:raise ValueError('OBJ demasiado grande; usar la exportacion reparada')
    with ruta.open(encoding='utf-8',errors='replace') as stream:
        for line in stream:
            t=line.split()
            if not t:continue
            if t[0]=='v':
                v.append([float(x) for x in t[1:4]])
                if len(t)>=7:c.append([float(x) for x in t[4:7]])
            elif t[0]=='f':
                if len(t)!=4:raise ValueError('Se requiere OBJ triangular')
                indices=[int(x.split('/')[0]) for x in t[1:]]
                f.append([x-1 if x>0 else len(v)+x for x in indices])
            if len(f)>800000 or len(v)>2400000:raise ValueError('OBJ supera el limite de geometria')
    return np.asarray(v),np.asarray(f),np.asarray(c) if len(c)==len(v) else None
