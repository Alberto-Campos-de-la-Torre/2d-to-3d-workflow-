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

# Una sola pregunta para toda la imagen no sirve cuando hay dos personas: "cuatro brazos"
# es lo normal con dos cuerpos y tambien es el sintoma de que a uno le sobra uno, y el
# modelo resuelve la duda siempre a favor de "esta bien". Por eso la revision va por
# sujeto, sobre un recorte ampliado de cada uno, y con una pasada aparte para la zona
# donde los cuerpos se tocan, que es donde salen los brazos que no son de nadie.
REVISION_SUJETOS = (
    "Cuenta las figuras con cuerpo que hay en la imagen (personas, animales o personajes; "
    "no cuentes objetos).\n"
    "PASO 1: di cuantas hay y describelas de izquierda a derecha, una por linea, por lo que "
    "las distingue (ropa, color de pelo, tamano).\n"
    "PASO 2: termina con una unica linea que empiece por JSON: y contenga\n"
    '{"cuantas":<numero>,"figuras":[{"donde":"<izquierda|centro|derecha>",'
    '"quien":"<3 o 4 palabras que la distingan>"}]}'
)

REVISION_ANATOMIA = (
    "Revisas una figura buscando errores de anatomia.\n"
    "PASO 1: describela parte por parte. Cuantas cabezas, brazos, piernas, manos, dedos por "
    "mano, alas y colas ves, y donde esta cada una. Cuenta en voz alta.\n"
    "PASO 2: termina con una unica linea que empiece por JSON: y contenga\n"
    '{"extremidades_de_mas":<true/false>,"partes_fusionadas":<true/false>,'
    '"asimetria_rara":<true/false>,"proporciones_raras":<true/false>,"manos_mal":<true/false>,'
    '"defectos":["<donde y que, en pocas palabras>"]}\n'
    "Cuenta solo lo que VES con claridad. No inventes defectos."
)

# Por sujeto. Lo que mas resultado da es obligar a SEGUIR cada brazo desde la mano hasta el
# hombro: el fallo tipico en una escena de dos personas es un brazo que aparece apoyado
# sobre el otro cuerpo sin nada que lo conecte, y preguntando "cuantos brazos hay" no sale.
REVISION_UN_SUJETO = (
    "En esta imagen hay varias figuras. Fijate SOLO en esta: {quien} ({donde}). Ignora por "
    "completo a las demas; lo que sea de otra figura no es un defecto de esta.\n"
    "PASO 1, cuenta en voz alta y SOLO de esa figura: cabezas, brazos, manos, dedos de cada "
    "mano que se vea entera, piernas y pies.\n"
    "PASO 2, sigue cada brazo y cada pierna desde la mano o el pie hasta el hombro o la "
    "cadera, y di en voz alta si puedes recorrerlo entero o si se pierde, se corta, sale de "
    "un sitio imposible o no se ve de quien es.\n"
    "PASO 3, mira las manos de cerca: cuantos dedos tiene cada una, si hay dedos pegados, "
    "de mas, de menos, o torcidos hacia donde no deben.\n"
    "PASO 4: termina con una unica linea que empiece por JSON: y contenga\n"
    '{"brazos":<numero>,"manos":<numero>,"piernas":<numero>,'
    '"extremidades_de_mas":<true/false>,"partes_fusionadas":<true/false>,'
    '"miembro_sin_conectar":<true si algun brazo o pierna no llega a un cuerpo>,'
    '"asimetria_rara":<true/false>,"proporciones_raras":<true/false>,"manos_mal":<true/false>,'
    '"defectos":["<donde y que, en pocas palabras>"]}\n'
    "Cuenta solo lo que VES con claridad. Si una parte queda tapada por otra figura o por "
    "el borde, NO la pongas en la lista de defectos: una parte tapada no es un fallo, y la "
    "lista es solo para fallos reales. Si no encuentras ninguno, deja la lista vacia."
)

# La zona donde los cuerpos se tocan o se solapan.
REVISION_CONTACTO = (
    "Este es un recorte ampliado de la zona donde dos figuras se tocan o se solapan.\n"
    "REGLA: que dos manos se tapen entre si al darse la mano, agarrarse o abrazarse es "
    "NORMAL. Que una parte quede escondida detras de otra tambien. Eso no es un fallo.\n"
    "PASO 1: enumera en voz alta cada mano, brazo y pierna que ves, y di de quien es "
    "siguiendolo hasta el cuerpo del que sale.\n"
    "PASO 2: di cuales de esas partes se explican bien y cuales no.\n"
    "PASO 3: da UN veredicto de la zona, con una de estas tres palabras:\n"
    "  limpio     = todo lo que ves se explica por partes normales que se tapan.\n"
    "  sospechoso = algo no te cuadra, pero podria ser que este tapado.\n"
    "  fallo      = ves CON CLARIDAD una de estas cosas: una mano con dedos de mas o de "
    "menos, dedos fundidos en una masa sin separacion, dedos naciendo de la muneca o del "
    "dorso, un brazo o una pierna que no llega a ningun cuerpo, una mano sin brazo, o dos "
    "cuerpos fundidos en uno.\n"
    "PASO 4: termina con una unica linea que empiece por JSON: y contenga\n"
    '{"veredicto":"limpio|sospechoso|fallo","que_pasa":"<donde y que, en pocas palabras>"}\n'
    "En la duda, 'sospechoso'. Reserva 'fallo' para lo que ves sin lugar a dudas."
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
    # Era el unico remedio que iba solo al negativo, y el negativo apenas hace nada a
    # cfg 1: por eso el texto ilegible de una camiseta no se corregia nunca.
    "texto_o_marca": ("plain clean surfaces with no writing, no letters and no logos",
                      "text, watermark, logo, signature, letters"),
    "partes_finas": ("thick solid forms, chunky proportions, no thin parts", "thin fragile parts, wires, hair strands"),
    "transparente": ("opaque matte material, solid surface", "glass, transparent, translucent, reflections"),
    "fondo_sucio": ("plain seamless neutral background", "busy background, scenery, props"),
    "sombras_duras": ("soft even studio lighting", "hard shadows, harsh light"),
    "encuadre": ("object fills the frame, centered", ""),
}


def _extraer_json(texto):
    """Coge el ultimo bloque {...} del texto: el modelo suele envolverlo en prosa.

    Se emparejan las llaves a mano en vez de con una expresion regular: con {"a":[{"b":1}]}
    una expresion no codiciosa corta en la primera llave de cierre y devuelve basura, que
    es como la revision por sujeto se quedaba sin leer y caia al camino de una sola pasada.
    """
    if not texto:
        return {}
    bloques, pila = [], []
    for i, c in enumerate(texto):
        if c == "{":
            pila.append(i)
        elif c == "}" and pila:
            inicio = pila.pop()
            if not pila:
                bloques.append(texto[inicio:i + 1])
    for bloque in reversed(bloques):
        try:
            datos = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        if isinstance(datos, dict):
            return datos
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


# El modelo cuela en la lista cosas que el mismo aclara que no son fallos ("mano tapada
# por la otra figura", "no es defecto propio"). Se descartan: si se cuentan, el bucle se
# pone a corregir una oclusion, que no tiene arreglo por prompt.
NO_ES_DEFECTO = ("no es defecto", "no es un defecto", "no es un fallo", "sin defecto",
                 "tapad", "ocult", "cubiert", "no se ve por", "fuera de encuadre",
                 "no visible", "correcto", "normal para")


def _es_defecto(texto):
    bajo = str(texto).strip().lower()
    if not bajo:
        return False
    return not any(marca in bajo for marca in NO_ES_DEFECTO)


# Cuentas: entre pasadas se queda la mas alta, no la primera.
CUENTAS_ANATOMIA = ("manos_con_dedos_raros", "brazos_sin_dueno")

BANDERAS_ANATOMIA = ("extremidades_de_mas", "partes_fusionadas", "asimetria_rara",
                     "proporciones_raras", "manos_mal", "miembro_sin_conectar",
                     "miembro_sin_dueno", "cuerpos_fundidos", "mano_suelta")


def _insistir(imagen, pregunta, tokens, ciclos, avisos):
    """Repite la pregunta hasta 'ciclos' veces y devuelve la union de lo encontrado.

    El modelo no es ciego, es inconstante: en el brazo mal conectado de dos ninas acerto en
    una pasada suelta y no dijo nada en la siguiente, con la misma imagen. Como lo que se
    quiere evitar son los fallos que se escapan, se pregunta otra vez cuando una pasada sale
    limpia, subiendo la temperatura para que no repita la misma lectura; en cuanto una
    encuentra algo se para, asi que una imagen con defectos no cuesta mas que antes.
    """
    union, visto = {}, set()
    for intento in range(max(1, int(ciclos))):
        texto, aviso = _preguntar(imagen, pregunta, tokens=tokens,
                                  temperatura=0.2 + 0.3 * intento)
        if aviso:
            avisos.append(aviso)
            continue
        datos = _extraer_json(texto)
        for clave, valor in datos.items():
            if clave == "defectos":
                continue
            if clave in BANDERAS_ANATOMIA:
                union[clave] = bool(union.get(clave)) or bool(valor)
            elif clave == "veredicto":
                orden = {"limpio": 0, "sospechoso": 1, "fallo": 2}
                actual = orden.get(str(union.get(clave, "limpio")).lower(), 0)
                if orden.get(str(valor).lower(), 0) >= actual:
                    union[clave] = valor
                    union["que_pasa"] = None   # se rellena abajo con el de esta pasada
            elif clave == "que_pasa":
                if union.get("que_pasa") is None or "que_pasa" not in union:
                    union["que_pasa"] = valor
            else:
                union.setdefault(clave, valor)
        for d in (datos.get("defectos") or []):
            d = str(d).strip()
            if _es_defecto(d) and d.lower() not in visto:
                visto.add(d.lower())
                union.setdefault("defectos", []).append(d)
        if (union.get("defectos")
                or str(union.get("veredicto", "")).lower().startswith("fallo")
                or any(union.get(b) for b in BANDERAS_ANATOMIA)):
            break
    union.setdefault("defectos", [])
    union["ciclos"] = intento + 1
    return union


def _ampliar(imagen, caja, lado=1152):
    """Recorta y agranda, porque una mano en una foto de dos cuerpos enteros son 40 pixeles."""
    trozo = imagen.crop(caja)
    if trozo.width < 8 or trozo.height < 8:
        return imagen
    escala = lado / max(trozo.width, trozo.height)
    if escala > 1:
        from PIL import Image as _Image
        trozo = trozo.resize((int(trozo.width * escala), int(trozo.height * escala)),
                             _Image.LANCZOS)
    return trozo


def _columna(imagen, i, n, margen=0.22):
    """Caja de la figura i de n, contando de izquierda a derecha, con margen de sobra.

    Sin detector no hay cajas de verdad: se reparte el ancho y se solapa bastante, que es
    suficiente cuando las figuras estan una al lado de otra, que es el caso que falla. La
    pregunta ademas nombra a quien hay que mirar, asi que si en el recorte entra media
    figura vecina no se confunde.
    """
    ancho, alto = imagen.size
    paso = ancho / max(n, 1)
    izq = max(0, int((i * paso) - paso * margen))
    der = min(ancho, int(((i + 1) * paso) + paso * margen))
    return (izq, 0, der, alto)


def _bandas_contacto(imagen, n):
    """Dos recortes de la zona donde se tocan los cuerpos: hombros y cintura.

    Mirar la franja entera de una vez deja las manos en 100 pixeles y se le escapan. En dos
    mitades cada mano sale al doble de tamano, que es la diferencia entre ver unos dedos
    fundidos y no verlos.
    """
    ancho, alto = imagen.size
    if n == 2:
        izq, der = int(ancho * 0.20), int(ancho * 0.80)
    else:
        izq, der = 0, ancho
    # Se probo partirla en dos mitades para que las manos salieran mas grandes y salio
    # peor: aparecio una falsa alarma nueva (dos cuerpos abrazados leidos como fundidos) y
    # el fallo pequeno que se buscaba siguio sin verse. Se queda la franja entera.
    return [("zona de contacto", (izq, int(alto * 0.05), der, int(alto * 0.75)))]


def _revisar_contacto(imagen, cuantas, ciclos, avisos):
    """Veredicto de la zona de contacto, mirando cada mitad y quedandose con el peor."""
    orden = {"limpio": 0, "sospechoso": 1, "fallo": 2}
    peor = {"veredicto": "limpio", "que_pasa": "", "donde": ""}
    for donde, caja in _bandas_contacto(imagen, cuantas):
        zona = _insistir(_ampliar(imagen, caja), REVISION_CONTACTO, 700, ciclos, avisos)
        nivel = orden.get(str(zona.get("veredicto", "")).lower(), 0)
        if nivel > orden.get(peor["veredicto"], 0):
            peor = {"veredicto": str(zona.get("veredicto")).lower(),
                    "que_pasa": str(zona.get("que_pasa") or ""), "donde": donde}
        if nivel >= 2:
            break
    return peor


def _revisar_anatomia(imagen, informe, ciclos=2):
    """Anatomia por sujeto. Devuelve un unico dict con la union de lo encontrado.

    Con una sola figura se pregunta una vez, como siempre. Con dos o mas se pregunta por
    cada una sobre su recorte ampliado, y una vez mas sobre la zona de contacto. Cualquier
    pasada que encuentre algo cuenta: lo que se buscaba arreglar son los fallos que se
    escapan, no los que se inventan.
    """
    texto, aviso = _preguntar(imagen, REVISION_SUJETOS, tokens=400)
    if aviso:
        informe["avisos"].append(aviso)
    reparto = _extraer_json(texto)
    figuras = [f for f in (reparto.get("figuras") or []) if isinstance(f, dict)]
    cuantas = int(reparto.get("cuantas") or len(figuras) or 1)
    informe["figuras"] = figuras

    if cuantas < 2:
        return _insistir(imagen, REVISION_ANATOMIA, 800, ciclos, informe["avisos"])

    # Si el reparto no trajo descripciones utiles se inventan por posicion, que es lo unico
    # que hace falta para dirigir la mirada.
    if len(figuras) != cuantas:
        sitios = ["la de la izquierda", "la del centro", "la de la derecha"]
        figuras = [{"donde": sitios[min(i, 2)], "quien": "la figura %d" % (i + 1)}
                   for i in range(cuantas)]

    union = {"extremidades_de_mas": False, "partes_fusionadas": False, "asimetria_rara": False,
             "proporciones_raras": False, "manos_mal": False, "defectos": [], "por_sujeto": []}
    for i, figura in enumerate(figuras[:4]):
        recorte = _ampliar(imagen, _columna(imagen, i, cuantas))
        # Reemplazo a mano, no .format: la plantilla lleva dentro el JSON de respuesta y
        # sus llaves harian saltar al formateador.
        pregunta = (REVISION_UN_SUJETO
                    .replace("{quien}", figura.get("quien") or "la figura %d" % (i + 1))
                    .replace("{donde}", figura.get("donde") or "sin precisar"))
        parte = _insistir(recorte, pregunta, 900, ciclos, informe["avisos"])
        union["por_sujeto"].append({"quien": figura.get("quien"), **parte})
        for bandera in ("extremidades_de_mas", "partes_fusionadas", "asimetria_rara",
                        "proporciones_raras", "manos_mal"):
            union[bandera] = union[bandera] or bool(parte.get(bandera))
        if parte.get("miembro_sin_conectar"):
            union["partes_fusionadas"] = True
        etiqueta = figura.get("quien") or ("figura %d" % (i + 1))
        for d in (parte.get("defectos") or []):
            if _es_defecto(d):
                union["defectos"].append("%s: %s" % (etiqueta, d))

    zona = _revisar_contacto(imagen, cuantas, ciclos, informe["avisos"])
    union["contacto"] = zona
    # El veredicto sale de las cuentas, no de la prosa: preguntado en abierto, el modelo
    # llamaba "dedos fusionados" a un apreton de manos bien hecho, que es solo dos manos
    # tapandose. Con las cuentas delante, eso deja de ser un defecto.
    # Tres niveles en vez de si/no. Preguntado en abierto, el modelo llamaba fallo a un
    # apreton de manos normal; obligado a elegir entre tres, un apreton sale 'limpio' y una
    # mano deforme sale 'fallo'. Lo de en medio se anota pero no puntua, que es justo lo que
    # no se sabe decidir mirando una foto de dos cuerpos enteros.
    veredicto = str(zona.get("veredicto", "")).strip().lower()
    que_pasa = str(zona.get("que_pasa") or "").strip()
    if veredicto.startswith("fallo"):
        union["partes_fusionadas"] = True
        union["defectos"].append("entre las figuras (%s): %s" % (
            zona.get("donde") or "zona de contacto", que_pasa or "anatomia mal resuelta"))
    elif veredicto.startswith("sospech") and que_pasa:
        union["dudas"] = union.get("dudas", []) + ["entre las figuras: %s" % que_pasa]
    return union


def criticar(imagen, revisar_anatomia="auto", referencias=0, para3d=True, ciclos=2):
    """Informe completo de una imagen PIL. Devuelve un dict con defectos y puntuacion.

    'referencias' son las imagenes de referencia que se usaron al generar. Con dos, tener
    varios objetos en la imagen puede ser lo pedido ("las dos cosas juntas"), asi que deja
    de contar como defecto: si no, el bucle lo "corregiria" borrando el segundo objeto.

    'ciclos' es cuantas veces se insiste en cada pregunta de anatomia cuando la primera
    sale limpia. El modelo es inconstante y se le escapan fallos que ve perfectamente en
    otra pasada; en cuanto una encuentra algo se para.

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
        anatomia = _revisar_anatomia(imagen, informe, ciclos)
    informe["anatomia"] = anatomia
    for duda in (anatomia.get("dudas") or []):
        informe["notas"] = informe.get("notas", []) + ["a revisar a ojo: " + duda]

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


SISTEMA_USUARIO = (
    "Eres quien reescribe el prompt de un generador de imagenes. Tienes delante la imagen "
    "que salio, el prompt con el que se hizo, y lo que la persona que la ha mirado dice que "
    "esta mal. Ella manda: lo que diga es un fallo, es un fallo, aunque a ti te parezca "
    "bien.\n"
    "PASO 1: enumera en voz alta, una por una, las cosas que te dice. Para cada una, mira la "
    "imagen y di si la ves y donde.\n"
    "PASO 2: para cada una, decide que cambiar: que anadir al prompt, que anadir al prompt "
    "negativo, o si no tiene arreglo por palabras y hay que cambiar la semilla (es el caso "
    "de manos, dedos y extremidades: no hay palabra que las coloque, se tira otra vez).\n"
    "PASO 3: termina con una unica linea que empiece por JSON: y contenga\n"
    '{"prompt":"<el prompt entero reescrito, en ingles>",'
    '"negative_prompt":"<el negativo entero, en ingles>",'
    '"cambiar_semilla":<true/false>,"cambios":"<en espanol, que has cambiado y por que>"}\n'
    "Reglas al reescribir:\n"
    "- Conserva la intencion y el asunto del prompt original. No lo reinventes: es su "
    "encargo, no el tuyo.\n"
    "- No quites lo que ya lleva el prompt, salvo que contradiga lo que pide la persona.\n"
    "- Di las cosas con palabras concretas, no con nombres de defectos. 'sin sombras duras' "
    "no hace nada; 'soft even studio lighting' si.\n"
    "- EL PROMPT NEGATIVO CASI NO FUNCIONA con este modelo, que va destilado a cfg 1. Se "
    "comprobo: pidiendo quitar un platano por el negativo, el platano seguia ahi. Asi que "
    "TODO lo que importe va en el prompt positivo y dicho en afirmativo: en vez de fiarlo "
    "a un negativo 'text', escribe 'a plain t-shirt with no writing on it'; en vez de "
    "'extra fingers', escribe 'hands with five clearly separated fingers'. Al negativo "
    "manda solo una copia de refuerzo, nunca lo unico.\n"
    "- Si lo que falla es anatomia, manos o extremidades, pon cambiar_semilla en true."
)

REGLAS_3D_USUARIO = (
    "\nLa imagen se va a convertir en un modelo 3D imprimible, asi que el prompt debe "
    "seguir pidiendo un objeto entero, centrado, sobre fondo liso y con luz pareja, y evitar "
    "partes finas, transparencias y formas ramificadas. No pierdas eso al corregir."
)

REGLAS_REF_USUARIO = (
    "\nLa imagen se genero con 2 imagenes de referencia. El objeto sale siempre de la "
    "referencia 1; la 2 solo presta atributos sin cuerpo (color, patron, material, estilo, "
    "fondo, expresion). Si lo que se pide es una pose, una accion o una escena, describela "
    "con palabras y NO menciones la segunda imagen."
)


def corregir_con_usuario(imagen, prompt, negativo, observaciones, informe=None,
                         referencias=0, para3d=True):
    """Reescribe el prompt con lo que el usuario dice que falla. Ve la imagen.

    El corrector automatico solo sabe de los defectos que tiene en su tabla. Este recibe lo
    que la persona ha visto, que es lo que el modelo no supo ver, y lo traduce a cambios de
    prompt y de negativo. Devuelve (prompt, negativo, cambios, cambiar_semilla, aviso).
    """
    observaciones = (observaciones or "").strip()
    if not observaciones:
        return prompt, negativo, "", False, "no habia nada que corregir"

    sistema = SISTEMA_USUARIO
    if para3d:
        sistema += REGLAS_3D_USUARIO
    if int(referencias or 0) >= 2:
        sistema += REGLAS_REF_USUARIO

    partes = [sistema, "", "PROMPT ACTUAL:", prompt or "(vacio)",
              "", "NEGATIVO ACTUAL:", (negativo or "(vacio)"),
              "", "LO QUE DICE QUIEN LA HA MIRADO:", observaciones]
    if informe and informe.get("defectos"):
        partes += ["", "Lo que ademas habia encontrado la revision automatica (secundario, "
                   "manda lo de arriba):", "; ".join(informe.get("detalle") or informe["defectos"])]

    texto, aviso = _preguntar(imagen, "\n".join(partes), tokens=1100, temperatura=0.4)
    if aviso:
        return prompt, negativo, "", False, aviso
    datos = _extraer_json(texto)
    nuevo = str(datos.get("prompt") or "").strip()
    if not nuevo:
        return prompt, negativo, "", False, "la IA no devolvio un prompt; se deja el de antes"
    return (nuevo,
            str(datos.get("negative_prompt") or negativo or "").strip(),
            str(datos.get("cambios") or "").strip(),
            bool(datos.get("cambiar_semilla")),
            "")


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
