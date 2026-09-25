"""Monta una hoja de contacto con los renders de una carpeta de revision.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\hoja_contacto.py <carpeta> [vista]
"""
import sys
from pathlib import Path

from PIL import Image

carpeta = Path(sys.argv[1])
vista = sys.argv[2] if len(sys.argv) > 2 else "frente"
LADO, COLUMNAS = 400, 4

archivos = sorted(r for r in carpeta.glob(f"*_{vista}.png") if not r.name.startswith("hoja_"))
if not archivos:
    raise SystemExit(f"sin renders *_{vista}.png en {carpeta}")

filas = (len(archivos) + COLUMNAS - 1) // COLUMNAS
hoja = Image.new("RGB", (COLUMNAS * LADO, filas * LADO), (0, 0, 0))
for i, ruta in enumerate(archivos):
    hoja.paste(Image.open(ruta).convert("RGB"), ((i % COLUMNAS) * LADO, (i // COLUMNAS) * LADO))
destino = carpeta / f"hoja_{vista}.png"
hoja.save(destino)
print(destino)
for i, ruta in enumerate(archivos):
    print(f"  {i + 1}. {ruta.stem}")
