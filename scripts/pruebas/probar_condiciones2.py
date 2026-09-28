"""Segunda vuelta: como evitar que un personaje de la referencia 2 robe el protagonismo.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_condiciones2.py

La primera vuelta (probar_condiciones.py) dejo claro el problema: si la referencia 2
contiene una persona o un personaje, el generador la convierte en el sujeto y el objeto de
la referencia 1 pasa a ser decorado. Con una lampara en la referencia 2 no pasa.

Aqui se prueban tres remedios sobre los tres casos que fallaron:
- "palabras": la condicion se describe con palabras y NO se menciona la segunda imagen,
- "negativo": se menciona la segunda imagen, pero el intruso va al prompt negativo,
- "ambos": las dos cosas a la vez.

Mismo juez y misma semilla que la primera vuelta, para poder comparar.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import prompt_ia
from generar_3d import peticion
from probar_condiciones import CHICA, DRAGON, SALIDA, hoja, juzgar

INTRUSO = "girl, woman, human, person, anime character, humanoid figure"

# (nombre, prompt, negativo) por remedio, mas la pregunta al juez
CASOS = [
    ("pose",
     "El sujeto principal es un dragon verde de plastico, y NO una chica? Y esta sentado "
     "con las piernas abiertas hacia los lados?",
     {"palabras": ("the green plastic dragon from the first image, sitting astride with its "
                   "legs spread wide apart to the sides, keeping its own shape, colors and identity", ""),
      "negativo": ("the dragon from the first image, in the same pose as the girl in the second "
                   "image, same body position and orientation, keeping its own colors, material "
                   "and identity", INTRUSO),
      "ambos": ("the green plastic dragon from the first image, sitting astride with its legs "
                "spread wide apart to the sides, keeping its own shape, colors and identity", INTRUSO)}),
    ("actividad",
     "El sujeto principal es un dragon verde de plastico, y NO una chica? Y sostiene un libro "
     "negro con las manos?",
     {"palabras": ("the green plastic dragon from the first image, holding a black book with "
                   "both hands in front of its chest, keeping its own shape, colors and identity", ""),
      "negativo": ("the dragon from the first image, doing the same action as the girl in the "
                   "second image, holding a book, keeping its own shape, colors and identity", INTRUSO),
      "ambos": ("the green plastic dragon from the first image, holding a black book with both "
                "hands in front of its chest, keeping its own shape, colors and identity", INTRUSO)}),
    ("sustitucion",
     "El sujeto principal es un dragon verde de plastico, y NO una chica? Y esta sentado encima "
     "de un pulpo morado grande?",
     {"palabras": ("the green plastic dragon from the first image, sitting on top of a large "
                   "purple octopus with orange suckers, dark background, keeping its own shape, "
                   "colors and identity", ""),
      "negativo": ("the dragon from the first image, in the same pose and position as the girl "
                   "in the second image, same framing and background", INTRUSO),
      "ambos": ("the green plastic dragon from the first image, sitting on top of a large purple "
                "octopus with orange suckers, dark background, keeping its own shape, colors and "
                "identity", INTRUSO)}),
]


def grafo(ref1, ref2, prompt, negativo, semilla):
    """Igual que el de la primera vuelta, pero con prompt negativo."""
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen-image-2.1-UC-Q8_0.gguf"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "20": {"class_type": "LoadImage", "inputs": {"image": ref1}},
        "21": {"class_type": "LoadImage", "inputs": {"image": ref2}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["2", 0], "vae": ["3", 0], "prompt": prompt, "negative_prompt": negativo,
            "resolution": 1024, "images.image_1": ["20", 0], "images.image_2": ["21", 0]}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1], "latent_image": ["4", 2],
            "seed": semilla, "steps": 25, "cfg": 1.0, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "qwen21/cond2"}},
    }


def generar(ref1, ref2, prompt, negativo, semilla):
    respuesta = peticion("/prompt", json.dumps(
        {"prompt": grafo(ref1, ref2, prompt, negativo, semilla)}).encode(),
        {"Content-Type": "application/json"})
    if respuesta.get("node_errors"):
        raise RuntimeError(json.dumps(respuesta["node_errors"])[:400])
    pid = respuesta["prompt_id"]
    while True:
        historial = peticion("/history/" + pid)
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--casos", default="")
    p.add_argument("--semilla", type=int, default=42)
    args = p.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)

    cfg = prompt_ia.ajustes()
    url = cfg["ia_url"].rstrip("/")
    modelo = cfg["ia_modelo"] or prompt_ia.modelo_disponible(url)
    elegidos = {c.strip() for c in args.casos.split(",") if c.strip()}

    resumen = []
    for nombre, pregunta, remedios in CASOS:
        if elegidos and nombre not in elegidos:
            continue
        print("\n=== " + nombre + " ===", flush=True)
        generadas = []
        for remedio, (prompt, negativo) in remedios.items():
            inicio = time.time()
            try:
                archivo = generar(DRAGON, CHICA, prompt, negativo, args.semilla)
            except Exception as e:
                print("  [%s] ERROR: %s" % (remedio, str(e)[:200]), flush=True)
                continue
            veredicto, razon = juzgar(archivo, pregunta, url, modelo)
            sujeto, condicion = veredicto.get("sujeto"), veredicto.get("condicion")
            marca = "OK      " if (sujeto and condicion) else ("a medias" if sujeto else "MAL     ")
            print("  [%s] %s sujeto=%s condicion=%s - %s - %.0f s"
                  % (remedio, marca, sujeto, condicion, archivo, time.time() - inicio))
            print("      juez: " + razon, flush=True)
            generadas.append((remedio, archivo))
            resumen.append({"caso": nombre, "remedio": remedio, "prompt": prompt,
                            "negativo": negativo, "archivo": archivo, "sujeto": sujeto,
                            "condicion": condicion, "juez": razon})
        if generadas:
            print("  hoja: %s" % hoja(nombre + "_remedios", DRAGON, CHICA, generadas), flush=True)

    (SALIDA / "resumen_remedios.json").write_text(
        json.dumps(resumen, indent=1, ensure_ascii=False), encoding="utf-8")
    buenos = sum(1 for r in resumen if r.get("sujeto") and r.get("condicion"))
    print("\n%d/%d cumplen sujeto y condicion" % (buenos, len(resumen)))
    for remedio in ("palabras", "negativo", "ambos"):
        filas = [r for r in resumen if r["remedio"] == remedio]
        ok = sum(1 for r in filas if r.get("sujeto") and r.get("condicion"))
        print("  %-9s %d/%d" % (remedio, ok, len(filas)))


if __name__ == "__main__":
    main()
