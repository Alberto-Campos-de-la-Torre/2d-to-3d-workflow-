"""Convierte una idea corta en un prompt de imagen, usando una IA local.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\prompt_ia.py "un buho de ceramica"
  ...\\python.exe scripts\\prompt_ia.py "cartel retro de cafe" --modo imagen

La direccion del servidor NO va en el codigo: se lee de config_local.json (que no se
publica) o de la variable de entorno EXO_IA_URL. Asi el repositorio no lleva la IP de
nadie. Ver config_local.ejemplo.json.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config_local.json"
POR_DEFECTO = {"ia_url": "http://127.0.0.1:8080/v1", "ia_modelo": "", "ia_temperatura": 0.8}

# Lo aprendido midiendo 10 piezas reales: el generador debe entregar un objeto entero,
# centrado y sobre fondo liso, o la parte 3D fabrica geometria de la sombra y del fondo.
SISTEMA_3D = (
    "Escribes prompts en ingles para un generador de imagenes. La imagen se convertira "
    "despues en un modelo 3D imprimible, asi que debe cumplir sin excepcion:\n"
    "- UN solo objeto, completo y entero en el encuadre, nada recortado.\n"
    "- Centrado, en vista de tres cuartos, sobre fondo liso y neutro.\n"
    "- Luz pareja y suave, sin sombras duras ni reflejos fuertes.\n"
    "- Sin texto, sin marcas de agua, sin personas, sin escenario ni otros objetos.\n"
    "- Formas macizas y bien definidas: evita telas al viento, humo, pelo suelto, "
    "estructuras muy ramificadas y materiales transparentes, que no se pueden imprimir.\n"
    "Responde UNICAMENTE con el prompt, en una sola linea, sin comillas ni explicaciones."
)

SISTEMA_IMAGEN = (
    "Escribes prompts en ingles para un generador de imagenes. Amplias la idea del usuario "
    "con composicion, luz, materiales, estilo y calidad, manteniendo su intencion. "
    "Responde UNICAMENTE con el prompt, en una sola linea, sin comillas ni explicaciones."
)

MODOS = {"3d": SISTEMA_3D, "imagen": SISTEMA_IMAGEN}

# Reglas medidas con una bateria de 10 casos sobre Qwen-Image 2.1 (ver
# scripts/pruebas/probar_dos_referencias.py). Se anaden solo cuando hay referencias
# cargadas, porque cambian por completo la forma correcta de redactar el prompt.
REGLAS_UNA_REFERENCIA = (
    "\n\nHAY 1 IMAGEN DE REFERENCIA. El prompt no describe la escena entera, sino EL CAMBIO "
    "sobre esa imagen ('remove the background', 'make it matte red', 'turn it into a ceramic "
    "figurine'). Menciona el objeto para anclarlo, y no describas de nuevo lo que ya se ve."
)
REGLAS_DOS_REFERENCIAS = (
    "\n\nHAY 2 IMAGENES DE REFERENCIA, y se comprobo como responde el generador:\n"
    "- El OBJETO sale siempre de la referencia 1. Nunca escribas 'the object from the second "
    "image': el generador lo ignora y usa igualmente el de la primera.\n"
    "- La referencia 2 solo aporta un atributo: color, patron, material, fondo, o un segundo "
    "objeto que acompana.\n"
    "- NOMBRA ese atributo con palabras concretas ('bright yellow', 'matte black', 'colorful "
    "square pattern'). Escribir 'with the colors of the second image' a secas no hace nada "
    "cuando esos colores son oscuros o apagados.\n"
    "Formula que funciona: <objeto de la referencia 1> + <atributo nombrado> + 'like the "
    "<cosa> in the second image'."
)


def ajustes():
    """config_local.json, pisado por variables de entorno si las hay."""
    datos = dict(POR_DEFECTO)
    if CONFIG.exists():
        try:
            datos.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    datos["ia_url"] = os.environ.get("EXO_IA_URL", datos["ia_url"])
    datos["ia_modelo"] = os.environ.get("EXO_IA_MODELO", datos["ia_modelo"])
    return datos


def modelo_disponible(url, tiempo=8):
    """Primer modelo que sirve el servidor, para no tener que nombrarlo a mano."""
    with urllib.request.urlopen(url.rstrip("/") + "/models", timeout=tiempo) as r:
        datos = json.loads(r.read())
    lista = datos.get("data") or datos.get("models") or []
    return (lista[0].get("id") or lista[0].get("name")) if lista else ""


def mejorar(idea, modo="3d", servidor=None, modelo=None, temperatura=None, semilla=None,
            tiempo=120, referencias=0):
    """Devuelve (prompt, aviso). Si el servidor falla, devuelve la idea tal cual.

    'referencias' es cuantas imagenes de referencia hay cargadas (0, 1 o 2): cambia las
    instrucciones, porque con referencias el prompt describe un cambio y no una escena.
    """
    cfg = ajustes()
    url = (servidor or cfg["ia_url"]).rstrip("/")
    idea = (idea or "").strip()
    if not idea:
        return "", "no habia idea que ampliar"

    try:
        nombre = modelo or cfg["ia_modelo"] or modelo_disponible(url)
    except Exception as e:
        return idea, f"no se pudo consultar {url}: {e}"

    sistema = MODOS.get(modo, SISTEMA_3D)
    if referencias >= 2:
        sistema += REGLAS_DOS_REFERENCIAS
    elif referencias == 1:
        sistema += REGLAS_UNA_REFERENCIA

    cuerpo = {
        "model": nombre,
        "messages": [{"role": "system", "content": sistema},
                     {"role": "user", "content": idea}],
        "max_tokens": 400,
        "temperature": float(cfg["ia_temperatura"] if temperatura is None else temperatura),
        "stream": False,
        # Qwen3 razona antes de responder: sin esto se gasta los tokens pensando y
        # devuelve contenido vacio, ademas de tardar mucho mas.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if semilla is not None:
        cuerpo["seed"] = int(semilla)

    peticion = urllib.request.Request(url + "/chat/completions",
                                      data=json.dumps(cuerpo).encode("utf-8"),
                                      headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=tiempo) as r:
            respuesta = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return idea, f"la IA no respondio ({e}); se usa la idea tal cual"

    texto = (respuesta.get("choices") or [{}])[0].get("message", {}).get("content", "")
    texto = " ".join(texto.split()).strip().strip('"').strip("'")
    if not texto:
        return idea, "la IA devolvio una respuesta vacia; se usa la idea tal cual"
    return texto, ""


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("idea")
    p.add_argument("--modo", choices=sorted(MODOS), default="3d")
    p.add_argument("--servidor", default=None)
    p.add_argument("--modelo", default=None)
    p.add_argument("--semilla", type=int, default=None)
    p.add_argument("--referencias", type=int, default=0, choices=[0, 1, 2],
                   help="cuantas imagenes de referencia se van a usar")
    args = p.parse_args()

    prompt, aviso = mejorar(args.idea, args.modo, args.servidor, args.modelo,
                            semilla=args.semilla, referencias=args.referencias)
    if aviso:
        print(f"AVISO: {aviso}")
    print(prompt)


if __name__ == "__main__":
    main()
