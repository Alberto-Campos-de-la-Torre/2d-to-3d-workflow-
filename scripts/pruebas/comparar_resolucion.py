"""Compara ajustes del nodo Solidificar: resolucion y pasadas de suavizado.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\comparar_resolucion.py [modelo.glb]

Sirve para elegir con que valores dejan de verse los escalones de la rejilla sin que la
pieza tarde de mas ni pierda las aristas vivas. Escribe un STL por combinacion.
"""
import sys
import time
import types
from pathlib import Path

COMFY = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI")
sys.path.insert(0, str(COMFY))
sys.path.insert(0, r"D:\AI3D\scripts")

import numpy as np  # noqa: E402
import torch  # noqa: E402

sys.modules["custom_nodes.exo_filaments.estudio"] = types.ModuleType("estudio")
from comfy_api.latest._util.geometry_types import MESH  # noqa: E402
from custom_nodes.exo_filaments.nodes import ExoSolidificar  # noqa: E402
from glb_lector import escribir_stl, leer_glb  # noqa: E402

SALIDA = Path(r"D:\AI3D\pruebas\resolucion")
SALIDA.mkdir(parents=True, exist_ok=True)
COMBINACIONES = [(320, 2), (320, 6), (448, 3), (512, 4), (640, 4)]

ruta = Path(sys.argv[1] if len(sys.argv) > 1 else COMFY / "output/3d/hy2.0/cakestudio-0-900x580_00001_.glb")
atributos, tri, _ = leer_glb(ruta, ("POSITION",))
malla = MESH(vertices=torch.from_numpy(atributos["POSITION"].astype(np.float32)).unsqueeze(0),
             faces=torch.from_numpy(tri.astype(np.int64)).unsqueeze(0))
print(f"{ruta.name} · {len(tri):,} caras de entrada\n")

for resolucion, suavizado in COMBINACIONES:
    inicio = time.time()
    salida = ExoSolidificar.execute(mesh=malla, resolucion=resolucion,
                                    cerrar_grietas=1, suavizar_forma=suavizado)
    datos = dict(linea.split(None, 1) for linea in salida.result[1].split("\n"))
    v = salida.result[0].vertices[0].cpu().numpy()
    f = salida.result[0].faces[0].cpu().numpy()
    escribir_stl(SALIDA / f"res{resolucion}_suave{suavizado}.stl", v, f)
    paso_mm = 80.0 / resolucion   # con una pieza de 80 mm
    print(f"resolucion {resolucion:>3} · suavizado {suavizado}: {datos['salida'].strip():<42} "
          f"escalon {paso_mm:.2f} mm · {time.time() - inicio:.0f} s")
