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
INTOCABLE = ("models", "input", "custom_nodes", "repo", "scripts", "user", "python_embeded")


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
    return any(parte in INTOCABLE for parte in ruta.parts)


def revisar(grupo, carpeta, dias, conservar):
    """Archivos del grupo que se pueden borrar, mas lo que se deja y por que."""
    if not carpeta.exists() or _protegida(carpeta):
        return [], 0, 0
    archivos = [f for f in carpeta.rglob("*") if f.is_file()]
    archivos.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    limite = time.time() - dias * 86400
    sobran, guardados = [], 0
    for i, archivo in enumerate(archivos):
        if i < conservar or archivo.stat().st_mtime > limite:
            guardados += 1
            continue
        sobran.append(archivo)
    return sobran, guardados, sum(_tamano(f) for f in sobran)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--borrar", action="store_true", help="borra de verdad; sin esto solo lista")
    p.add_argument("--dias", type=int, default=7,
                   help="no toca nada de los ultimos N dias (por defecto 7)")
    p.add_argument("--conservar", type=int, default=5,
                   help="archivos mas recientes que se salvan siempre en cada grupo")
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
    for archivo in por_borrar:
        if _protegida(archivo):
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
            if sub.is_dir() and not any(sub.iterdir()):
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
