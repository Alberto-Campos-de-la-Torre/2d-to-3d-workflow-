"""Lectura de .glb y escritura de .stl con numpy, sin el importador glTF de Blender.

El importador de Blender es Python y necesita decenas de GB con las mallas grandes de
TRELLIS.2 (llego a pedir 53 GB con un GLB de 2 GB). Aqui se mapea el fichero con
np.memmap y solo se leen los accesores necesarios.
"""
import json
import struct

import numpy as np


def escribir_stl(destino, vertices, triangulos):
    """STL binario: cabecera de 80 bytes, numero de caras y 50 bytes por cara."""
    a, b, c = vertices[triangulos[:, 0]], vertices[triangulos[:, 1]], vertices[triangulos[:, 2]]
    normales = np.cross(b - a, c - a)
    largo = np.linalg.norm(normales, axis=1, keepdims=True)
    normales = np.divide(normales, largo, out=np.zeros_like(normales), where=largo > 0)
    registro = np.zeros(len(triangulos), dtype=np.dtype([
        ("n", "<f4", 3), ("v1", "<f4", 3), ("v2", "<f4", 3), ("v3", "<f4", 3), ("attr", "<u2")]))
    registro["n"], registro["v1"], registro["v2"], registro["v3"] = normales, a, b, c
    with open(destino, "wb") as f:
        f.write(b"Exo filaments".ljust(80, b" "))
        f.write(struct.pack("<I", len(triangulos)))
        f.write(registro.tobytes())


def leer_stl(ruta):
    """Lee un STL binario y devuelve (vertices, triangulos) sin soldar duplicados."""
    with open(ruta, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        datos = np.frombuffer(f.read(n * 50), dtype=np.dtype([
            ("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")]), count=n)
    vertices = datos["v"].reshape(-1, 3).astype(np.float32)
    return vertices, np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)

TIPOS = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
COMPONENTES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _accesor(cabecera, mapa, indice):
    acc = cabecera["accessors"][indice]
    vista = cabecera["bufferViews"][acc["bufferView"]]
    tipo = TIPOS[acc["componentType"]]
    ancho = COMPONENTES[acc["type"]] * np.dtype(tipo).itemsize
    paso = vista.get("byteStride") or ancho
    if paso != ancho:
        raise ValueError("buferes entrelazados no soportados")
    desplazamiento = vista.get("byteOffset", 0) + acc.get("byteOffset", 0)
    crudo = np.asarray(mapa[desplazamiento:desplazamiento + acc["count"] * ancho])
    return crudo.view(tipo).reshape(acc["count"], -1)


def leer_glb(ruta, atributos=("POSITION",)):
    """Devuelve (dict de atributos apilados, triangulos Mx3 int32, cabecera JSON).

    Los atributos ausentes en el archivo simplemente no aparecen en el resultado.
    Los colores (COLOR_0) se normalizan a float32 en 0..1.
    """
    with open(ruta, "rb") as f:
        magic, _version, _longitud = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise ValueError("no es un archivo GLB")
        json_len, _tipo = struct.unpack("<II", f.read(8))
        cabecera = json.loads(f.read(json_len))
        bin_len, _tipo = struct.unpack("<II", f.read(8))
        inicio_bin = f.tell()
    mapa = np.memmap(ruta, dtype=np.uint8, mode="r", offset=inicio_bin, shape=(bin_len,))

    acumulado = {a: [] for a in atributos}
    triangulos, base = [], 0
    for malla in cabecera.get("meshes", []):
        for prim in malla.get("primitives", []):
            if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                continue
            n_verts = cabecera["accessors"][prim["attributes"]["POSITION"]]["count"]
            for atributo in atributos:
                if atributo in prim["attributes"]:
                    datos = np.array(_accesor(cabecera, mapa, prim["attributes"][atributo]))
                    if atributo.startswith("COLOR") and datos.dtype != np.float32:
                        maximo = np.iinfo(datos.dtype).max
                        datos = datos.astype(np.float32) / maximo
                    acumulado[atributo].append(datos)
            triangulos.append(np.array(_accesor(cabecera, mapa, prim["indices"]), dtype=np.int32).reshape(-1, 3) + base)
            base += n_verts
    if not triangulos:
        raise ValueError("el GLB no tiene triangulos")

    resultado = {a: np.concatenate(v) for a, v in acumulado.items() if v}
    return resultado, np.concatenate(triangulos), cabecera


def leer_imagen_base(ruta, cabecera):
    """Devuelve los bytes de la primera imagen embebida (textura base), o None."""
    if not cabecera.get("images"):
        return None
    imagen = cabecera["images"][0]
    if "bufferView" not in imagen:
        return None
    with open(ruta, "rb") as f:
        f.read(12)
        json_len, _ = struct.unpack("<II", f.read(8))
        f.read(json_len)
        _bin_len, _ = struct.unpack("<II", f.read(8))
        inicio_bin = f.tell()
        vista = cabecera["bufferViews"][imagen["bufferView"]]
        f.seek(inicio_bin + vista.get("byteOffset", 0))
        return f.read(vista["byteLength"])
