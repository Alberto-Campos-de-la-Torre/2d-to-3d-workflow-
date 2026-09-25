"""Deja una malla generada por IA lista para imprimir: cerrada, limpia y a escala.

  "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe" -b -P scripts\\preparar_impresion.py -- <entrada.glb|stl> [opciones]

Opciones:
  --altura-mm 80       altura final de la pieza (se aplica al eje mas largo)
  --caras 200000       limite de caras del STL final
  --detalle 350        resolucion del remallado por voxeles (mas alto = mas detalle)
  --min-pieza 1.0      descarta trozos sueltos por debajo de este % de la pieza principal
  --base-plana 0       corta la base a esta altura en mm para que apoye (0 = no cortar)
  --grosor-min 1.2     grosor de pared minimo a vigilar, en mm
  --relleno 15         relleno en % para estimar el peso
  --salida <ruta.stl>  por defecto, junto a la entrada, como <nombre>_listo.stl

Imprime un informe JSON con medidas, estanqueidad, zonas finas y peso estimado.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).parent))
from color_util import (agrupar, escribir_obj_color, hex_a_rgb, lineal_a_srgb, quitar_islas,
                        suavizar_etiquetas, vecindad)
from glb_lector import escribir_stl, leer_glb, leer_stl

DENSIDAD = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "TPU": 1.21}  # g/cm3
_reloj = [time.time()]


def paso(texto):
    """Traza con tiempos: sin esto no se ve que etapa se atasca con mallas grandes."""
    ahora = time.time()
    print(f"[{ahora - _reloj[0]:6.1f}s] {texto}", flush=True)
    _reloj[0] = ahora


def cargar(ruta):
    """Devuelve (vertices, triangulos, color por vertice o None)."""
    if ruta.suffix.lower() == ".stl":
        pos, tri = leer_stl(ruta)
        return pos, tri, None
    atributos, tri, _ = leer_glb(ruta, ("POSITION", "COLOR_0"))
    color = atributos.get("COLOR_0")
    if color is not None:
        color = lineal_a_srgb(color[:, :3].astype(np.float32))
    return atributos["POSITION"].astype(np.float32), tri, color


def trasladar_color(obj, pos_original, color_original):
    """Pasa el color del modelo original a la malla ya reparada.

    El remallado crea vertices nuevos, asi que cada uno toma el color del vertice
    original mas cercano. Sin esto, el modelo reparado sale gris.
    """
    from mathutils.kdtree import KDTree
    arbol = KDTree(len(pos_original))
    for i, punto in enumerate(pos_original):
        arbol.insert(Vector(punto.tolist()), i)
    arbol.balance()
    me = obj.data
    destino = np.empty((len(me.vertices), 3), dtype=np.float32)
    for i, vertice in enumerate(me.vertices):
        _, indice, _ = arbol.find(vertice.co)
        destino[i] = color_original[indice]
    return destino


def quitar_trozos_sueltos(pos, tri, minimo_pct):
    """Elimina fragmentos flotantes: la camara salio con 315 y el flexo con 192."""
    padre = np.arange(len(pos), dtype=np.int32)
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

    grupo_cara = padre[tri[:, 0]]
    grupos, cuentas = np.unique(grupo_cara, return_counts=True)
    umbral = cuentas.max() * minimo_pct / 100.0
    conservados = grupos[cuentas >= umbral]
    mantener = np.isin(grupo_cara, conservados)
    tri = tri[mantener]
    usados, remapeo = np.unique(tri, return_inverse=True)
    return (pos[usados], remapeo.reshape(-1, 3).astype(np.int32),
            int(len(grupos)), int(len(conservados)), usados)


def construir(pos, tri):
    me = bpy.data.meshes.new("pieza")
    me.vertices.add(len(pos))
    me.vertices.foreach_set("co", pos.ravel())
    me.loops.add(tri.size)
    me.loops.foreach_set("vertex_index", tri.ravel())
    me.polygons.add(len(tri))
    me.polygons.foreach_set("loop_start", np.arange(len(tri), dtype=np.int32) * 3)
    me.update()
    me.validate(verbose=False)
    obj = bpy.data.objects.new("pieza", me)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj


def aplicar(obj, modificador):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modificador.name)


def escalar(obj, altura_mm):
    dim = max(obj.dimensions)
    factor = altura_mm / dim
    obj.scale = (factor, factor, factor)
    bpy.ops.object.transform_apply(scale=True)
    return factor


def cortar_base(obj, altura_corte):
    """Corta por debajo para que la pieza apoye en la cama en vez de sobre una punta."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    z_min = min(v.co.z for v in bm.verts)
    plano = Vector((0, 0, z_min + altura_corte))
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    resultado = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=plano, plane_no=Vector((0, 0, 1)),
                                       clear_inner=True, use_snap_center=False)
    aristas = [e for e in resultado["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if aristas:
        bmesh.ops.holes_fill(bm, edges=aristas)
    bm.to_mesh(me)
    bm.free()


def contar_aristas_abiertas(me):
    """Aristas que no pertenecen a exactamente dos caras (agujeros o bordes)."""
    lazos = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("edge_index", lazos)
    return int(np.count_nonzero(np.bincount(lazos, minlength=len(me.edges)) != 2))


def limpiar(obj, tapar_agujeros=False):
    """Suelda vertices duplicados, quita sueltos y recalcula normales.

    El tapado de agujeros va aparte y desactivado por defecto: 'triangle_fill' tarda
    muchos minutos cuando hay miles de bordes abiertos, y no hace falta, porque el
    remallado por voxeles cierra igual (la camara entro con 2.631 aristas abiertas y
    salio solida y estanca).
    """
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    if tapar_agujeros:
        bordes = [e for e in bm.edges if len(e.link_faces) < 2]
        if bordes:
            bmesh.ops.holes_fill(bm, edges=bordes)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return contar_aristas_abiertas(me)


def medir(obj, grosor_min, muestras=4000):
    """Estanqueidad, volumen, area y zonas por debajo del grosor minimo."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    abiertas = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    volumen = bm.calc_volume(signed=False)
    area = sum(f.calc_area() for f in bm.faces)
    bm.free()

    # Grosor local: desde el centro de cada cara, un rayo hacia dentro; lo que tarda en
    # salir por el otro lado es el grosor en ese punto.
    me.calc_loop_triangles()
    bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices],
                               [tuple(p.vertices) for p in me.polygons], all_triangles=False)
    caras = list(me.polygons)
    salto = max(1, len(caras) // muestras)
    # Se pondera por superficie, no por numero de caras: una placa fina tiene pocas caras
    # grandes y muchas de canto, y contando caras salia un enganoso 33 %.
    area_fina, area_medida, minimo = 0.0, 0.0, float("inf")
    margen = 0.02  # mm: si no, el rayo vuelve a chocar con la cara de la que sale
    for cara in caras[::salto]:
        origen = cara.center - cara.normal * margen
        direccion = -cara.normal
        recorrido, golpe = margen, bvh.ray_cast(origen, direccion)
        # Se ignoran los choques pegados al origen (la propia cara y sus vecinas).
        while golpe[0] is not None and (golpe[0] - origen).length < margen:
            origen = golpe[0] + direccion * margen
            recorrido += (golpe[0] - origen).length + margen
            golpe = bvh.ray_cast(origen, direccion)
        if golpe[0] is None:
            continue
        grosor = recorrido + (golpe[0] - origen).length
        superficie = cara.area
        area_medida += superficie
        minimo = min(minimo, grosor)
        if grosor < grosor_min:
            area_fina += superficie
    return {
        "aristas_abiertas": abiertas,
        "cerrada": abiertas == 0,
        "volumen_cm3": round(volumen / 1000.0, 2),
        "area_cm2": round(area / 100.0, 2),
        "grosor_min_mm": round(minimo, 2) if area_medida else None,
        "pct_zonas_finas": round(100 * area_fina / area_medida, 1) if area_medida else None,
    }


def estimar_peso(volumen_cm3, area_cm2, relleno_pct, pared_mm, material="PLA"):
    """Peso aproximado: cascara solida + relleno en el interior."""
    volumen_pared = min(area_cm2 * pared_mm / 10.0, volumen_cm3)
    interior = max(volumen_cm3 - volumen_pared, 0.0)
    material_cm3 = volumen_pared + interior * relleno_pct / 100.0
    return round(material_cm3 * DENSIDAD[material], 1)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("entrada")
    p.add_argument("--altura-mm", type=float, default=80.0)
    p.add_argument("--caras", type=int, default=200000)
    p.add_argument("--detalle", type=int, default=350)
    p.add_argument("--min-pieza", type=float, default=1.0)
    p.add_argument("--base-plana", type=float, default=0.0)
    p.add_argument("--grosor-min", type=float, default=1.2)
    p.add_argument("--relleno", type=float, default=15.0)
    p.add_argument("--pared-mm", type=float, default=1.2)
    p.add_argument("--salida", default="")
    p.add_argument("--colores", type=int, default=4, help="maximo de filamentos si el modelo trae color")
    p.add_argument("--paleta", default="", help="colores reales de tus bobinas: '#c41e3a,#ffd500,...'")
    p.add_argument("--sin-color", action="store_true", help="no exportar el OBJ de color aunque el modelo lo traiga")
    p.add_argument("--min-mancha", type=float, default=0.3,
                   help="absorbe manchas de color que ocupen menos de este %% de las caras (0 = no tocar)")
    p.add_argument("--suavizar-color", type=int, default=3,
                   help="pasadas del filtro de mayoria sobre las caras vecinas (0 = sin suavizar)")
    p.add_argument("--tapar-agujeros", action="store_true",
                   help="tapa los agujeros antes de remallar (lento con mallas muy rotas y casi nunca necesario)")
    args = p.parse_args(argv)

    entrada = Path(args.entrada)
    salida = Path(args.salida) if args.salida else entrada.parent / f"{entrada.stem}_listo.stl"
    salida.parent.mkdir(parents=True, exist_ok=True)

    pos, tri, color = cargar(entrada)
    caras_inicio = len(tri)
    pos, tri, piezas, conservadas, usados = quitar_trozos_sueltos(pos, tri, args.min_pieza)
    paso(f"trozos sueltos: {piezas} encontrados, {conservadas} conservados")
    if color is not None:
        color = color[usados]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = construir(pos, tri)
    factor = escalar(obj, args.altura_mm)
    abiertas_tras_cierre = limpiar(obj, args.tapar_agujeros)
    paso(f"limpieza: quedan {abiertas_tras_cierre} aristas abiertas antes de remallar")

    # Remallado por voxeles: es lo que convierte una malla con agujeros y caras sueltas
    # en un solido cerrado. Sin esto el laminador rellena mal o deja huecos.
    remallado = obj.modifiers.new("remallado", "REMESH")
    remallado.mode = "VOXEL"
    remallado.voxel_size = max(obj.dimensions) / args.detalle
    remallado.use_smooth_shade = False
    aplicar(obj, remallado)

    abiertas_tras_remallado = contar_aristas_abiertas(obj.data)
    paso(f"remallado: {len(obj.data.polygons)} caras, {abiertas_tras_remallado} aristas abiertas")
    if len(obj.data.polygons) > args.caras:
        decimado = obj.modifiers.new("decimado", "DECIMATE")
        decimado.ratio = args.caras / len(obj.data.polygons)
        aplicar(obj, decimado)

    if args.base_plana > 0:
        cortar_base(obj, args.base_plana)

    paso(f"decimado: {len(obj.data.polygons)} caras")
    informe = medir(obj, args.grosor_min)
    paso("medido")
    informe.update({
        "archivo": entrada.name,
        "caras_entrada": caras_inicio,
        "caras_salida": len(obj.data.polygons),
        "trozos_encontrados": piezas,
        "trozos_conservados": conservadas,
        "aristas_abiertas_tras_cierre": abiertas_tras_cierre,
        "aristas_abiertas_tras_remallado": abiertas_tras_remallado,
        "medidas_mm": [round(d, 1) for d in obj.dimensions],
        "peso_estimado_g": estimar_peso(informe["volumen_cm3"], informe["area_cm2"], args.relleno, args.pared_mm),
        "relleno_pct": args.relleno,
    })

    me = obj.data
    me.calc_loop_triangles()
    verts = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", verts)
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tris)
    verts, tris = verts.reshape(-1, 3), tris.reshape(-1, 3)
    escribir_stl(salida, verts, tris)
    informe["salida"] = str(salida)

    # El color se traslada a la malla YA reparada: si se exporta del modelo crudo, el
    # laminador se queja de aristas no-manifold y descarta los materiales.
    if color is not None and not args.sin_color:
        paleta = [hex_a_rgb(c) for c in args.paleta.split(",") if c.strip()]
        color_final = trasladar_color(obj, pos * factor, color)
        etiquetas, centros = agrupar(color_final[tris].mean(axis=1), paleta or None, args.colores)
        if args.suavizar_color or args.min_mancha:
            vecinas = vecindad(tris)
            if args.min_mancha:
                minimo = max(1, int(len(tris) * args.min_mancha / 100.0))
                antes = etiquetas.copy()
                etiquetas = quitar_islas(tris, etiquetas, minimo, vecinas)
                paso(f"manchas absorbidas: {int(np.count_nonzero(antes != etiquetas))} caras "
                     f"(regiones de menos de {minimo} caras)")
            if args.suavizar_color:
                etiquetas = suavizar_etiquetas(tris, etiquetas, len(centros), args.suavizar_color, vecinas=vecinas)
                paso(f"bordes suavizados ({args.suavizar_color} pasadas)")
        obj_salida = salida.with_suffix(".obj")
        escribir_obj_color(obj_salida, verts, tris, etiquetas, centros, nombre=entrada.stem)
        informe["salida_color"] = str(obj_salida)
        informe["colores"] = [{"hex": "#%02x%02x%02x" % tuple((c * 255).round().astype(int)),
                               "porcentaje": round(100 * float(np.count_nonzero(etiquetas == i)) / len(tris), 1)}
                              for i, c in enumerate(centros)]

    Path(str(salida) + ".json").write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
    print("INFORME:", json.dumps(informe, ensure_ascii=False), flush=True)

    avisos = []
    if not informe["cerrada"]:
        avisos.append(f"la malla NO quedo cerrada ({informe['aristas_abiertas']} aristas abiertas)")
    if informe["pct_zonas_finas"] and informe["pct_zonas_finas"] > 5:
        avisos.append(f"{informe['pct_zonas_finas']}% de la superficie por debajo de {args.grosor_min} mm")
    if piezas > conservadas:
        avisos.append(f"se descartaron {piezas - conservadas} trozos sueltos")
    for aviso in avisos:
        print("AVISO:", aviso)
    if not avisos:
        print("OK: lista para laminar")


main()




