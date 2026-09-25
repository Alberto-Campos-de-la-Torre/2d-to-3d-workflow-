"""Comprueba el nodo Solidificar sobre varias mallas reales.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_solidificar.py

Verifica tres cosas: que la salida quede cerrada, que conserve el tamano del original
(un fallo de escala pasa desapercibido porque el informe reescala despues) y el tiempo.
"""
import sys
import time
from pathlib import Path

COMFY = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI")
sys.path.insert(0, str(COMFY))
sys.path.insert(0, r"D:\AI3D\scripts")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from comfy_api.latest._util.geometry_types import MESH  # noqa: E402
from custom_nodes.exo_filaments.nodes import ExoSolidificar  # noqa: E402
from glb_lector import leer_glb  # noqa: E402

SALIDA = COMFY / "output" / "3d"
PRUEBAS = [
    ("llave trellis2", SALIDA / "trellis2" / "single-key-isolated-EKYW4C_00002_.glb"),
    ("cubo rubik", SALIDA / "trellis2" / "images_vertices_00002.glb"),
    ("camara hy2.0", SALIDA / "hy2.0" / "cakestudio-0-900x580_00001_.glb"),
    ("girasol hy2.0", SALIDA / "hy2.0" / "istockphoto-174648035-612x612_00001_.glb"),
    ("conejo hy2.0", SALIDA / "hy2.0" / "bunny_double_negative_00001_.glb"),
    ("flexo hy2.0", SALIDA / "hy2.0" / "images (3)_00001_.glb"),
]

for nombre, ruta in PRUEBAS:
    if not ruta.exists():
        print(f"{nombre:<16} (no existe)")
        continue
    atributos, tri, _ = leer_glb(ruta, ("POSITION",))
    pos = atributos["POSITION"]
    malla = MESH(vertices=torch.from_numpy(pos.astype(np.float32)).unsqueeze(0),
                 faces=torch.from_numpy(tri.astype(np.int64)).unsqueeze(0))
    medida_antes = (pos.max(axis=0) - pos.min(axis=0)).max()

    inicio = time.time()
    salida = ExoSolidificar.execute(mesh=malla, resolucion=320, cerrar_grietas=1, suavizar_forma=2)
    malla_salida, informe = salida.result[0], salida.result[1]
    datos = dict(linea.split(None, 1) for linea in informe.split("\n"))

    v = malla_salida.vertices[0].cpu().numpy()
    medida_despues = (v.max(axis=0) - v.min(axis=0)).max()
    desvio = 100 * abs(medida_despues - medida_antes) / medida_antes
    print(f"{nombre:<16} {datos['salida'].strip():<38} · tamano {desvio:4.1f}% de desvio · {time.time() - inicio:.0f} s")
