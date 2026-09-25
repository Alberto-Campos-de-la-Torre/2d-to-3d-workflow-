"""Comprueba que las piezas guardadas quedan de pie (altura en Z, como espera el laminador).

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_orientacion.py
"""
import sys
from pathlib import Path

COMFY = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI")
sys.path.insert(0, str(COMFY))
sys.path.insert(0, r"D:\AI3D\scripts")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from comfy_api.latest._util.geometry_types import MESH  # noqa: E402
import types  # noqa: E402

# El paquete registra de paso las rutas del estudio, que necesitan el servidor en marcha;
# fuera de ComfyUI se sustituye por un modulo vacio.
sys.modules["custom_nodes.exo_filaments.estudio"] = types.ModuleType("estudio")
from custom_nodes.exo_filaments.nodes import ExoGuardarImpresion  # noqa: E402
from glb_lector import leer_glb, leer_stl  # noqa: E402

ruta = Path(sys.argv[1] if len(sys.argv) > 1 else
            COMFY / "output" / "3d" / "texto" / "pieza_vertices_00001.glb")
atributos, tri, _ = leer_glb(ruta, ("POSITION", "COLOR_0"))
pos = atributos["POSITION"].astype(np.float32)
malla = MESH(vertices=torch.from_numpy(pos).unsqueeze(0),
             faces=torch.from_numpy(tri.astype(np.int64)).unsqueeze(0),
             vertex_colors=torch.from_numpy(atributos["COLOR_0"][:, :3].astype(np.float32)).unsqueeze(0))

antes = pos.max(axis=0) - pos.min(axis=0)
print(f"entrada     ancho {antes[0]:.3f} · {antes[1]:.3f} · {antes[2]:.3f}   (eje mas largo: {'XYZ'[int(antes.argmax())]})")

for de_pie in (False, True):
    salida = ExoGuardarImpresion.execute(mesh=malla, nombre=f"orientacion/prueba_{'z' if de_pie else 'y'}",
                                         guardar_obj=False, poner_de_pie=de_pie)
    archivo = Path(salida.result[0].split("\n")[0])
    v, _ = leer_stl(archivo)
    medidas = v.max(axis=0) - v.min(axis=0)
    eje = "XYZ"[int(medidas.argmax())]
    estado = "DE PIE (correcto)" if eje == "Z" else "tumbada"
    print(f"poner_de_pie={str(de_pie):<5} {medidas[0]:.3f} · {medidas[1]:.3f} · {medidas[2]:.3f}   eje mas largo: {eje} -> {estado}")
