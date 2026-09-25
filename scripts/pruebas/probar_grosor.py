"""Valida el nodo de grosor contra piezas de medida conocida.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_grosor.py

Un cubo macizo de 20 mm no debe tener zonas finas; una placa de 0,6 mm debe salir casi
entera marcada. Si estos dos casos no salen, el aviso del flujo no vale nada.
"""
import sys
from pathlib import Path

COMFY = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI")
sys.path.insert(0, str(COMFY))
sys.path.insert(0, r"D:\AI3D\scripts")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from comfy_api.latest._util.geometry_types import MESH  # noqa: E402
from custom_nodes.exo_filaments.nodes import ExoRevisarGrosor  # noqa: E402
from glb_lector import leer_stl  # noqa: E402


def caja(ancho, alto, fondo):
    """Caja cerrada centrada en el origen."""
    x, y, z = ancho / 2, fondo / 2, alto / 2
    v = np.array([[-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z],
                  [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]], dtype=np.float32)
    caras = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                      [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                      [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], dtype=np.int64)
    return MESH(vertices=torch.from_numpy(v).unsqueeze(0), faces=torch.from_numpy(caras).unsqueeze(0))


def revisar(nombre, malla, grosor=1.2):
    salida = ExoRevisarGrosor.execute(mesh=malla, grosor_min_mm=grosor, aviso_pct=5.0, muestras=4000)
    pct = salida.result[2]
    print(f"{nombre:<34} zonas finas: {pct:5.1f} %")
    return pct


print("=== formas de control (grosor minimo 1,2 mm) ===")
cubo = revisar("cubo macizo 20 mm", caja(20, 20, 20))
placa = revisar("placa de 0,6 mm", caja(40, 40, 0.6))
pared = revisar("placa de 2 mm", caja(40, 40, 2.0))

print("\n=== piezas reales ===")
for ruta in [r"D:\AI3D\pruebas\listos\rubik_limpio.stl", r"D:\AI3D\pruebas\listos\llave_sdf.stl",
             r"D:\AI3D\pruebas\listos\camara_hy20.stl"]:
    archivo = Path(ruta)
    if not archivo.exists():
        continue
    pos, tri = leer_stl(archivo)
    malla = MESH(vertices=torch.from_numpy(pos).unsqueeze(0),
                 faces=torch.from_numpy(tri.astype(np.int64)).unsqueeze(0))
    revisar(archivo.stem, malla)

print("\nesperado: cubo ~0 %, placa de 0,6 mm alta, placa de 2 mm ~0 %")
print("resultado:", "OK" if cubo < 2 and placa > 90 and pared < 5 else "REVISAR EL NODO")

