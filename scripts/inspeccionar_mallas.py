"""Control de calidad de las mallas generadas: estadisticas + renders de contacto.

Uso:
  "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe" -b -P scripts\\inspeccionar_mallas.py -- [carpeta_glb] [carpeta_salida]

Por cada .glb: n de caras/vertices, aristas non-manifold (agujeros), numero de piezas
sueltas, proporciones y volumen. Renderiza dos vistas (3/4 frontal y 3/4 trasera) y
monta dos hojas de contacto para revisarlas de un vistazo.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CARPETA_GLB = Path(argv[0]) if argv else Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\output\3d")
SALIDA = Path(argv[1]) if len(argv) > 1 else Path(r"D:\AI3D\pruebas\revision")
SALIDA.mkdir(parents=True, exist_ok=True)
LADO = 400  # px por celda
VISTAS = {"frente": (1.0, -1.2, 0.55), "detras": (-1.0, 1.2, 0.55)}


def limpiar_escena():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def importar(ruta):
    bpy.ops.import_scene.gltf(filepath=str(ruta))
    mallas = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in mallas:
        o.select_set(True)
    bpy.context.view_layer.objects.active = mallas[0]
    if len(mallas) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


LIMITE_PIEZAS = 5_000_000  # por encima de esto no se cuentan piezas sueltas (coste de memoria)


def estadisticas(obj):
    # Todo con numpy sobre los datos de la malla: bmesh duplicaba la malla en memoria y
    # reventaba con las salidas de TRELLIS.2 (decenas de millones de caras).
    me = obj.data
    n_verts, n_aristas, n_caras = len(me.vertices), len(me.edges), len(me.polygons)

    # Aristas abiertas / no-manifold: cada arista sana pertenece a exactamente 2 caras.
    lazos = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("edge_index", lazos)
    caras_por_arista = np.bincount(lazos, minlength=n_aristas)
    no_manifold = int(np.count_nonzero(caras_por_arista != 2))

    # Volumen: suma de tetraedros con vertice en el origen sobre los triangulos.
    me.calc_loop_triangles()
    tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tri)
    co = np.empty(n_verts * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    tri = tri.reshape(-1, 3)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    volumen = abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    # Piezas sueltas: union-find vectorizado por saltos de puntero.
    piezas, pct_principal = -1, -1.0
    if n_caras <= LIMITE_PIEZAS:
        ar = np.empty(n_aristas * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ar)
        ar = ar.reshape(-1, 2)
        padre = np.arange(n_verts, dtype=np.int32)
        for _ in range(100):
            ra, rb = padre[ar[:, 0]], padre[ar[:, 1]]
            distintos = ra != rb
            if not distintos.any():
                break
            menor = np.minimum(ra, rb)[distintos]
            np.minimum.at(padre, ra[distintos], menor)
            np.minimum.at(padre, rb[distintos], menor)
            padre = padre[padre]
        raices, tam = np.unique(padre, return_counts=True)
        piezas = int(len(raices))
        pct_principal = round(100 * int(tam.max()) / max(n_verts, 1), 1)

    return {
        "caras": n_caras,
        "vertices": n_verts,
        "aristas_no_manifold": no_manifold,
        "piezas_sueltas": piezas,
        "pct_verts_pieza_principal": pct_principal,
        "dim_relativas": [round(d, 3) for d in obj.dimensions],
        "volumen": round(float(volumen), 4),
    }


def preparar_render(obj):
    # Normaliza el objeto a un cubo de lado 2 centrado en el origen.
    dim = max(obj.dimensions)
    obj.scale = [2.0 / dim] * 3
    bpy.context.view_layer.update()
    bpy.ops.object.transform_apply(scale=True)
    # Centro de la caja envolvente (recorrer todos los vertices en Python es inviable
    # con las mallas grandes de TRELLIS.2).
    caja = np.array([list(v) for v in obj.bound_box], dtype=np.float64)
    centro = (caja.min(axis=0) + caja.max(axis=0)) / 2.0
    obj.location = tuple(-centro)
    bpy.context.view_layer.update()

    mat = bpy.data.materials.new("qc")
    mat.diffuse_color = (0.75, 0.75, 0.78, 1.0)
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    escena = bpy.context.scene
    escena.render.engine = "BLENDER_WORKBENCH"
    escena.display.shading.light = "STUDIO"
    escena.display.shading.show_cavity = True  # resalta huecos y ruido de superficie
    escena.render.resolution_x = escena.render.resolution_y = LADO
    escena.render.film_transparent = False
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


def render(cam, direccion, destino):
    d = np.array(direccion, dtype=float)
    d /= np.linalg.norm(d)
    cam.location = tuple(d * 6.0)
    bpy.context.view_layer.update()
    bpy.context.scene.render.filepath = str(destino)
    bpy.ops.render.render(write_still=True)


def hoja_contacto(rutas, etiquetas, destino, columnas=4):
    filas = math.ceil(len(rutas) / columnas)
    lienzo = np.zeros((filas * LADO, columnas * LADO, 4), dtype=np.float32)
    lienzo[..., 3] = 1.0
    for i, ruta in enumerate(rutas):
        img = bpy.data.images.load(str(ruta))
        pix = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)
        f, c = divmod(i, columnas)
        lienzo[f * LADO:(f + 1) * LADO, c * LADO:(c + 1) * LADO] = pix
        bpy.data.images.remove(img)
    # El origen de imagen en Blender esta abajo: se invierte el orden de filas por bloques.
    bloques = [lienzo[f * LADO:(f + 1) * LADO] for f in range(filas)][::-1]
    lienzo = np.concatenate(bloques, axis=0) if bloques else lienzo
    salida = bpy.data.images.new("hoja", width=columnas * LADO, height=filas * LADO)
    salida.pixels = lienzo.ravel().tolist()
    salida.filepath_raw = str(destino)
    salida.file_format = "PNG"
    salida.save()
    print("HOJA:", destino, "orden:", etiquetas)


def main():
    archivos = sorted(CARPETA_GLB.glob("*.glb")) or sorted(CARPETA_GLB.rglob("*.glb"))
    informe, renders = [], {v: [] for v in VISTAS}
    for ruta in archivos:
        print("=== ", ruta.name, flush=True)
        limpiar_escena()
        try:
            obj = importar(ruta)
            datos = estadisticas(obj)
            cam = preparar_render(obj)
            # El prefijo de carpeta evita choques cuando se comparan varios motores.
            clave = f"{ruta.parent.name}_{ruta.stem}" if ruta.parent != CARPETA_GLB else ruta.stem
            for vista, direccion in VISTAS.items():
                destino = SALIDA / f"{clave}_{vista}.png"
                render(cam, direccion, destino)
                renders[vista].append(destino)
            datos["archivo"] = ruta.name
            informe.append(datos)
            print("STATS:", json.dumps(datos))
        except Exception as e:
            print("ERROR:", ruta.name, e)

    (SALIDA / "informe.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    for vista, rutas in renders.items():
        if rutas:
            hoja_contacto(rutas, [r.stem for r in rutas], SALIDA / f"hoja_{vista}.png")


main()
