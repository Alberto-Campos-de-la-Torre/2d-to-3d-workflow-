"""Convierte un modelo con color en piezas separadas por filamento (impresion multicolor).

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\colores_a_piezas.py <modelo.glb> [opciones]

Opciones:
  --colores 4          cuantos filamentos usar (ranuras del AMS)
  --altura-mm 80       altura final de la pieza; escala el modelo a milimetros
  --paleta "#RRGGBB,#RRGGBB,..."   colores reales de tus bobinas: cada grupo se asigna
                       al filamento mas parecido en vez de inventar colores
  --salida <carpeta>   por defecto, junto al modelo, en <nombre>_multicolor\\

Acepta GLB con color por vertice (COLOR_0) o con textura UV. Escribe un STL binario por
color y un colores.json con el RGB y el porcentaje de cada grupo. En Bambu Studio u Orca:
importar los STL juntos y responder "si" a cargarlos como un solo objeto con varias
piezas; luego asignar a cada pieza su filamento.
"""
import argparse
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from color_util import agrupar, escribir_obj_color, hex_a_rgb, lineal_a_srgb
from glb_lector import escribir_stl, leer_glb, leer_imagen_base


def color_por_cara(atributos, tri, ruta, cabecera):
    """Color medio de cada triangulo, desde COLOR_0 o muestreando la textura."""
    if "COLOR_0" in atributos:
        col = atributos["COLOR_0"][:, :3]
        medio = (col[tri[:, 0]] + col[tri[:, 1]] + col[tri[:, 2]]) / 3.0
        # glTF guarda COLOR_0 en espacio lineal; se pasa a sRGB para que los hex
        # coincidan con lo que se ve en pantalla y con el color de las bobinas.
        return np.where(medio <= 0.0031308, medio * 12.92, 1.055 * np.power(np.clip(medio, 0, None), 1 / 2.4) - 0.055)

    if "TEXCOORD_0" not in atributos:
        raise SystemExit("el modelo no tiene ni color por vertice ni coordenadas UV")
    from PIL import Image
    crudo = leer_imagen_base(ruta, cabecera)
    if crudo is None:
        raise SystemExit("el modelo tiene UV pero ninguna textura embebida")
    textura = np.asarray(Image.open(io.BytesIO(crudo)).convert("RGB"), dtype=np.float32) / 255.0
    uv = atributos["TEXCOORD_0"]
    centro = (uv[tri[:, 0]] + uv[tri[:, 1]] + uv[tri[:, 2]]) / 3.0
    alto, ancho = textura.shape[:2]
    x = np.clip((centro[:, 0] % 1.0) * (ancho - 1), 0, ancho - 1).astype(np.int32)
    y = np.clip((1.0 - centro[:, 1] % 1.0) * (alto - 1), 0, alto - 1).astype(np.int32)
    return textura[y, x]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("modelo")
    p.add_argument("--colores", type=int, default=4)
    p.add_argument("--altura-mm", type=float, default=80.0)
    p.add_argument("--paleta", default="", help="colores de tus bobinas: '#1a1a1a,#d92b2b,...'")
    p.add_argument("--salida", default="")
    p.add_argument("--peso-luz", type=float, default=0.25,
                   help="cuanto pesa el brillo al agrupar (0 = solo color, 1 = color y sombra por igual)")
    p.add_argument("--min-distancia", type=float, default=14.0, help="funde grupos de color mas parecidos que esto")
    p.add_argument("--min-porcentaje", type=float, default=2.0, help="funde grupos que cubran menos superficie que esto")
    args = p.parse_args()

    ruta = Path(args.modelo)
    salida = Path(args.salida) if args.salida else ruta.parent / f"{ruta.stem}_multicolor"
    salida.mkdir(parents=True, exist_ok=True)

    atributos, tri, cabecera = leer_glb(ruta, ("POSITION", "COLOR_0", "TEXCOORD_0"))
    pos = atributos["POSITION"].astype(np.float32)
    colores = color_por_cara(atributos, tri, ruta, cabecera)
    print(f"malla: {len(tri)} caras, {len(pos)} vertices")

    paleta = [hex_a_rgb(c) for c in args.paleta.split(",") if c.strip()]
    etiquetas, centros = agrupar(colores, paleta or None, args.colores,
                                 args.peso_luz, args.min_distancia, args.min_porcentaje)
    k = len(centros)

    # Escalado a milimetros: la altura pedida se aplica al eje mas alto.
    minimo, maximo = pos.min(axis=0), pos.max(axis=0)
    escala = args.altura_mm / float((maximo - minimo).max())
    pos_mm = (pos - (minimo + maximo) / 2.0) * escala

    informe = []
    for i in range(k):
        caras = tri[etiquetas == i]
        if not len(caras):
            continue
        usados, remapeo = np.unique(caras, return_inverse=True)
        destino = salida / f"pieza_{i + 1}.stl"
        escribir_stl(destino, pos_mm[usados], remapeo.reshape(-1, 3).astype(np.int32))
        rgb = (centros[i] * 255).round().astype(int).tolist()
        informe.append({
            "pieza": destino.name,
            "rgb": rgb,
            "hex": "#%02x%02x%02x" % tuple(rgb),
            "caras": int(len(caras)),
            "porcentaje": round(100 * len(caras) / len(tri), 1),
        })
        print(f"  {destino.name}: {informe[-1]['hex']}  {informe[-1]['porcentaje']}% de la superficie")

    obj_destino = salida / f"{ruta.stem}_color.obj"
    escribir_obj_color(obj_destino, pos_mm, tri, etiquetas, centros, nombre=ruta.stem)
    print(f"\n  {obj_destino.name}: modelo entero con color por vertice (recomendado para el AMS)")
    print("  AVISO: sale de la malla en bruto. Para imprimir, mejor usar preparar_impresion.py,")
    print("         que repara la malla y exporta el OBJ de color ya cerrado.")

    (salida / "colores.json").write_text(json.dumps({
        "modelo": ruta.name,
        "altura_mm": args.altura_mm,
        "piezas": informe,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nlisto: {salida}")
    print("Dos caminos en el laminador (Creality Print 6.3, Bambu Studio u Orca):")
    print("  1. Importar el .obj (llevatelo junto a su .mtl): sale el dialogo de emparejar")
    print("     los colores del modelo con los filamentos cargados. Conserva una sola pieza.")
    print("  2. Si esa version no lo admite: importar los STL a la vez, cargarlos como un")
    print("     solo objeto con varias piezas y asignar filamento a cada una.")


main()
