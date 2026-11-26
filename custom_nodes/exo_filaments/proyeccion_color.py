"""Proyeccion frontal ortografica: solo para referencias frontales alineadas."""
import numpy as np
from scipy.ndimage import maximum_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def proyectar(vertices, caras, colores, imagen, mascara, completar_oscuras=False):
    pixels=np.argwhere(mascara>0.5)
    if not len(pixels):raise ValueError('Referencia sin mascara de objeto')
    ymin,xmin=pixels.min(0);ymax,xmax=pixels.max(0)
    bajo,alto=vertices.min(0),vertices.max(0)
    uv=(vertices[:,:2]-bajo[:2])/np.maximum(alto[:2]-bajo[:2],1e-9)
    x=np.clip(np.rint(xmin+uv[:,0]*(xmax-xmin)),0,imagen.shape[1]-1).astype(int)
    y=np.clip(np.rint(ymax-uv[:,1]*(ymax-ymin)),0,imagen.shape[0]-1).astype(int)
    z=vertices[:,2]
    profundidad=np.full(imagen.shape[:2],-np.inf,dtype=np.float32)
    np.maximum.at(profundidad,(y,x),z)
    profundidad=maximum_filter(profundidad,size=3)
    normal=np.zeros_like(vertices)
    a,b,c=vertices[caras[:,0]],vertices[caras[:,1]],vertices[caras[:,2]]
    n=np.cross(b-a,c-a)
    for i in range(3):np.add.at(normal,caras[:,i],n)
    largo=np.linalg.norm(normal,axis=1)
    nz=normal[:,2]/np.maximum(largo,1e-12)
    tolerancia=float((alto-bajo).max())*.012
    visibles=(z>=profundidad[y,x]-tolerancia)&(nz>.15)&(mascara[y,x]>.5)
    resultado=colores.copy()
    resultado[visibles]=imagen[y[visibles],x[visibles],:3]
    if completar_oscuras:
        oscuras=(colores.max(axis=1)<.25)|((colores[:,0]>.2)&(colores[:,0]>3*colores[:,1])&(colores[:,2]<.25))
        ids=np.flatnonzero(oscuras)
        mapa=np.full(len(vertices),-1,dtype=np.int32);mapa[ids]=np.arange(len(ids))
        e=np.concatenate([caras[:,[0,1]],caras[:,[1,2]],caras[:,[2,0]]])
        e=e[oscuras[e].all(axis=1)]
        if len(e):
            graph=coo_matrix((np.ones(len(e),dtype=np.uint8),(mapa[e[:,0]],mapa[e[:,1]])),shape=(len(ids),len(ids))).tocsr()
            _,labels=connected_components(graph,directed=False)
            fotos=imagen[y,x,:3]
            for grupo in np.unique(labels):
                region=ids[labels==grupo]
                semillas=region[visibles[region]]
                if len(semillas)<50:continue
                claras=fotos[semillas].max(axis=1)>.5
                if claras.mean()<.6:continue
                tono=np.median(fotos[semillas[claras]],axis=0)
                semillas_tono=semillas[np.linalg.norm(fotos[semillas]-tono,axis=1)<.25]
                if not len(semillas_tono):continue
                borde=float((alto-bajo).max())*.05
                limites_min=vertices[semillas_tono,:2].min(0)-borde
                limites_max=vertices[semillas_tono,:2].max(0)+borde
                candidatos=region[~visibles[region]]
                candidatos=candidatos[((vertices[candidatos,:2]>=limites_min)&(vertices[candidatos,:2]<=limites_max)).all(axis=1)]
                fg=mascara[y[candidatos],x[candidatos]]>.5
                foto=fotos[candidatos]
                # Conservar ojos visibles y pelo gris; no inferir tonos de otras piezas.
                ojos=fg&(foto.max(1)<.3)&(y[candidatos]<ymin+.53*(ymax-ymin))&(z[candidatos]>profundidad[y[candidatos],x[candidatos]]-.08*(alto-bajo).max())
                pelo=fg&((foto.max(1)-foto.min(1))<.12)&(foto.mean(1)>.15)
                candidatos=candidatos[~(ojos|pelo)]
                resultado[candidatos]=tono
                visibles[candidatos]=True
    return resultado,visibles
