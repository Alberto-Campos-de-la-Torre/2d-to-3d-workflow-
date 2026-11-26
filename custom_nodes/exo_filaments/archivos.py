"""Dependencias OBJ/MTL, confinadas a la carpeta autorizada."""
from pathlib import Path
import shlex

def dependencias(archivo, base):
    base = Path(base).resolve()
    archivo = Path(archivo).resolve()
    if not archivo.is_relative_to(base):
        raise ValueError("Archivo fuera de la carpeta autorizada")
    if archivo.suffix.lower() not in (".obj", ".mtl"):
        return []
    resultado = []
    for linea in archivo.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        partes = linea.strip().split(None, 1)
        if len(partes) != 2:
            continue
        clave, argumento = partes
        if archivo.suffix.lower() == ".obj" and clave.lower() == "mtllib":
            nombres = [argumento] if (archivo.parent / argumento).is_file() else shlex.split(argumento, posix=True)
        elif archivo.suffix.lower() == ".mtl" and (clave.lower().startswith("map_") or clave.lower() in ("bump", "disp", "decal", "norm")):
            nombres = [argumento] if (archivo.parent / argumento).is_file() else [shlex.split(argumento, posix=True)[-1]]
        else:
            continue
        for nombre in nombres:
            ruta = (archivo.parent / nombre).resolve()
            if not ruta.is_relative_to(base) or not ruta.is_file():
                raise ValueError("Dependencia ausente o fuera de la carpeta: " + nombre)
            resultado.append(ruta)
    return resultado

def reunir(archivos, base):
    pendientes = list(archivos)
    vistos = set()
    while pendientes:
        archivo = Path(pendientes.pop()).resolve()
        if archivo in vistos:
            continue
        if not archivo.is_relative_to(Path(base).resolve()) or not archivo.is_file():
            raise ValueError("Archivo ausente o fuera de la carpeta autorizada")
        vistos.add(archivo)
        pendientes.extend(dependencias(archivo, base))
    return sorted(vistos)
