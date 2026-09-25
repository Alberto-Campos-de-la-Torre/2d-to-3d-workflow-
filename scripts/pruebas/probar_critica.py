"""Valida el critico contra casos conocidos.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_critica.py

Tres bloques:
- casos negativos: imagenes que sabemos malas; debe encontrar el defecto concreto.
- casos limpios: imagenes buenas; no debe inventarse defectos.
- caso positivo de anatomia: se fabrica en memoria una figura con la cabeza duplicada
  (el JSON directo no la veia; enumerando si) y debe marcarla.
"""
import sys
import time
import types
from pathlib import Path

COMFY = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI")
sys.path.insert(0, str(COMFY))
sys.path.insert(0, r"D:\AI3D\scripts")

from PIL import Image  # noqa: E402

sys.modules["custom_nodes.exo_filaments.estudio"] = types.ModuleType("estudio")
from custom_nodes.exo_filaments.critica import corregir, criticar, resumen  # noqa: E402

ENTRADA = Path(r"D:\AI3D\pruebas\entrada")
GENERADAS = COMFY / "output" / "qwen21"

NEGATIVOS = [
    ("girasol", ENTRADA / "istockphoto-174648035-612x612.jpg", "partes_finas"),
    ("licorera de cristal", ENTRADA / "images (2).jpg", "transparente"),
    ("manzana con marca de agua", ENTRADA / "gettyimages-184276818-612x612.jpg", "texto_o_marca"),
    ("conejo enredado", ENTRADA / "bunny_double_negative.jpg", "partes_finas"),
    # La foto de la llave lleva marca de agua de Alamy y el objeto ocupa el 6% del
    # encuadre. Que la marque es correcto, aunque su pieza 3D saliera bien.
    ("llave con marca de agua", ENTRADA / "single-key-isolated-EKYW4C.jpg", "texto_o_marca"),
]
# Como casos limpios solo valen imagenes generadas: las de banco llevan marca de agua.
LIMPIOS = []

aciertos, total = 0, 0


def revisar(etiqueta, ruta, esperado=None, imagen=None):
    global aciertos, total
    total += 1
    img = imagen or Image.open(ruta)
    inicio = time.time()
    informe = criticar(img)
    segundos = time.time() - inicio
    defectos = informe.get("defectos", [])
    if esperado is None:
        bien = not defectos
        veredicto = "OK (limpia)" if bien else f"FALSA ALARMA: {defectos}"
    else:
        bien = esperado in defectos
        veredicto = f"OK (detecto {esperado})" if bien else f"FALLO: esperaba {esperado}, dio {defectos or 'nada'}"
    aciertos += bool(bien)
    print(f"{etiqueta:<28} {veredicto:<44} {informe.get('puntuacion')}/10 · {segundos:.1f} s")
    return informe


print("=== casos que deben dar defecto ===")
for etiqueta, ruta, esperado in NEGATIVOS:
    if ruta.exists():
        revisar(etiqueta, ruta, esperado)

print("\n=== casos que deben salir limpios ===")
for etiqueta, ruta in LIMPIOS:
    if ruta.exists():
        revisar(etiqueta, ruta)
for ruta in sorted(GENERADAS.glob("qwen_*.png"))[:2]:
    revisar(f"generada {ruta.stem}", ruta)

print("\n=== anatomia: figura manipulada ===")
base = sorted(GENERADAS.glob("*.png"))
if base:
    original = Image.open(base[0]).convert("RGB")
    ancho, alto = original.size
    rota = original.copy()
    rota.paste(original.crop((int(ancho * .25), int(alto * .25), int(ancho * .75), int(alto * .75))),
               (int(ancho * .45), int(alto * .30)))
    informe = revisar("cabeza duplicada", None, "anatomia", imagen=rota)

    print("\n=== correccion propuesta ===")
    prompt, negativo, cambios = corregir("a small dragon figurine", "", informe, 42)
    print(f"  prompt:   {prompt[:150]}")
    print(f"  negativo: {negativo[:150]}")
    print(f"  cambios:  {cambios}")
    print("\n--- informe completo del ultimo caso:")
    print(resumen(informe))

print(f"\n=== {aciertos} de {total} correctos ===")
