"""Prueba los nodos de Exo filaments sin pasar por la GPU: carga un GLB ya generado.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_nodos_directo.py [modelo.glb]
"""
import asyncio
import sys
from pathlib import Path

COMFY = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI")
sys.path.insert(0, str(COMFY))
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from comfy_api.latest._util.geometry_types import MESH  # noqa: E402
from custom_nodes.exo_filaments.nodes import (ExoGuardarImpresion, ExoInformeImpresion,  # noqa: E402
                                              ExoPaletaFilamentos)
from glb_lector import leer_glb  # noqa: E402
from color_util import lineal_a_srgb  # noqa: E402

ruta = Path(sys.argv[1] if len(sys.argv) > 1 else
            r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\output\3d\trellis2\images_vertices_00002.glb")
atributos, tri, _ = leer_glb(ruta, ("POSITION", "COLOR_0"))
print(f"entrada: {ruta.name} · {len(tri)} caras · color={'COLOR_0' in atributos}")

malla = MESH(
    vertices=torch.from_numpy(atributos["POSITION"].astype(np.float32)).unsqueeze(0),
    faces=torch.from_numpy(tri.astype(np.int64)).unsqueeze(0),
    vertex_colors=torch.from_numpy(atributos["COLOR_0"][:, :3].astype(np.float32)).unsqueeze(0),
)


def ejecutar(nodo, **kwargs):
    salida = nodo.execute(**kwargs)
    return salida.result if hasattr(salida, "result") else salida


print("\n=== Paleta de filamentos ===")
resultado = ejecutar(ExoPaletaFilamentos, mesh=malla, paleta="#c41e3a,#ffd500,#0046ad,#1a1a1a",
                     colores=4, peso_luz=0.25, min_mancha=0.3, suavizar_bordes=3)
coloreada, informe = resultado[0], resultado[1]
print(informe)

print("\n=== Paleta automatica (sin indicar colores) ===")
auto = ejecutar(ExoPaletaFilamentos, mesh=malla, paleta="", colores=5,
                peso_luz=0.25, min_mancha=0.3, suavizar_bordes=3)
print(auto[1])

print("\n=== Informe de impresion ===")
escalada, informe2, peso = ejecutar(ExoInformeImpresion, mesh=coloreada, altura_mm=60.0,
                                    material="PLA", relleno=15.0, pared_mm=1.2)
print(informe2)

print("\n=== Guardar para imprimir ===")
rutas = ejecutar(ExoGuardarImpresion, mesh=escalada, nombre="exo/prueba_directa", guardar_obj=True)
print(rutas[0] if isinstance(rutas, tuple) else rutas)
