"""Revisa una imagen generada y propone como corregir el prompt.

Tres capas:
- revision general: encuadre y material (un objeto, recortado, fondo, marca de agua,
  partes finas, transparencias).
- revision anatomica: solo en figuras y personajes. Extremidades de mas, partes
  fusionadas, manos mal resueltas, proporciones imposibles.
- encuadre por numeros: sin modelos, solo para corroborar recorte y tamano del objeto.

Sobre como se pregunta: el modelo contesta "todo bien" si se le pide el JSON de golpe.
Con una figura manipulada a proposito (una segunda cabeza pegada encima) el JSON directo
decia "sin defectos"; obligandole a enumerar en voz alta antes de responder, la detecto.
Por eso la revision anatomica describe primero y cierra con el JSON en la misma respuesta.
"""
import base64
import io
import json
import re
import urllib.error
import urllib.request

import numpy as np

from .prompt_ia import ajustes, modelo_disponible

TIEMPO = 240

REVISION_GENERAL = (
    "Revisas imagenes que se van a convertir en modelos 3D imprimibles. "
    "Mira la imagen y responde SOLO con este JSON, sin texto alrededor:\n"
    '{"tipo":"<objeto|animal|persona|personaje>","objetos":<cuantos objetos principales>,'
    '"recortado":<true si el objeto se sale del encuadre>,"fondo_liso":<true/false>,'
    '"sombras_duras":<true/false>,"texto_o_marca":<true/false>,'
    '"partes_finas":<true si hay partes delgadas o ramificadas>,'
    '"transparente":<true si es vidrio o translucido>,"que_es":"<en 3 palabras>",'
    '"problemas":["<breve>"]}'
)

REVISION_ANATOMIA = (
    "Revisas figuras que se van a imprimir en 3D.\n"
    "PASO 1: describe la figura parte por parte. Cuantas cabezas, brazos, piernas, manos, "
    "dedos por mano, alas y colas ves, y donde esta cada una. Cuenta en voz alta.\n"
    "PASO 2: termina con una unica linea que empiece por JSON: y contenga\n"
    '{"extremidades_de_mas":<true/false>,"partes_fusionadas":<true/false>,'
    '"asimetria_rara":<true/false>,"proporciones_raras":<true/false>,"manos_mal":<true/false>,'
    '"defectos":["<donde y que, en pocas palabras>"]}\n'
    "Cuenta solo lo que VES con claridad. No inventes defectos."
)

# Defectos que solo lo son si la imagen se va a convertir en 3D. En una imagen normal
# unos petalos finos, un cristal, dos objetos o un fondo con escenario no son un fallo:
# son decisiones. Marcarlos ahi seria nagear al usuario con reglas de impresion que no ha
# pedido, y el corrector le llenaria el prompt de "thick solid forms" sin motivo.
SOLO_3D = ("partes_finas", "transparente", "varios_objetos", "fondo_sucio", "sombras_duras")

# Peso de cada defecto al puntuar. Sirve para comparar intentos entre si.
PESOS = {
    "anatomia": 3, "recortado": 3, "varios_objetos": 2, "transparente": 2,
    "partes_finas": 2, "texto_o_marca": 2, "fondo_sucio": 1, "sombras_duras": 1,
    "encuadre": 1,
}

# Que anadir al prompt y al negativo por cada defecto. Fijo, para que la IA no improvise.
REMEDIOS = {
    "anatomia": ("correct anatomy, exactly two arms and two legs, five fingers per hand, "
                 "symmetrical body, clean silhouette",
                 "extra limbs, extra arms, extra legs, extra fingers, fused body parts, "
                 "deformed hands, mutated anatomy, malformed"),
    "recortado": ("full object visible, nothing cut off, wide framing with margin", "cropped, cut off"),
    "varios_objetos": ("exactly one single object, nothing else in the frame", "multiple objects, group"),
    "texto_o_marca": ("", "text, watermark, logo, signature, letters"),
    "partes_finas": ("thick solid forms, chunky proportions, no thin parts", "thin fragile parts, wires, hair strands"),
    "transparente": ("opaque matte material, solid surface", "glass, transparent, translucent, reflections"),
    "fondo_sucio": ("plain seamless neutral background", "busy background, scenery, props"),
    "sombras_duras": ("soft even studio lighting", "hard shadows, harsh light"),
    "encuadre": ("object fills the frame, centered", ""),
}


def _extraer_json(texto):
    """Coge el ultimo bloque {...} del texto: el modelo suele envolverlo en prosa."""
    if not texto:
        return {}
    bloques = re.findall(r"\{.*?\}", texto, re.S)
    for bloque in reversed(bloques):
        try:
            return json.loads(bloque)
        except json.JSONDecodeError:
            continue
    return {}


def _preguntar(imagen, pregunta, tokens=700, temperatura=0.2):
    """Una consulta con imagen a la IA local. Devuelve (texto, aviso)."""
    cfg = ajustes()
    url = cfg["ia_url"].rstrip("/")
    try:
        modelo = cfg["ia_modelo"] or modelo_disponible(url)
    except Exception as e:
        return "", f"no se pudo consultar {url}: {e}"

    buffer = io.BytesIO()
    imagen.convert("RGB").save(buffer, format="PNG")
    datos = base64.b64encode(buffer.getvalue()).decode()

    cuerpo = {
        "model": modelo,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": pregunta},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{datos}"}},
        ]}],
        "max_tokens": tokens,
        "temperature": temperatura,
        "stream": False,
        # Con el razonamiento puesto se gasta los tokens pensando y devuelve vacio.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    peticion = urllib.request.Request(url + "/chat/completions",
                                      data=json.dumps(cuerpo).encode("utf-8"),
                                      headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO) as r:
            respuesta = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return "", f"la IA no respondio ({e})"
    return (respuesta.get("choices") or [{}])[0].get("message", {}).get("content", "") or "", ""


# Senales de que el prompt pide una CONDICION de la segunda imagen (pose, gesto, accion,
# forma, material, vestuario, estilo o encuadre) y no solo un color o un patron. Cambia la
# correccion: hay que reforzar la identidad del objeto, no repetir la formula del atributo.
CONDICIONES = (
    "same pose", "same position", "same posture", "same facial expression", "same expression",
    "same gesture", "same action", "doing the same", "same shape", "same proportions",
    "same material", "same finish", "same style", "same outfit", "wearing the same",
    "same camera angle", "same framing", "instead of", "in place of", "replacing",
)

# De esas, las que llevan CUERPO. Medido con 22 imagenes: si el prompt pide una pose, una
# accion, una escena o sustituir a alguien mientras la segunda referencia sigue cargada, su
# sujeto se apodera de la escena y el objeto de la primera queda de decorado. Con una
# persona en la segunda imagen pasa siempre, y el prompt negativo no lo evita. Lo unico que
# funciono fue describir la condicion con palabras y soltar la segunda referencia: 3 de 3,
# y en la mitad de tiempo.
CONDICIONES_CON_CUERPO = (
    "same pose", "same position", "same posture", "same action", "doing the same",
    "instead of", "in place of", "replacing", "same framing",
)


def medir_encuadre(imagen):
    """Tres numeros que la IA mide mal: si toca el borde, cuanto ocupa y si esta centrado.

    La mascara sale del canal alfa si lo hay, o de comparar con el color del borde. Solo
    vale porque exigimos fondo liso; por eso estos numeros corroboran, no deciden.
    """
    from scipy import ndimage

    pequena = imagen.copy()
    pequena.thumbnail((512, 512))
    if pequena.mode == "RGBA" and np.asarray(pequena)[..., 3].min() < 250:
        objeto = np.asarray(pequena)[..., 3] > 128
    else:
        a = np.asarray(pequena.convert("RGB"), dtype=np.float32) / 255.0
        borde = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        color_fondo = np.median(borde, axis=0)
        ruido = float(borde.std(axis=0).mean())
        objeto = np.linalg.norm(a - color_fondo, axis=2) > max(0.10, ruido * 3)
        objeto = ndimage.binary_opening(objeto, iterations=2)

    etiquetas, cuantos = ndimage.label(objeto)
    if not cuantos:
        return {"area": 0.0, "toca_borde": False, "descentrado": 0.0, "trozos": 0}

    tamanos = ndimage.sum(objeto, etiquetas, range(1, cuantos + 1))
    principal = etiquetas == (int(np.argmax(tamanos)) + 1)
    alto, ancho = principal.shape
    centro_y, centro_x = ndimage.center_of_mass(principal)
    return {
        "area": round(float(principal.sum()) / (alto * ancho), 3),
        "toca_borde": bool(principal[0].any() or principal[-1].any()
                           or principal[:, 0].any() or principal[:, -1].any()),
        "descentrado": round(float(np.hypot(centro_x / ancho - 0.5, centro_y / alto - 0.5)), 3),
        "trozos": int((tamanos > tamanos.max() * 0.08).sum()),
    }


def criticar(imagen, revisar_anatomia="auto", referencias=0, para3d=True):
    """Informe completo de una imagen PIL. Devuelve un dict con defectos y puntuacion.

    'referencias' son las imagenes de referencia que se usaron al generar. Con dos, tener
    varios objetos en la imagen puede ser lo pedido ("las dos cosas juntas"), asi que deja
    de contar como defecto: si no, el bucle lo "corregiria" borrando el segundo objeto.

    'para3d' dice si la imagen se va a convertir en pieza. Con el puesto se exige lo que
    necesita la conversion (un objeto, macizo, opaco, sobre fondo liso); sin el solo se
    buscan los fallos que lo son en cualquier imagen: anatomia, recortes, marcas de agua y
    encuadre. Ver SOLO_3D.
    """
    informe = {"defectos": [], "detalle": [], "avisos": []}

    texto, aviso = _preguntar(imagen, REVISION_GENERAL, tokens=500)
    if aviso:
        informe["avisos"].append(aviso)
        return informe | {"puntuacion": 0.0, "apto": None, "general": {}, "anatomia": {}, "encuadre": {}}
    general = _extraer_json(texto)
    informe["general"] = general

    try:
        informe["encuadre"] = medir_encuadre(imagen)
    except Exception as e:
        informe["encuadre"] = {}
        informe["avisos"].append(f"no se pudo medir el encuadre: {e}")

    tipo = str(general.get("tipo", "")).lower()
    toca_anatomia = revisar_anatomia is True or (revisar_anatomia == "auto" and tipo and tipo != "objeto")
    anatomia = {}
    if toca_anatomia:
        texto_a, aviso_a = _preguntar(imagen, REVISION_ANATOMIA, tokens=800)
        if aviso_a:
            informe["avisos"].append(aviso_a)
        anatomia = _extraer_json(texto_a)
    informe["anatomia"] = anatomia

    def marcar(clave, motivo):
        if not para3d and clave in SOLO_3D:
            # En modo imagen se anota, pero no cuenta ni baja la puntuacion.
            informe["notas"] = informe.get("notas", []) + [motivo + " (solo importa para 3D)"]
            return
        if clave not in informe["defectos"]:
            informe["defectos"].append(clave)
        informe["detalle"].append(motivo)

    # --- encuadre y material ---
    encuadre = informe["encuadre"]
    # "recortado" solo cuenta si tambien lo ve la medida: la IA lo confunde con las
    # barras de marca de agua que tocan el borde.
    if general.get("recortado") and encuadre.get("toca_borde"):
        marcar("recortado", "el objeto se sale del encuadre")
    if (general.get("objetos") or 1) > 1:
        if referencias >= 2:
            informe["notas"] = informe.get("notas", []) + [
                f"hay {general.get('objetos')} objetos, pero con dos referencias puede ser lo pedido"]
        else:
            marcar("varios_objetos", f"hay {general.get('objetos')} objetos en la imagen")
    if general.get("texto_o_marca"):
        marcar("texto_o_marca", "hay texto o marca de agua")
    if general.get("partes_finas"):
        marcar("partes_finas", "tiene partes finas o ramificadas")
    if general.get("transparente"):
        marcar("transparente", "es de material transparente")
    if general.get("fondo_liso") is False:
        marcar("fondo_sucio", "el fondo no es liso")
    if general.get("sombras_duras"):
        marcar("sombras_duras", "tiene sombras duras")
    if encuadre.get("area", 1) and (encuadre["area"] < 0.12 or encuadre.get("descentrado", 0) > 0.15):
        # Con dos referencias caben dos cosas en el cuadro, asi que cada una ocupa menos y
        # queda descentrada por fuerza: es lo pedido, no un defecto. El corrector ya lo
        # ignoraba, y marcarlo aqui solo hundia la puntuacion del intento bueno.
        if referencias >= 2:
            informe["notas"] = informe.get("notas", []) + [
                f"objeto pequeno o descentrado (area {encuadre.get('area')}), normal al combinar dos referencias"]
        else:
            marcar("encuadre", f"objeto pequeno o descentrado (area {encuadre.get('area')})")

    # --- anatomia: la lista de defectos manda sobre las banderas ---
    # En la prueba con dos cabezas las banderas decian false y fue la lista la que lo vio.
    if anatomia:
        problemas = [p for p in (anatomia.get("defectos") or []) if str(p).strip()]
        banderas = [k for k in ("extremidades_de_mas", "partes_fusionadas", "asimetria_rara",
                                "proporciones_raras", "manos_mal") if anatomia.get(k)]
        if problemas or banderas:
            marcar("anatomia", "anatomia: " + "; ".join([str(p) for p in problemas] or banderas))

    informe["puntuacion"] = round(10.0 - sum(PESOS.get(d, 1) for d in informe["defectos"]), 1)
    informe["apto"] = not informe["defectos"]
    informe["problemas_ia"] = general.get("problemas") or []
    informe["que_es"] = general.get("que_es", "")
    informe["tipo"] = tipo
    informe["referencias"] = referencias
    informe["para3d"] = para3d
    return informe


def corregir(prompt, negativo, informe, semilla_actual=0, referencias=None, para3d=None):
    """Prompt y negativo corregidos segun los defectos. Reglas fijas, sin improvisar.

    Con referencias cargadas el prompt no describe una escena sino un cambio, asi que no
    se le pegan frases de encuadre que contradirian la imagen de partida, y con dos nunca
    se pide "un solo objeto": seria borrar la combinacion que se ha pedido.
    """
    if referencias is None:
        referencias = int(informe.get("referencias") or 0)
    if para3d is None:
        para3d = bool(informe.get("para3d", True))
    anadir, negar = [], []
    for defecto in informe.get("defectos", []):
        if referencias >= 2 and defecto in ("varios_objetos", "encuadre"):
            continue
        if not para3d and defecto in SOLO_3D:
            continue
        if referencias >= 1 and defecto in ("fondo_sucio", "sombras_duras"):
            # Con referencia, el fondo y la luz vienen de la imagen original; pedir otra
            # cosa pelea con ella en vez de arreglar nada.
            continue
        mas, menos = REMEDIOS.get(defecto, ("", ""))
        if mas and mas.lower() not in prompt.lower():
            anadir.append(mas)
        if menos:
            negar.extend(m.strip() for m in menos.split(",") if m.strip().lower() not in (negativo or "").lower())

    nuevo = prompt.rstrip(" .,")
    if anadir:
        nuevo += ", " + ", ".join(anadir)
    if referencias >= 2:
        # Se conserva la formula medida: el objeto sale de la referencia 1 y lo que se toma
        # de la 2 hay que nombrarlo apuntando a ella. Si lo que se pide es una condicion
        # (pose, gesto, accion, material, estilo) y no un color, hay que blindar ademas la
        # identidad del objeto, o el generador lo reemplaza por el de la segunda imagen.
        if not any(c in nuevo.lower() for c in CONDICIONES):
            if "second image" not in nuevo.lower():
                nuevo += ", keeping the object from the first image and the attribute from the second image"
        elif "identity" not in nuevo.lower():
            nuevo += ", keeping its own shape, colors and identity from the first image"
    nuevo_negativo = ", ".join(filter(None, [(negativo or "").strip(" ,")] + negar))

    cambios = {"seed": int(semilla_actual) + 1013904223 & 0xFFFFFFFF}   # siempre otra semilla
    if "anatomia" in informe.get("defectos", []) or "partes_finas" in informe.get("defectos", []):
        cambios["steps"] = 28   # mas pasos ayudan a resolver manos y detalles finos
    if referencias >= 2 and any(c in nuevo.lower() for c in CONDICIONES_CON_CUERPO):
        # La condicion ya esta descrita en el prompt; la segunda referencia solo puede
        # robarle el sitio al sujeto. Se suelta y se deja dicho por que.
        cambios["quitar_referencia_2"] = True
        cambios["motivo_referencia"] = (
            "se suelta la referencia 2: con una pose, una accion o una sustitucion, su sujeto "
            "se apodera de la escena.")
    return nuevo, nuevo_negativo, cambios


def resumen(informe):
    """Texto corto para mostrar en un nodo o en la interfaz."""
    if informe.get("avisos") and not informe.get("general"):
        return "AVISO: " + "; ".join(informe["avisos"])
    lineas = [f"{informe.get('que_es', '?')} ({informe.get('tipo', '?')}) · puntuacion {informe.get('puntuacion')}/10"]
    if informe.get("defectos"):
        lineas += [f"  - {d}" for d in informe.get("detalle", [])]
    else:
        lineas.append("  sin defectos detectados")
    encuadre = informe.get("encuadre") or {}
    if encuadre:
        lineas.append(f"  encuadre: ocupa {encuadre.get('area')} · toca borde {encuadre.get('toca_borde')}")
    for aviso in informe.get("avisos", []):
        lineas.append(f"  AVISO: {aviso}")
    return "\n".join(lineas)
