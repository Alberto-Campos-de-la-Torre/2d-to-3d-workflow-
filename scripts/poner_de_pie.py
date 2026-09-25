"""Gira piezas ya guardadas de Y arriba a Z arriba, para que entren de pie en el laminador.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\poner_de_pie.py <carpeta o archivo>

Sirve para las piezas generadas antes de que el nodo 'Guardar para imprimir' lo hiciera
solo. Escribe copias con el sufijo _depie y no toca los originales.
"""
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from glb_lector import escribir_stl, leer_stl


def girar(puntos):
    """(x, y, z) -> (x, -z, y): la altura pasa del eje Y al eje Z."""
    return np.stack([puntos[:, 0], -puntos[:, 2], puntos[:, 1]], axis=1)


def girar_stl(origen):
    vertices, caras = leer_stl(origen)
    destino = origen.with_name(origen.stem + "_depie.stl")
    escribir_stl(destino, girar(vertices), caras)
    return destino


def main():
    origen = Path(sys.argv[1] if len(sys.argv) > 1 else
                  r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\output\final")
    archivos = [origen] if origen.is_file() else sorted(
        f for f in origen.iterdir() if f.suffix.lower() == ".stl" and "_depie" not in f.stem)
    if not archivos:
        print(f"nada que girar en {origen}")
        return

    for archivo in archivos:
        destino = girar_stl(archivo)
        if archivo.suffix.lower() == ".stl":
            v, _ = leer_stl(destino)
            medidas = v.max(axis=0) - v.min(axis=0)
            eje = "XYZ"[int(medidas.argmax())]
            print(f"{destino.name:<52} eje mas largo: {eje}")
        else:
            print(f"{destino.name:<52} (+ .mtl)")
    print(f"\n{len(archivos)} archivos girados en {origen}")


if __name__ == "__main__":
    main()

