"""Enseña que ocupan las pruebas y, si se le pide, lo borra.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\limpiar.py
  ...\\python.exe scripts\\limpiar.py --borrar            (borra de verdad)
  ...\\python.exe scripts\\limpiar.py --dias 30 --conservar 10

Por defecto NO BORRA: lista lo que sobra, agrupado y con su tamano, para poder mirarlo
antes. Hay que pasar --borrar para que toque el disco.

Nunca se mete con los modelos (son decenas de GB y se tarda horas en volver a bajarlos),
ni con input/, ni con el repositorio, ni con los scripts. Y de cada grupo deja siempre los
mas recientes y lo de los ultimos dias, que es con lo que se suele estar trabajando.
"""
import argparse
import shutil
import time
import sys
from pathlib import Path

RAIZ = Path(r"D:\AI3D")
SALIDA = RAIZ / "ComfyUI_windows_portable" / "ComfyUI" / "output"

# (nombre, carpeta, que son)
GRUPOS = [
    ("mallas de prueba", SALIDA / "3d", "GLB, STL y OBJ de las conversiones"),
    ("pruebas finales", SALIDA / "final", "salidas de la bateria final"),
    ("texto a pieza", SALIDA / "texto", "salidas del flujo de texto"),
    ("comparativas exo", SALIDA / "exo", "salidas de las comparaciones"),
    ("orientacion", SALIDA / "orientacion", "pruebas de puesta de pie"),
    ("hojas de prueba", RAIZ / "pruebas", "hojas comparativas y renders"),
    ("descargas", RAIZ / "downloads", "instaladores ya usados"),
]

# Lo que no se toca ni pasando --borrar.
INTOCABLE = ("models", "input", "custom_nodes", "repo", "scripts", "user", "python_embeded", "encargos")


def _tamano(ruta):
    try:
        return ruta.stat().st_size
    except OSError:
        return 0


def _humano(bytes_):
    for unidad in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024 or unidad == "GB":
            return "%.1f %s" % (bytes_, unidad)
        bytes_ /= 1024.0


def _protegida(ruta):
    return any(parte.casefold() in INTOCABLE for parte in ruta.parts)


def revisar(grupo, carpeta, dias, conservar):
    """Archivos del grupo que se pueden borrar, mas lo que se deja y por que."""
    if not carpeta.exists() or _protegida(carpeta):
        return [], 0, 0
    if dias < 0 or conservar < 0:
        raise ValueError("dias y conservar deben ser no negativos")
    base = carpeta.resolve()
    sys.path.insert(0, str(RAIZ / "ComfyUI_windows_portable/ComfyUI/custom_nodes/exo_filaments"))
    from archivos import dependencias
    archivos = [f.resolve() for f in carpeta.rglob("*") if f.is_file() and not f.is_symlink()
                and f.resolve().is_relative_to(base) and not _protegida(f)]
    padres = {f: f for f in archivos}
    def raiz(f):
        while padres[f] != f:
            padres[f] = padres[padres[f]]
            f = padres[f]
        return f
    def unir(a, b):
        padres[raiz(a)] = raiz(b)
    por_corte = {}
    por_nombre = {}
    proteger = set()
    for archivo in archivos:
        for ancestro in archivo.parents:
            if ancestro == base: break
            if ancestro.name.startswith("corte_"):
                if ancestro in por_corte: unir(archivo, por_corte[ancestro])
                por_corte[ancestro] = archivo
                break
        clave = (archivo.parent, archivo.stem)
        if clave in por_nombre:
            unir(archivo, por_nombre[clave])
        por_nombre[clave] = archivo
        try:
            for otro in dependencias(archivo, base):
                if otro in padres:
                    unir(archivo, otro)
                else:
                    proteger.add(archivo)
        except (ValueError, OSError):
            # Ante una dependencia desconocida se conserva el grupo entero.
            proteger.add(archivo)
    grupos = {}
    for archivo in archivos:
        grupos.setdefault(raiz(archivo), []).append(archivo)
    grupos = sorted(grupos.values(), key=lambda g: max(f.stat().st_mtime for f in g), reverse=True)
    limite = time.time() - dias * 86400
    sobran, guardados = [], 0
    for i, conjunto in enumerate(grupos):
        if i < conservar or any(f in proteger or f.stat().st_mtime > limite for f in conjunto):
            guardados += len(conjunto)
        else:
            sobran.extend(conjunto)
    return sobran, guardados, sum(_tamano(f) for f in sobran)



def main():
    p = argparse.ArgumentParser()
    p.add_argument("--borrar", action="store_true", help="borra de verdad; sin esto solo lista")
    p.add_argument("--dias", type=int, default=7,
                   help="no toca nada de los ultimos N dias (por defecto 7)")
    p.add_argument("--conservar", type=int, default=5,
                   help="conjuntos mas recientes que se salvan siempre en cada grupo")
    args = p.parse_args()

    total, por_borrar = 0, []
    print("grupo                carpeta                          sobran        ocupan   se quedan")
    print("-" * 88)
    for nombre, carpeta, _que in GRUPOS:
        sobran, guardados, ocupan = revisar(nombre, carpeta, args.dias, args.conservar)
        total += ocupan
        por_borrar += sobran
        # Las rutas comparten prefijo largo, asi que se ensena la cola, que es lo que
        # distingue una carpeta de otra.
        corta = str(carpeta).replace(str(RAIZ) + "\\", "")
        if len(corta) > 30:
            corta = "..." + corta[-27:]
        print("%-20s %-30s %6d %13s %11d" % (nombre, corta, len(sobran),
                                             _humano(ocupan), guardados))
    print("-" * 88)
    print("%-20s %-32s %6d %13s" % ("TOTAL", "", len(por_borrar), _humano(total)))

    if not por_borrar:
        print("\nno hay nada que limpiar con estos margenes")
        return
    if not args.borrar:
        print("\nNo se ha borrado nada. Para hacerlo de verdad:")
        print("  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\limpiar.py --borrar")
        print("Se respetan siempre los %d mas recientes de cada grupo y todo lo de los "
              "ultimos %d dias." % (args.conservar, args.dias))
        return

    borrados, fallos = 0, 0
    bases = [carpeta.resolve() for _, carpeta, _ in GRUPOS]
    for archivo in por_borrar:
        destino = archivo.resolve()
        if archivo.is_symlink() or not any(destino.is_relative_to(base) for base in bases) or _protegida(destino):
            continue
        try:
            archivo.unlink()
            borrados += 1
        except OSError:
            fallos += 1
    # Carpetas que quedan vacias, para no dejar el arbol lleno de esqueletos.
    for _nombre, carpeta, _que in GRUPOS:
        if not carpeta.exists():
            continue
        for sub in sorted(carpeta.rglob("*"), key=lambda r: len(r.parts), reverse=True):
            if sub.is_dir() and not sub.is_symlink() and not _protegida(sub) and sub.resolve().is_relative_to(carpeta.resolve()) and not any(sub.iterdir()):
                try:
                    sub.rmdir()
                except OSError:
                    pass
    print("\nborrados %d archivos (%s)%s" % (borrados, _humano(total),
                                             ", %d no se pudieron borrar" % fallos if fallos else ""))
    libre = shutil.disk_usage(RAIZ).free
    print("libre en el disco: %s" % _humano(libre))


if __name__ == "__main__":
    main()
