"""Render rapido de un OBJ con sus materiales, para revisar el color antes de laminar.

  blender.exe -b -P scripts\\render_obj.py -- <archivo.obj> <salida.png>
"""
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
archivo, destino = Path(argv[0]), Path(argv[1])

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=str(archivo))

objetos = [o for o in bpy.context.scene.objects if o.type == "MESH"]
caja_min = Vector((min(min((o.matrix_world @ Vector(v)).x for v in o.bound_box) for o in objetos),
                   min(min((o.matrix_world @ Vector(v)).y for v in o.bound_box) for o in objetos),
                   min(min((o.matrix_world @ Vector(v)).z for v in o.bound_box) for o in objetos)))
caja_max = Vector((max(max((o.matrix_world @ Vector(v)).x for v in o.bound_box) for o in objetos),
                   max(max((o.matrix_world @ Vector(v)).y for v in o.bound_box) for o in objetos),
                   max(max((o.matrix_world @ Vector(v)).z for v in o.bound_box) for o in objetos)))
centro = (caja_min + caja_max) / 2
radio = max(caja_max - caja_min)

escena = bpy.context.scene
escena.render.engine = "BLENDER_WORKBENCH"
escena.display.shading.light = "STUDIO"
escena.display.shading.color_type = "MATERIAL"
escena.render.resolution_x = escena.render.resolution_y = 700
escena.render.image_settings.file_format = "PNG"

diana = bpy.data.objects.new("diana", None)
diana.location = centro
escena.collection.objects.link(diana)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
escena.collection.objects.link(cam)
escena.camera = cam
cam.location = centro + Vector((1.0, -1.2, 0.75)).normalized() * radio * 2.6
con = cam.constraints.new("TRACK_TO")
con.target = diana
con.track_axis = "TRACK_NEGATIVE_Z"
con.up_axis = "UP_Y"

escena.render.filepath = str(destino)
bpy.ops.render.render(write_still=True)
print("LISTO:", destino)
