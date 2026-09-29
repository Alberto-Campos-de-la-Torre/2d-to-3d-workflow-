"""Valida la medida de volumen contra formas de volumen conocido.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\pruebas\\probar_volumen.py

Se comprueban tres cosas:
- que en una malla bien orientada el resultado coincide con la formula exacta,
- que la medida por voxeles se acerca al volumen teorico (cubo, esfera, cilindro),
- y lo que motivo todo esto: que con las caras mal orientadas el volumen firmado se
  hunde y la medida por voxeles aguanta.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\custom_nodes\exo_filaments")))
from geometria import volumen, volumen_firmado, volumen_voxeles   # noqa: E402


def cubo(lado=20.0):
    v = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64) * lado
    c = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return v, c


def esfera(radio=15.0, n=64):
    u = np.linspace(0, np.pi, n)
    w = np.linspace(0, 2 * np.pi, n)
    uu, ww = np.meshgrid(u, w, indexing="ij")
    v = np.stack([np.sin(uu) * np.cos(ww), np.sin(uu) * np.sin(ww), np.cos(uu)], -1) * radio
    v = v.reshape(-1, 3)
    caras = []
    for i in range(n - 1):
        for j in range(n - 1):
            a, b, c, d = i * n + j, i * n + j + 1, (i + 1) * n + j + 1, (i + 1) * n + j
            caras += [[a, b, c], [a, c, d]]
    return v, np.array(caras)


def cilindro(radio=10.0, alto=40.0, n=96):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    aro = np.stack([np.cos(ang) * radio, np.sin(ang) * radio], -1)
    v = np.concatenate([np.c_[aro, np.zeros(n)], np.c_[aro, np.full(n, alto)],
                        [[0, 0, 0]], [[0, 0, alto]]])
    caras = []
    for i in range(n):
        j = (i + 1) % n
        caras += [[i, j, n + j], [i, n + j, n + i], [2 * n, j, i], [2 * n + 1, n + i, n + j]]
    return v, np.array(caras)


CASOS = [
    ("cubo 20 mm", cubo(20.0), 20.0 ** 3),
    ("esfera r=15", esfera(15.0), 4 / 3 * np.pi * 15.0 ** 3),
    ("cilindro r=10 h=40", cilindro(), np.pi * 10.0 ** 2 * 40.0),
]

print("forma                 teorico    firmado    voxeles   metodo     error")
fallos = 0
for nombre, (v, c), teorico in CASOS:
    firmado = volumen_firmado(v, c)
    por_vox = volumen_voxeles(v, c)
    valor, metodo = volumen(v, c)
    error = abs(valor - teorico) / teorico * 100
    fallos += error > 6
    print("%-20s %9.0f %10.0f %10.0f   %-9s %5.1f %%"
          % (nombre, teorico, firmado, por_vox, metodo, error))

# El caso que motivo el cambio: la mitad de las caras del reves. El firmado se cancela
# solo; el de voxeles ni se entera, porque no mira hacia donde apunta nada.
print("\ncon la mitad de las caras invertidas (lo que pasa tras solidificar y decimar):")
for nombre, (v, c), teorico in CASOS:
    rota = c.copy()
    rota[::2] = rota[::2][:, ::-1]
    firmado = volumen_firmado(v, rota)
    valor, metodo = volumen(v, rota)
    error = abs(valor - teorico) / teorico * 100
    fallos += error > 8
    print("%-20s teorico %8.0f · firmado %8.0f (%4.0f %% del real) · elegido %8.0f por %s (%.1f %% de error)"
          % (nombre, teorico, firmado, firmado / teorico * 100, valor, metodo, error))

print("\n%s" % ("todo dentro de tolerancia" if not fallos else "HAY %d CASOS FUERA" % fallos))
