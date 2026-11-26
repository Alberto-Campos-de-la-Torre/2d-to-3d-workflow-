"""Lee atributos del GLB generado sin perder COLOR_0 por su material PBR."""
import json,struct
import numpy as np


def cargar(p):
    data=p.read_bytes()
    magic,version,total=struct.unpack_from('<III',data)
    if magic!=0x46546c67 or version!=2 or total!=len(data):raise ValueError('GLB invalido')
    offset=12;doc=None;binary=None
    while offset<len(data):
        size,kind=struct.unpack_from('<II',data,offset);offset+=8
        chunk=data[offset:offset+size];offset+=size
        if kind==0x4e4f534a:doc=json.loads(chunk)
        elif kind==0x004e4942:binary=chunk
    if doc is None or binary is None:raise ValueError('GLB sin datos')
    if len(doc['meshes'])!=1:raise ValueError('Elegir una malla generada de un solo objeto')
    for node in doc.get('nodes',[]):
        if any(k in node for k in ['matrix','translation','rotation','scale']):
            raise ValueError('GLB con transformaciones: convertir antes a malla')
    primitive=doc['meshes'][0]['primitives']
    if len(primitive)!=1 or primitive[0].get('mode',4)!=4:raise ValueError('GLB sin triangulos simples')
    primitive=primitive[0]
    def atributo(i):
        a=doc['accessors'][i];view=doc['bufferViews'][a['bufferView']]
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
        cols={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']]
        start=view.get('byteOffset',0)+a.get('byteOffset',0)
        stride=view.get('byteStride',cols*dtype.itemsize)
        arr=np.ndarray((a['count'],cols),dtype=dtype,buffer=binary,offset=start,
                       strides=(stride,dtype.itemsize)).copy()
        if a.get('normalized') and dtype.kind=='u':arr=arr.astype(np.float32)/np.iinfo(dtype).max
        return arr
    attrs=primitive['attributes']
    if 'COLOR_0' not in attrs:raise ValueError('Elegir el GLB con color por vertice')
    v=atributo(attrs['POSITION']).astype(np.float32)
    f=atributo(primitive['indices']).reshape(-1,3).astype(np.int64)
    c=atributo(attrs['COLOR_0'])[:,:3].astype(np.float32)
    if len(c)!=len(v):raise ValueError('COLOR_0 no corresponde a los vertices')
    return v,f,c
