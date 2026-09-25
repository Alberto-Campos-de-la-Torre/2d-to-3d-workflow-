"""Analiza y renderiza UNA malla .glb, sin usar el importador glTF de Blender.

  "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe" -b -P scripts\\revisar_glb.py -- <archivo.glb> <carpeta_salida>

El importador glTF de Blender es Python y necesita decenas de GB con las mallas de
TRELLIS.2 (hasta 2 GB de archivo): congelaba el equipo. Aqui se leen los buferes del
GLB con numpy (memmap, sin copiar el archivo) y se construye la malla directamente.
Una malla por proceso: al terminar, Windows recupera toda la memoria.
"""
import json
import struct
import sys
from pathlib import Path

import bpy
import numpy as np

TIPOS = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
COMPONENTES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
LADO = 400
VISTAS = {"frente": (1.0, -1.2, 0.55), "detras": (-1.0, 1.2, 0.55)}
LIMITE_PIEZAS = 5_000_000      # caras: por encima no se cuentan piezas sueltas
LIMITE_ARISTAS = 25_000_000    # caras: por encima no se cuentan aristas abiertas


def leer_glb(ruta):
    """Devuelve (posiciones Nx3 float32, triangulos Mx3 int32) juntando todas las primitivas."""
    with open(ruta, "rb") as f:
        magic, _version, _longitud = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise ValueError("no es un archivo GLB")
        json_len, _tipo = struct.unpack("<II", f.read(8))
        cabecera = json.loads(f.read(json_len))
        bin_len, _tipo = struct.unpack("<II", f.read(8))
        inicio_bin = f.tell()

    mapa = np.memmap(ruta, dtype=np.uint8, mode="r", offset=inicio_bin, shape=(bin_len,))

    def accesor(indice):
        acc = cabecera["accessors"][indice]
        vista = cabecera["bufferViews"][acc["bufferView"]]
        if vista.get("byteStride") not in (None, 0) and acc["type"] != "SCALAR":
            paso = vista["byteStride"]
            ancho = COMPONENTES[acc["type"]] * np.dtype(TIPOS[acc["componentType"]]).itemsize
            if paso != ancho:
                raise ValueError("buferes entrelazados no soportados")
        desplazamiento = vista.get("byteOffset", 0) + acc.get("byteOffset", 0)
        tipo = TIPOS[acc["componentType"]]
        n = acc["count"] * COMPONENTES[acc["type"]]
        bytes_totales = n * np.dtype(tipo).itemsize
        crudo = np.asarray(mapa[desplazamiento:desplazamiento + bytes_totales])
        return crudo.view(tipo).reshape(acc["count"], -1)

    posiciones, triangulos, base = [], [], 0
    for malla in cabecera.get("meshes", []):
        for prim in malla.get("primitives", []):
            if prim.get("mode", 4) != 4:  # solo triangulos
                continue
            pos = np.array(accesor(prim["attributes"]["POSITION"]), dtype=np.float32)
            idx = np.array(accesor(prim["indices"]), dtype=np.int32).reshape(-1, 3)
            posiciones.append(pos)
            triangulos.append(idx + base)
            base += len(pos)
    if not posiciones:
        raise ValueError("el GLB no tiene triangulos")
    return np.concatenate(posiciones), np.concatenate(triangulos)


def estadisticas(pos, tri):
    n_verts, n_caras = len(pos), len(tri)

    # Por bloques: con 60M de triangulos, hacerlo de golpe pide varios GB de golpe.
    acumulado = 0.0
    for inicio in range(0, n_caras, 2_000_000):
        bloque = tri[inicio:inicio + 2_000_000]
        a = pos[bloque[:, 0]].astype(np.float64)
        b = pos[bloque[:, 1]].astype(np.float64)
        c = pos[bloque[:, 2]].astype(np.float64)
        acumulado += np.einsum("ij,ij->i", a, np.cross(b, c)).sum()
    volumen = abs(acumulado / 6.0)

    no_manifold = -1
    if n_caras <= LIMITE_ARISTAS:
        aristas = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
        aristas.sort(axis=1)
        clave = aristas[:, 0].astype(np.int64) * n_verts + aristas[:, 1]
        del aristas
        _, cuentas = np.unique(clave, return_counts=True)
        no_manifold = int(np.count_nonzero(cuentas != 2))
        del clave, cuentas

    piezas, pct_principal = -1, -1.0
    if n_caras <= LIMITE_PIEZAS:
        padre = np.arange(n_verts, dtype=np.int64)
        pares = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
        for _ in range(100):
            ra, rb = padre[pares[:, 0]], padre[pares[:, 1]]
            distintos = ra != rb
            if not distintos.any():
                break
            menor = np.minimum(ra, rb)[distintos]
            np.minimum.at(padre, ra[distintos], menor)
            np.minimum.at(padre, rb[distintos], menor)
            padre = padre[padre]
        # Solo cuentan los vertices usados por algun triangulo: los sueltos no son piezas.
        usados = np.zeros(n_verts, dtype=bool)
        usados[tri.ravel()] = True
        _, tam = np.unique(padre[usados], return_counts=True)
        piezas = int(len(tam))
        pct_principal = round(100 * int(tam.max()) / int(usados.sum()), 1)

    dim = pos.max(axis=0) - pos.min(axis=0)
    return {
        "caras": n_caras,
        "vertices": n_verts,
        "aristas_no_manifold": no_manifold,
        "piezas_sueltas": piezas,
        "pct_verts_pieza_principal": pct_principal,
        "dim_relativas": [round(float(d), 3) for d in dim],
        "volumen": round(float(volumen), 4),
    }


def poner_colores(me, colores):
    """Color por vertice para el render (los GLB de TRELLIS.2 lo traen en COLOR_0)."""
    capa = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    rgba = np.ones((len(colores), 4), dtype=np.float32)
    rgba[:, :3] = colores[:, :3]
    capa.data.foreach_set("color", rgba.ravel())


def construir_malla(pos, tri):
    me = bpy.data.meshes.new("malla")
    me.vertices.add(len(pos))
    me.vertices.foreach_set("co", pos.ravel())
    me.loops.add(tri.size)
    me.loops.foreach_set("vertex_index", tri.astype(np.int32).ravel())
    me.polygons.add(len(tri))
    me.polygons.foreach_set("loop_start", (np.arange(len(tri), dtype=np.int32) * 3))
    me.update()
    obj = bpy.data.objects.new("malla", me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def preparar_escena(obj, pos):
    minimo, maximo = pos.min(axis=0), pos.max(axis=0)
    escala = 2.0 / float((maximo - minimo).max())
    obj.scale = (escala, escala, escala)
    obj.location = tuple(-(minimo + maximo) / 2.0 * escala)

    mat = bpy.data.materials.new("qc")
    mat.diffuse_color = (0.75, 0.75, 0.78, 1.0)
    obj.data.materials.append(mat)

    escena = bpy.context.scene
    escena.render.engine = "BLENDER_WORKBENCH"
    escena.display.shading.light = "STUDIO"
    escena.display.shading.show_cavity = True
    escena.render.resolution_x = escena.render.resolution_y = LADO
    escena.render.image_settings.file_format = "PNG"

    diana = bpy.data.objects.new("diana", None)
    escena.collection.objects.link(diana)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("cam", cam_data)
    escena.collection.objects.link(cam)
    escena.camera = cam
    con = cam.constraints.new("TRACK_TO")
    con.target = diana
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return cam


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    archivo = Path(argv[0])
    salida = Path(argv[1])
    salida.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).parent))
    from glb_lector import leer_glb as leer_atributos
    atributos, tri, _cabecera = leer_atributos(archivo, ("POSITION", "COLOR_0"))
    pos = atributos["POSITION"].astype(np.float32)
    colores = atributos.get("COLOR_0")
    datos = estadisticas(pos, tri)
    datos["archivo"] = archivo.name
    print("STATS:", json.dumps(datos), flush=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = construir_malla(pos, tri)
    cam = preparar_escena(obj, pos)
    if colores is not None:
        poner_colores(obj.data, colores)
        bpy.context.scene.display.shading.color_type = "VERTEX"
        bpy.context.scene.display.shading.show_cavity = False
    for vista, direccion in VISTAS.items():
        d = np.array(direccion, dtype=float)
        cam.location = tuple(d / np.linalg.norm(d) * 6.0)
        bpy.context.view_layer.update()
        bpy.context.scene.render.filepath = str(salida / f"{archivo.stem}_{vista}.png")
        bpy.ops.render.render(write_still=True)
    print("LISTO:", archivo.name, flush=True)


main()
