"""Render de uno o varios STL con la misma camara, para comparar acabados.

  blender.exe -b -P scripts\\render_stl.py -- <carpeta o archivo.stl> <carpeta_salida>
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
origen, salida = Path(argv[0]), Path(argv[1])
salida.mkdir(parents=True, exist_ok=True)
archivos = [origen] if origen.is_file() else sorted(origen.glob("*.stl"))

for archivo in archivos:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.stl_import(filepath=str(archivo))
    obj = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]

    caja = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
    minimo = Vector((min(p.x for p in caja), min(p.y for p in caja), min(p.z for p in caja)))
    maximo = Vector((max(p.x for p in caja), max(p.y for p in caja), max(p.z for p in caja)))
    centro, radio = (minimo + maximo) / 2, max(maximo - minimo)

    mat = bpy.data.materials.new("qc")
    mat.diffuse_color = (0.76, 0.75, 0.72, 1.0)
    obj.data.materials.append(mat)

    escena = bpy.context.scene
    escena.render.engine = "BLENDER_WORKBENCH"
    escena.display.shading.light = "STUDIO"
    escena.display.shading.show_cavity = True   # marca los escalones de la rejilla
    escena.render.resolution_x = escena.render.resolution_y = 600
    escena.render.image_settings.file_format = "PNG"

    diana = bpy.data.objects.new("diana", None)
    diana.location = centro
    escena.collection.objects.link(diana)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    escena.collection.objects.link(cam)
    escena.camera = cam
    cam.location = centro + Vector((0.9, -1.1, 0.5)).normalized() * radio * 1.6
    con = cam.constraints.new("TRACK_TO")
    con.target = diana
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    escena.render.filepath = str(salida / f"{archivo.stem}.png")
    bpy.ops.render.render(write_still=True)
    print("LISTO:", archivo.stem, flush=True)
