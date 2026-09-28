"""Bateria para las condiciones que se transfieren de la segunda referencia.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_condiciones.py

Sirve para saber si el generador obedece cuando lo que se pide de la segunda imagen no es
un color, sino una condicion: pose, expresion, actividad, o sustituir un objeto por otro.

Cada intencion se prueba DOS veces con la misma semilla:
- "literal": como lo escribiria alguien traduciendo su peticion palabra por palabra,
- "reglas": el mismo deseo pasado por la IA de prompts, con las reglas de dos referencias.

Asi se ve si las reglas aportan algo o si da igual como se pida. Un juez multimodal
responde por caso dos preguntas concretas (sujeto correcto, condicion cumplida) y se
guarda una hoja comparativa por intencion en pruebas\\condiciones.
"""
import argparse
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import prompt_ia
from probar_dos_referencias import COMFY, generar

SALIDA = Path(r"D:\AI3D\pruebas\condiciones")
DRAGON = "qwen_qwen_00002_.png"        # ref 1: dragon de plastico verde, sentado, neutro
CHICA = "qwen_qwen_00004_.png"         # ref 2: chica sentada a horcajadas, sonriendo, con libro
LAMPARA = "images (3).jpg"             # ref 2 alternativa: flexo inclinado hacia delante
CIERRE = 'JSON: {"sujeto":true/false,"condicion":true/false}'

# (nombre, ref1, ref2, deseo en espanol, prompt literal, pregunta al juez)
CASOS = [
    ("pose", DRAGON, CHICA,
     "quiero el dragon de la primera imagen con la pose de la chica de la segunda",
     "the dragon with the pose of the girl in the second image",
     "El sujeto principal es un dragon verde? Y esta sentado a horcajadas o con las piernas "
     "abiertas, como la chica de la referencia?"),
    ("expresion", DRAGON, CHICA,
     "el dragon de la primera imagen con la expresion de la cara de la chica de la segunda",
     "the dragon with the face expression of the second image",
     "El sujeto principal es un dragon verde? Y sonrie de forma suave, como la chica de la "
     "referencia, en lugar de tener cara neutra?"),
    ("actividad", DRAGON, CHICA,
     "que el dragon de la primera imagen este haciendo lo que hace la chica de la segunda, "
     "sosteniendo el libro",
     "the dragon doing what the girl in the second image does",
     "El sujeto principal es un dragon verde? Y sostiene un libro con las manos, como la chica "
     "de la referencia?"),
    ("sustitucion", DRAGON, CHICA,
     "pon el dragon de la primera imagen en lugar de la chica de la segunda foto",
     "replace the girl of the second image with the dragon",
     "El sujeto principal es un dragon verde, y NO una chica? Y esta sentado encima del pulpo "
     "morado, en el lugar que ocupaba la chica?"),
    ("pose_objeto", DRAGON, LAMPARA,
     "el dragon de la primera imagen inclinado hacia delante como la lampara de la segunda",
     "the dragon with the pose of the lamp in the second image",
     "El sujeto principal es un dragon verde? Y esta inclinado hacia delante, con la cabeza "
     "adelantada y baja?"),
]


def juzgar(archivo, pregunta, url, modelo):
    """Dos respuestas si/no del juez multimodal: sujeto correcto y condicion cumplida."""
    ruta = COMFY / "output/qwen21" / archivo
    b64 = base64.b64encode(ruta.read_bytes()).decode()
    orden = ("Mira la imagen y responde estas preguntas: " + pregunta +
             " Responde en una sola linea y termina con " + CIERRE)
    cuerpo = {"model": modelo, "max_tokens": 400, "temperature": 0.1, "stream": False,
              "chat_template_kwargs": {"enable_thinking": False},
              "messages": [{"role": "user", "content": [
                  {"type": "text", "text": orden},
                  {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}]}
    peticion = urllib.request.Request(url + "/chat/completions", json.dumps(cuerpo).encode(),
                                      {"Content-Type": "application/json"})
    with urllib.request.urlopen(peticion, timeout=180) as r:
        d = json.loads(r.read())
    texto = d["choices"][0]["message"]["content"]
    try:
        veredicto = json.loads(texto[texto.rindex("{"):texto.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        veredicto = {}
    return veredicto, " ".join(texto.split())[:300]


def hoja(nombre, ref1, ref2, resultados):
    """Una tira por intencion: las dos referencias y los dos resultados, etiquetados."""
    from PIL import Image, ImageDraw
    ims = [("ref 1", Image.open(COMFY / "input" / ref1).convert("RGB")),
           ("ref 2", Image.open(COMFY / "input" / ref2).convert("RGB"))]
    for etiqueta, archivo in resultados:
        ims.append((etiqueta.upper(), Image.open(COMFY / "output/qwen21" / archivo).convert("RGB")))
    for _, im in ims:
        im.thumbnail((340, 340))
    ancho = sum(i.width for _, i in ims) + 12 * len(ims)
    lienzo = Image.new("RGB", (ancho, max(i.height for _, i in ims) + 46), (18, 18, 18))
    dibujo = ImageDraw.Draw(lienzo)
    dibujo.text((6, 6), "condicion: " + nombre, fill=(235, 235, 235))
    x = 0
    for etiqueta, im in ims:
        lienzo.paste(im, (x, 40))
        dibujo.text((x + 6, 26), etiqueta, fill=(170, 200, 170))
        x += im.width + 12
    destino = SALIDA / (nombre + ".png")
    lienzo.save(destino)
    return destino


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--casos", default="", help="nombres separados por coma; vacio = todos")
    p.add_argument("--semilla", type=int, default=42)
    args = p.parse_args()
    SALIDA.mkdir(parents=True, exist_ok=True)

    cfg = prompt_ia.ajustes()
    url = cfg["ia_url"].rstrip("/")
    modelo = cfg["ia_modelo"] or prompt_ia.modelo_disponible(url)
    elegidos = {c.strip() for c in args.casos.split(",") if c.strip()}

    resumen = []
    for nombre, ref1, ref2, deseo, literal, pregunta in CASOS:
        if elegidos and nombre not in elegidos:
            continue
        con_reglas, aviso = prompt_ia.mejorar(deseo, modo="imagen", referencias=2, tiempo=180)
        if aviso:
            print("  AVISO: " + aviso)
        print("\n=== " + nombre + " ===", flush=True)
        print("  literal: " + literal)
        print("  reglas : " + con_reglas, flush=True)

        generadas = []
        for variante, prompt in (("literal", literal), ("reglas", con_reglas)):
            inicio = time.time()
            try:
                archivo = generar(ref1, ref2, prompt, args.semilla)
            except Exception as e:
                print("  [%s] ERROR: %s" % (variante, str(e)[:200]), flush=True)
                resumen.append({"caso": nombre, "variante": variante, "error": str(e)[:200]})
                continue
            veredicto, razon = juzgar(archivo, pregunta, url, modelo)
            sujeto, condicion = veredicto.get("sujeto"), veredicto.get("condicion")
            marca = "OK      " if (sujeto and condicion) else ("a medias" if sujeto else "MAL     ")
            print("  [%s] %s sujeto=%s condicion=%s - %s - %.0f s"
                  % (variante, marca, sujeto, condicion, archivo, time.time() - inicio))
            print("      juez: " + razon, flush=True)
            generadas.append((variante, archivo))
            resumen.append({"caso": nombre, "variante": variante, "prompt": prompt,
                            "archivo": archivo, "sujeto": sujeto, "condicion": condicion,
                            "juez": razon, "segundos": round(time.time() - inicio)})
        if generadas:
            print("  hoja: %s" % hoja(nombre, ref1, ref2, generadas), flush=True)

    (SALIDA / "resumen.json").write_text(json.dumps(resumen, indent=1, ensure_ascii=False),
                                         encoding="utf-8")
    buenos = sum(1 for r in resumen if r.get("sujeto") and r.get("condicion"))
    print("\n%d/%d cumplen sujeto y condicion - hojas en %s" % (buenos, len(resumen), SALIDA))


if __name__ == "__main__":
    main()
