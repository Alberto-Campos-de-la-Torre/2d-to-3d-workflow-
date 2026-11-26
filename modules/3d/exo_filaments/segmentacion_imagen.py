"""Paleta predominante del sujeto y mapa de regiones de color, sin fondo."""
import base64
import numpy as np
from PIL import Image
from .paleta import agrupar, rgb_a_hex


def segmentar(imagen, mascara, plazas=4):
    if not 1 <= plazas <= 16:
        raise ValueError('Elegir entre 1 y 16 filamentos')
    h,w=imagen.shape[:2]
    size=(max(1,round(w*min(1,256/max(h,w)))),max(1,round(h*min(1,256/max(h,w)))))
    rgb=np.asarray(Image.fromarray(np.uint8(np.clip(imagen[:,:,:3],0,1)*255)).resize(size,Image.Resampling.LANCZOS),dtype=np.float32)/255
    mask=np.asarray(Image.fromarray(np.float32(mascara)).resize(size,Image.Resampling.NEAREST))>.9
    if not mask.any():
        raise ValueError('No se identifico el sujeto; no se calculara una paleta del fondo')
    labels,colores=agrupar(rgb[mask],n_colores=plazas,peso_luz=.65,min_distancia=6,min_porcentaje=0)
    counts=np.bincount(labels,minlength=len(colores))
    order=np.argsort(-counts,kind='stable')
    order=order[counts[order]>0]
    inverse=np.zeros(len(colores),dtype=np.uint8)
    inverse[order]=np.arange(1,len(order)+1)
    regions=np.zeros(mask.shape,dtype=np.uint8)
    regions[mask]=inverse[labels]
    propuesta=[{'color':rgb_a_hex(colores[i]),'porcentaje':round(100*int(counts[i])/int(mask.sum()),2)} for i in order]
    return {'colores':propuesta,'ancho':size[0],'alto':size[1],
            'regiones':base64.b64encode(regions.tobytes()).decode('ascii'),
            'paleta':','.join(c['color'] for c in propuesta),
            'nota':'Porcentajes del area visible del sujeto; no estiman consumo de filamento ni colores ocultos.'}
