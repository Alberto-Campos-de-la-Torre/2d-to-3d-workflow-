"""Compara los dos reconstructores de voxeles: 'basic' (cubos) y 'surface net' (suave).

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\comparar_malladores.py

La primera medicion (que descarto surface net) fue antes de arreglar el soldado de
vertices y de separar agujeros reales de aristas no-manifold. Esto lo mide bien.
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
from scipy import ndimage  # noqa: E402

sys.modules["custom_nodes.exo_filaments.estudio"] = types.ModuleType("estudio")
from comfy_extras.nodes_hunyuan3d import voxel_to_mesh, voxel_to_mesh_surfnet  # noqa: E402
from custom_nodes.exo_filaments.nodes import (_clasificar_aristas, _rasterizar,  # noqa: E402
                                              _soldar, _suavizar_forma)
from glb_lector import escribir_stl, leer_glb  # noqa: E402

SALIDA = Path(r"D:\AI3D\pruebas\malladores")
SALIDA.mkdir(parents=True, exist_ok=True)

PRUEBAS = [
    ("llave", COMFY / "output/3d/trellis2/single-key-isolated-EKYW4C_00002_.glb"),
    ("camara", COMFY / "output/3d/hy2.0/cakestudio-0-900x580_00001_.glb"),
    ("conejo", COMFY / "output/3d/hy2.0/bunny_double_negative_00001_.glb"),
]
RESOLUCION = 320


def solido_de(ruta):
    atributos, tri, _ = leer_glb(ruta, ("POSITION",))
    rejilla, origen, escala = _rasterizar(atributos["POSITION"], tri, RESOLUCION)
    hueco = 2
    lleno = ndimage.binary_fill_holes(ndimage.binary_dilation(np.pad(rejilla, hueco), iterations=1))
    recorte = slice(hueco, -hueco)
    solido = ndimage.binary_erosion(lleno, iterations=1, border_value=0)[recorte, recorte, recorte]
    solido = ndimage.binary_fill_holes(solido)
    return solido, origen, escala


for nombre, ruta in PRUEBAS:
    if not ruta.exists():
        print(f"{nombre}: no existe")
        continue
    solido, origen, escala = solido_de(ruta)
    print(f"\n=== {nombre} · {int(solido.sum()):,} voxeles solidos")
    campo = torch.from_numpy(solido.astype(np.float32))
    for etiqueta, malla, suavizado in [("cubos (basic)", voxel_to_mesh, 2),
                                       ("suave (surface net)", voxel_to_mesh_surfnet, 0)]:
        inicio = time.time()
        v, f = malla(campo, threshold=0.5, device=None)
        coords = v.cpu().numpy().astype(np.float64)[:, ::-1] * (RESOLUCION / 2.0) + (RESOLUCION / 2.0)
        vertices = (coords / escala + origen).astype(np.float32)
        vertices, caras = _soldar(vertices, np.ascontiguousarray(f.cpu().numpy().astype(np.int64)))
        vertices = _suavizar_forma(vertices, caras, suavizado)
        agujeros, no_manifold = _clasificar_aristas(vertices, caras)
        escribir_stl(SALIDA / f"{nombre}_{etiqueta.split()[0]}.stl", vertices, caras)
        print(f"  {etiqueta:<22} {len(caras):>9,} caras · {agujeros:>6,} agujeros · "
              f"{no_manifold:>7,} no-manifold · {time.time() - inicio:.0f} s")
