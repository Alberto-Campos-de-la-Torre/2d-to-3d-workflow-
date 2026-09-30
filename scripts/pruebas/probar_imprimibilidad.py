"""Valida la revision de imprimibilidad contra formas de resultado conocido.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\pruebas\\probar_imprimibilidad.py

Cada caso tiene una respuesta que se sabe de antemano:
- un cubo apoyado: sin voladizos (su cara de abajo esta en la cama) y muy estable,
- una esfera: la calota inferior es voladizo, y son 14,6 % de su superficie por geometria,
- una seta (tallo fino con sombrero ancho): voladizo grande y huella pequena,
- una torre inclinada: el centro de masa se sale de la huella y vuelca,
- una pieza de 400 mm: no cabe en una cama de 350.
"""
import sys
from pathlib import Path

import numpy as np

# Se carga el modulo suelto: importar el paquete entero arrastra estudio.py, que necesita
# el servidor de ComfyUI en marcha, y esta prueba tiene que poder correr sin el.
import importlib
import types

PAQUETE = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\custom_nodes\exo_filaments")
_stub = types.ModuleType("exo_suelto")
_stub.__path__ = [str(PAQUETE)]
sys.modules["exo_suelto"] = _stub
revisar = importlib.import_module("exo_suelto.imprimibilidad").revisar

CAMA = (350.0, 350.0, 350.0)


def cubo(lado=40.0):
    v = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float) * lado
    c = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    return v, c


def esfera(radio=30.0, n=80):
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


def _cilindro(radio, z0, z1, n=64, desvio=0.0):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    aro = np.stack([np.cos(ang) * radio, np.sin(ang) * radio], -1)
    abajo = np.c_[aro, np.full(n, z0)]
    arriba = np.c_[aro + desvio, np.full(n, z1)]
    v = np.concatenate([abajo, arriba, [[0, 0, z0]], [[desvio, desvio, z1]]])
    caras = []
    for i in range(n):
        j = (i + 1) % n
        caras += [[i, j, n + j], [i, n + j, n + i], [2 * n, j, i], [2 * n + 1, n + i, n + j]]
    return v, np.array(caras)


def unir(*piezas):
    vs, cs, desplazamiento = [], [], 0
    for v, c in piezas:
        vs.append(v)
        cs.append(c + desplazamiento)
        desplazamiento += len(v)
    return np.concatenate(vs), np.concatenate(cs)


def seta():
    """Tallo fino y sombrero ancho: el sombrero es todo voladizo y apoya en poco."""
    return unir(_cilindro(6.0, 0.0, 40.0), _cilindro(35.0, 40.0, 55.0))


def torre_inclinada():
    """Se va tanto de lado que el centro de masa sale de la huella."""
    return _cilindro(12.0, 0.0, 90.0, desvio=45.0)


CASOS = [
    ("cubo 40 mm", cubo(), {"voladizo_max": 1.0, "cabe": True, "estable": True}),
    ("esfera r=30", esfera(), {"voladizo_min": 10.0, "voladizo_max": 20.0, "cabe": True}),
    ("seta (tallo fino)", seta(), {"voladizo_min": 20.0, "huella_max": 200.0}),
    ("torre inclinada", torre_inclinada(), {"estable": False}),
    ("cubo 400 mm", cubo(400.0), {"cabe": False}),
]

fallos = 0
for nombre, (v, c), espera in CASOS:
    # Las formas se definen ya de pie, asi que no hay que girarlas.
    informe = revisar(v.astype(np.float64), c, cama=CAMA, ya_de_pie=True)
    problemas = []
    if "voladizo_max" in espera and informe["voladizo_pct"] > espera["voladizo_max"]:
        problemas.append("voladizo %.1f > %.1f" % (informe["voladizo_pct"], espera["voladizo_max"]))
    if "voladizo_min" in espera and informe["voladizo_pct"] < espera["voladizo_min"]:
        problemas.append("voladizo %.1f < %.1f" % (informe["voladizo_pct"], espera["voladizo_min"]))
    if "cabe" in espera and informe["cabe"] != espera["cabe"]:
        problemas.append("cabe=%s" % informe["cabe"])
    if "huella_max" in espera and informe["huella_mm2"] > espera["huella_max"]:
        problemas.append("huella %.0f > %.0f" % (informe["huella_mm2"], espera["huella_max"]))
    if "estable" in espera:
        margen = informe["margen_vuelco_mm"]
        estable = margen is not None and margen > 0
        if estable != espera["estable"]:
            problemas.append("estable=%s (margen %s)" % (estable, margen))
    fallos += bool(problemas)
    print("[%s] %-20s voladizo %5.1f %% · huella %7.0f mm2 · margen %-6s · cabe %s"
          % ("MAL" if problemas else "OK ", nombre, informe["voladizo_pct"],
             informe["huella_mm2"], informe["margen_vuelco_mm"], informe["cabe"]))
    if problemas:
        print("      no cuadra:", "; ".join(problemas))

print("\n%s" % ("todos los casos como se esperaba" if not fallos else "HAY %d FUERA" % fallos))
