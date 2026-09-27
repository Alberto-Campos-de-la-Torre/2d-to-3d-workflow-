"""Bateria de pruebas para las dos imagenes de referencia.

  ComfyUI_windows_portable\python_embeded\python.exe scripts\probar_dos_referencias.py [--casos 1,3,5]

Cada caso son dos referencias y un prompt. Interesa saber tres cosas:
- si toma de cada imagen lo que se le pide,
- si distingue cual es la primera y cual la segunda (casos de orden invertido),
- si la forma de nombrarlas cambia el resultado ("first image" vs describir el objeto).

Guarda una hoja por caso en pruebas\dos_referencias con las dos referencias y el
resultado, y un resumen en dos_referencias.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generar_3d import peticion

COMFY = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI")
SALIDA = Path(r"D:\AI3D\pruebas\dos_referencias")
CAMARA, MANZANA = "cakestudio-0-900x580.jpg", "gettyimages-184276818-612x612.jpg"
CUBO, LLAVE = "images.jpg", "single-key-isolated-EKYW4C.jpg"
GIRASOL, BOTON = "istockphoto-174648035-612x612.jpg", "studio-shot-of-single-green-button-CR1943.jpg"

CASOS = [
    # (nombre, referencia 1, referencia 2, prompt, que se espera ver)
    ("1_forma_color_ordinal", CAMARA, MANZANA,
     "the object from the first image, painted with the colors of the second image",
     "camara con los colores de la manzana"),
    ("2_forma_color_descrito", CAMARA, MANZANA,
     "the camera, painted in the red and green colors of the apple",
     "camara con los colores de la manzana"),
    ("3_forma_color_numerado", CAMARA, MANZANA,
     "take the shape from image 1 and the color palette from image 2",
     "camara con los colores de la manzana"),
    # Control de orden: mismas imagenes, invertidas. Si sale igual que el caso 1, ignora el orden.
    ("4_orden_invertido", MANZANA, CAMARA,
     "the object from the first image, painted with the colors of the second image",
     "manzana con los colores de la camara (oscura)"),
    ("5_dos_objetos_juntos", CAMARA, MANZANA,
     "both objects together side by side on a plain background",
     "la camara Y la manzana, las dos"),
    ("6_patron_sobre_objeto", LLAVE, CUBO,
     "the key from the first image covered with the colorful square pattern of the second image",
     "llave con cuadros de colores"),
    ("7_objeto_y_fondo", BOTON, GIRASOL,
     "the button from the first image placed on top of the flower from the second image",
     "boton sobre el girasol"),
    # El caso 4 fallo: hay que separar si ignora el orden o si se resiste a pintar
    # una manzana de negro. El 9 pide el color oscuro de forma explicita; el 10 obliga
    # a tomar como sujeto la SEGUNDA imagen, que es el test duro de orden.
    ("9_negro_explicito", MANZANA, CAMARA,
     "the apple from the first image, painted matte black and dark grey like the camera in the second image",
     "manzana negra"),
    ("10_sujeto_es_la_segunda", LLAVE, CUBO,
     "the object from the second image, rendered in the plain metallic silver of the first image",
     "cubo de Rubik plateado (no una llave)"),
    ("8_color_solo_de_la_segunda", LLAVE, GIRASOL,
     "the key from the first image, but bright yellow like the flower in the second image",
     "llave amarilla"),
]


def grafo(ref1, ref2, prompt, semilla=42):
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen-image-2.1-UC-Q8_0.gguf"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "20": {"class_type": "LoadImage", "inputs": {"image": ref1}},
        "21": {"class_type": "LoadImage", "inputs": {"image": ref2}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["2", 0], "vae": ["3", 0], "prompt": prompt, "negative_prompt": "",
            "resolution": 1024, "images.image_1": ["20", 0], "images.image_2": ["21", 0]}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1], "latent_image": ["4", 2],
            "seed": semilla, "steps": 25, "cfg": 1.0, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "qwen21/dosref"}},
    }


def generar(ref1, ref2, prompt, semilla):
    respuesta = peticion("/prompt", json.dumps({"prompt": grafo(ref1, ref2, prompt, semilla)}).encode(),
                         {"Content-Type": "application/json"})
    if respuesta.get("node_errors"):
        raise RuntimeError(json.dumps(respuesta["node_errors"])[:400])
    pid = respuesta["prompt_id"]
    while True:
        historial = peticion(f"/history/{pid}")
        if pid in historial:
            break
        time.sleep(3)
    estado = historial[pid].get("status", {})
    if estado.get("status_str") != "success":
        raise RuntimeError(json.dumps(estado.get("messages", []))[:400])
    for salida in historial[pid]["outputs"].values():
        for imagen in salida.get("images", []):
            return imagen["filename"]
    raise RuntimeError("sin imagen")


def hoja(nombre, ref1, ref2, resultado, prompt):
    from PIL import Image, ImageDraw
    rutas = [COMFY / "input" / ref1, COMFY / "input" / ref2, COMFY / "output/qwen21" / resultado]
    ims = []
    for ruta in rutas:
        im = Image.open(ruta).convert("RGB")
        im.thumbnail((360, 360))
        ims.append(im)
    alto = max(i.height for i in ims) + 46
    lienzo = Image.new("RGB", (sum(i.width for i in ims) + 24, alto), (18, 18, 18))
    dibujo = ImageDraw.Draw(lienzo)
    dibujo.text((6, 6), f"{nombre}  ·  {prompt[:110]}", fill=(235, 235, 235))
    x = 0
    for etiqueta, im in zip(["ref 1", "ref 2", "RESULTADO"], ims):
        lienzo.paste(im, (x, 40))
        dibujo.text((x + 6, 26), etiqueta, fill=(170, 200, 170))
        x += im.width + 12
    destino = SALIDA / f"{nombre}.png"
    lienzo.save(destino)
    return destino


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--casos", default="", help="numeros separados por coma; vacio = todos")
    p.add_argument("--semilla", type=int, default=42)
    args = p.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)

    elegidos = {int(c) for c in args.casos.split(",") if c.strip()} if args.casos else None
    resultados = []
    for i, (nombre, ref1, ref2, prompt, esperado) in enumerate(CASOS, 1):
        if elegidos and i not in elegidos:
            continue
        print(f"[{i}/{len(CASOS)}] {nombre} ...", flush=True)
        inicio = time.time()
        try:
            archivo = generar(ref1, ref2, prompt, args.semilla)
        except Exception as e:
            print(f"    ERROR: {e}")
            resultados.append({"caso": nombre, "error": str(e)[:200]})
            continue
        destino = hoja(nombre, ref1, ref2, archivo, prompt)
        print(f"    {archivo} · {time.time() - inicio:.0f} s · esperado: {esperado}")
        resultados.append({"caso": nombre, "ref1": ref1, "ref2": ref2, "prompt": prompt,
                           "esperado": esperado, "archivo": archivo, "hoja": str(destino),
                           "segundos": round(time.time() - inicio)})
    (SALIDA / "resumen.json").write_text(json.dumps(resultados, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nhojas en {SALIDA}")


if __name__ == "__main__":
    main()
