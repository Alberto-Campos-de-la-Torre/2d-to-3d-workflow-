"""Prueba la revision visual de piezas terminadas.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_revision_pieza.py

Casos: piezas que sabemos buenas (camara, zorro) y piezas que sabemos problematicas
(girasol, conejo hueco). Guarda las hojas de vistas en pruebas\\revision_pieza.
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
from custom_nodes.exo_filaments.revision_pieza import resumen, revisar_pieza  # noqa: E402
from glb_lector import leer_stl  # noqa: E402

SALIDA = Path(r"D:\AI3D\pruebas\revision_pieza")
SALIDA.mkdir(parents=True, exist_ok=True)

CASOS = [
    ("camara-tarta", COMFY / "output/final/cakestudio-0-900x580_00001.stl", "una camara de fotos"),
    ("zorro", COMFY / "output/texto/pieza_00005.stl", "un zorro sentado, figura de resina"),
    ("girasol", COMFY / "output/final/istockphoto-174648035-612x612_00001.stl", "un girasol"),
    ("conejo (salio hueco)", COMFY / "output/final/bunny_double_negative_00001.stl", "un conejo decorativo"),
]

for etiqueta, ruta, descripcion in CASOS:
    if not ruta.exists():
        print(f"{etiqueta:<22} (no existe: {ruta.name})")
        continue
    pos, tri = leer_stl(ruta)
    malla = MESH(vertices=torch.from_numpy(pos).unsqueeze(0),
                 faces=torch.from_numpy(tri.astype(np.int64)).unsqueeze(0))
    inicio = time.time()
    informe, hoja = revisar_pieza(malla, descripcion, lado=448)
    hoja.save(SALIDA / f"{etiqueta.split()[0]}.png")
    print(f"=== {etiqueta}  ({time.time() - inicio:.0f} s)")
    for linea in resumen(informe).splitlines():
        print(f"   {linea}")
