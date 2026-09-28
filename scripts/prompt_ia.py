"""Convierte una idea corta en un prompt de imagen, usando una IA local.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\prompt_ia.py "un buho de ceramica"
  ...\\python.exe scripts\\prompt_ia.py "cartel retro de cafe" --modo imagen

La direccion del servidor NO va en el codigo: se lee de config_local.json (que no se
publica) o de la variable de entorno EXO_IA_URL. Asi el repositorio no lleva la IP de
nadie. Ver config_local.ejemplo.json.
"""
import base64
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
    "- La referencia 2 solo puede aportar atributos SIN CUERPO: color, patron, material, "
    "acabado, estilo, fondo, expresion de la cara, o un segundo objeto que acompana.\n"
    "- NOMBRA ese atributo con palabras concretas ('bright yellow', 'matte black', 'colorful "
    "square pattern', 'smiling with wide eyes'). Escribir 'with the colors of the second "
    "image' a secas no hace nada cuando esos colores son oscuros o apagados.\n"
    "Formula base: <objeto de la referencia 1> + <atributo nombrado> + 'like the <cosa> in "
    "the second image'.\n"
    "\nREGLA CRITICA, medida con una bateria de 22 imagenes: la segunda referencia NO puede "
    "prestar una POSE, una ACCION, una ESCENA ni sustituir a su sujeto. Si se le pide eso, el "
    "sujeto de la segunda imagen se apodera de la escena y el objeto de la primera queda de "
    "decorado; con una persona o un personaje en la segunda imagen ocurre siempre, y ponerla "
    "en el prompt negativo no lo evita. Con dos objetos, en vez de trasladar la pose los "
    "fusiona en uno.\n"
    "POR ESO, cuando el usuario pida una pose, una postura, una accion, una actividad, una "
    "escena, una situacion, o que un objeto sustituya o reemplace a otro, o se ponga 'en "
    "lugar de' otro:\n"
    "- DESCRIBE esa condicion con palabras, mirando la segunda imagen y contando lo que ves "
    "('sitting astride with its legs spread wide apart to the sides', 'holding a black book "
    "with both hands in front of its chest', 'sitting on top of a large purple octopus with "
    "orange suckers, dark background').\n"
    "- Y NO menciones la segunda imagen en el prompt. Ni 'the second image', ni 'like the "
    "girl', ni 'same pose as'. Solo el objeto de la primera y la condicion en palabras. Asi "
    "acerto en los 3 casos que antes fallaban en los 9 intentos.\n"
    "- Describe SOLO lo que te han pedido, no la segunda imagen entera. Si te piden la pose, "
    "no anadas lo que el otro sujeto sostiene, ni los objetos que le acompanan, ni su fondo. "
    "Si te piden la escena, no cambies la forma del objeto. Todo lo que anadas de mas es algo "
    "que el usuario no ha pedido y que luego hay que imprimir.\n"
    "\nSEGUN QUE SE QUIERA TRANSFERIR DE LA SEGUNDA IMAGEN:\n"
    "- Pose, postura, accion, actividad, escena o sustitucion: EN PALABRAS, sin citar la "
    "segunda imagen (ver la regla critica de arriba).\n"
    "- Expresion o gesto de la cara: 'with the same facial expression as ...', nombrandola "
    "('smiling', 'angry', 'eyes closed'). Esta si funciona citando la segunda imagen, porque "
    "una cara no compite por ser el sujeto.\n"
    "- Forma o silueta: 'with the same shape and proportions as ...'.\n"
    "- Material o acabado: 'made of the same material as ...', nombrandolo ('glossy ceramic', "
    "'rough stone', 'brushed metal').\n"
    "- Vestuario o accesorios: 'wearing the same ... as in the second image', nombrandolo.\n"
    "- Estilo o acabado artistico: 'in the same style as ...', describiendolo.\n"
    "Anade siempre que se conserva la identidad del objeto de la primera, para que el "
    "generador no lo convierta en el de la segunda, pero NO menciones en esa frase lo "
    "que estas cambiando: nombra solo lo que se queda igual. Si transfieres el color, "
    "escribe 'keeping its own shape and identity' (sin 'colors'); si transfieres la "
    "forma, 'keeping its own colors, material and identity' (sin 'shape'); si "
    "transfieres el material, 'keeping its own shape and identity'. Pedir 'keeping its "
    "own colors' mientras se pinta de otro color es una contradiccion y el generador se "
    "queda a medias.\n"
    "Si el usuario pide varias condiciones a la vez, listalas separadas por comas en una sola "
    "frase, de la mas importante a la menos."
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


def _adjuntar(idea, imagenes):
    """Mensaje del usuario con las referencias adjuntas, si el modelo puede verlas."""
    partes = [{"type": "text", "text": idea}]
    for i, ruta in enumerate(imagenes, 1):
        datos = base64.b64encode(Path(ruta).read_bytes()).decode()
        partes.append({"type": "text", "text": f"Esta es la imagen de referencia {i}:"})
        partes.append({"type": "image_url",
                       "image_url": {"url": "data:image/png;base64," + datos}})
    return partes


def mejorar(idea, modo="3d", servidor=None, modelo=None, temperatura=None, semilla=None,
            tiempo=120, referencias=0, imagenes=None):
    """Devuelve (prompt, aviso). Si el servidor falla, devuelve la idea tal cual.

    'referencias' es cuantas imagenes de referencia hay cargadas (0, 1 o 2): cambia las
    instrucciones, porque con referencias el prompt describe un cambio y no una escena.

    'imagenes' son las rutas de esas referencias. Se le adjuntan al modelo, que es
    multimodal: sin verlas tiene que inventarse lo que hay en la segunda, y para una pose
    o una escena —que hay que describir con palabras— inventarsela es justo el fallo.
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

    aviso_imagenes = ""
    contenido = idea
    if imagenes:
        try:
            contenido = _adjuntar(idea, imagenes)
        except OSError as e:
            aviso_imagenes = f"no se pudieron adjuntar las referencias ({e})"

    cuerpo = {
        "model": nombre,
        "messages": [{"role": "system", "content": sistema},
                     {"role": "user", "content": contenido}],
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
    return texto, aviso_imagenes


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
