"""Lo que separa un STL correcto de una impresion que sale bien.

La malla puede estar cerrada, con paredes de sobra y buen aspecto, y aun asi:
- no caber en la cama,
- estar llena de voladizos que obligan a soportes por todas partes,
- o apoyarse en tan poco que se cae a la mitad de la impresion.

Nada de eso lo ve el informe de medidas. Aqui se mide, con la pieza puesta como se va a
imprimir (Z hacia arriba), que es la unica orientacion en la que estas preguntas tienen
sentido.
"""
import numpy as np

# Regla de los 45 grados: una superficie que mira hacia abajo se sostiene sola mientras su
# inclinacion respecto a la vertical no pase de 45. Por debajo de eso hay que ponerle
# soportes, que dejan marca y hay que arrancar a mano.
ANGULO_VOLADIZO = 45.0
CAPA_APOYO_MM = 1.0     # lo que se considera "apoyado en la cama"


def poner_de_pie(vertices):
    """De Y arriba (como sale del generador) a Z arriba (como se imprime)."""
    return np.stack([vertices[:, 0], -vertices[:, 2], vertices[:, 1]], axis=1)


def _normales_y_areas(vertices, caras):
    a, b, c = vertices[caras[:, 0]], vertices[caras[:, 1]], vertices[caras[:, 2]]
    cruz = np.cross(b - a, c - a)
    areas = np.linalg.norm(cruz, axis=1) / 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        normales = cruz / np.where(areas[:, None] > 0, 2.0 * areas[:, None], 1.0)
    return normales, areas, (a + b + c) / 3.0


def medir_voladizos(vertices, caras, angulo=ANGULO_VOLADIZO, apoyo_mm=CAPA_APOYO_MM):
    """Fraccion de superficie que mira hacia abajo mas de la cuenta.

    No se cuenta lo que esta pegado a la cama: la cara de abajo de una pieza apoyada mira
    hacia abajo del todo y no necesita nada, se imprime contra el cristal.

    Las normales se calculan por el producto vectorial, asi que dependen del orden de los
    vertices, y ya se vio que tras solidificar y decimar ese orden no es de fiar. Por eso
    se mide el voladizo con el valor ABSOLUTO hacia abajo sobre las caras que estan en el
    contorno inferior de la pieza: lo que se busca es cuanta superficie "techo" hay.
    """
    normales, areas, centros = _normales_y_areas(vertices, caras)
    total = float(areas.sum()) or 1.0
    suelo = float(vertices[:, 2].min())

    # Cara que mira hacia abajo mas de lo que aguanta la regla de los 45 grados.
    limite = np.cos(np.radians(angulo))
    mira_abajo = normales[:, 2] < -limite
    sobre_la_cama = centros[:, 2] <= suelo + apoyo_mm
    problematicas = mira_abajo & ~sobre_la_cama

    return {
        "voladizo_pct": round(float(areas[problematicas].sum()) / total * 100, 1),
        "apoyada_pct": round(float(areas[mira_abajo & sobre_la_cama].sum()) / total * 100, 1),
        "area_total_mm2": round(total, 1),
    }


def medir_apoyo(vertices, caras, apoyo_mm=CAPA_APOYO_MM):
    """Cuanto toca la cama y donde: area de la huella y su contorno."""
    from scipy.spatial import ConvexHull, QhullError

    suelo = float(vertices[:, 2].min())
    tocan = vertices[vertices[:, 2] <= suelo + apoyo_mm][:, :2]
    if len(tocan) < 3:
        return {"huella_mm2": 0.0, "contorno": None}
    try:
        casco = ConvexHull(tocan)
    except (QhullError, ValueError):
        return {"huella_mm2": 0.0, "contorno": None}
    return {"huella_mm2": round(float(casco.volume), 1), "contorno": tocan[casco.vertices]}


def centro_de_masa(vertices, caras, resolucion=128):
    """Centro de masa del solido, por voxeles.

    Se usa el mismo relleno que para el volumen y por la misma razon: la superficie no
    esta bien orientada, asi que cualquier formula que dependa de las normales miente.
    """
    from scipy import ndimage

    from .geometria import _puntos_de_la_superficie

    minimo = vertices.min(axis=0)
    lado = float((vertices.max(axis=0) - minimo).max())
    if lado <= 0:
        return vertices.mean(axis=0)
    escala = (resolucion - 4) / lado

    puntos = _puntos_de_la_superficie(vertices, caras, escala, tope=resolucion * 3)
    indices = np.clip(((puntos - minimo) * escala + 2).astype(np.int32), 0, resolucion - 1)
    rejilla = np.zeros((resolucion,) * 3, dtype=bool)
    rejilla[indices[:, 0], indices[:, 1], indices[:, 2]] = True
    lleno = ndimage.binary_fill_holes(ndimage.binary_dilation(rejilla, iterations=1))
    ocupados = np.argwhere(lleno)
    if not len(ocupados):
        return vertices.mean(axis=0)
    return (ocupados.mean(axis=0) - 2) / escala + minimo


def _margen_dentro(punto, contorno):
    """Distancia del punto al borde del poligono. Negativa si esta fuera.

    Es lo que decide si la pieza se cae: el centro de masa tiene que caer dentro de la
    huella, y cuanto mas adentro, mas margen hay antes de que vuelque.
    """
    n = len(contorno)
    dentro = False
    distancia = np.inf
    for i in range(n):
        a, b = contorno[i], contorno[(i + 1) % n]
        # Cruce del rayo horizontal, para saber si esta dentro.
        if (a[1] > punto[1]) != (b[1] > punto[1]):
            corte = a[0] + (punto[1] - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
            if punto[0] < corte:
                dentro = not dentro
        # Distancia al segmento.
        ab = b - a
        largo = float(ab @ ab)
        t = 0.0 if largo == 0 else float(np.clip((punto - a) @ ab / largo, 0.0, 1.0))
        distancia = min(distancia, float(np.linalg.norm(punto - (a + t * ab))))
    return distancia if dentro else -distancia


def revisar(vertices, caras, cama=(350.0, 350.0, 350.0), angulo=ANGULO_VOLADIZO,
            apoyo_mm=CAPA_APOYO_MM, ya_de_pie=False):
    """Informe de imprimibilidad fisica. Espera milimetros."""
    v = vertices if ya_de_pie else poner_de_pie(vertices)
    medidas = v.max(axis=0) - v.min(axis=0)

    # La pieza se puede girar sobre la cama, asi que para saber si cabe basta con que el
    # lado largo de la base entre en el lado largo de la cama.
    base = sorted(medidas[:2])
    hueco = sorted(cama[:2])
    cabe = base[0] <= hueco[0] and base[1] <= hueco[1] and medidas[2] <= cama[2]
    holgura = min(hueco[0] / max(base[0], 1e-9), hueco[1] / max(base[1], 1e-9),
                  cama[2] / max(medidas[2], 1e-9))

    voladizos = medir_voladizos(v, caras, angulo, apoyo_mm)
    apoyo = medir_apoyo(v, caras, apoyo_mm)
    centro = centro_de_masa(v, caras)

    margen = None
    if apoyo["contorno"] is not None and len(apoyo["contorno"]) >= 3:
        margen = round(float(_margen_dentro(centro[:2], apoyo["contorno"])), 1)

    informe = {
        "medidas_mm": [round(float(x), 1) for x in medidas],
        "cama_mm": [float(x) for x in cama],
        "cabe": bool(cabe),
        "holgura": round(float(holgura), 2),
        "voladizo_pct": voladizos["voladizo_pct"],
        "apoyada_pct": voladizos["apoyada_pct"],
        "huella_mm2": apoyo["huella_mm2"],
        "huella_pct": round(apoyo["huella_mm2"] / max(medidas[0] * medidas[1], 1e-9) * 100, 1),
        "altura_centro_mm": round(float(centro[2] - v[:, 2].min()), 1),
        "margen_vuelco_mm": margen,
        "avisos": [],
    }

    if not cabe:
        informe["avisos"].append(
            "no cabe en la cama (%.0f x %.0f x %.0f mm): habria que bajarla a %.0f mm de alto"
            % (*cama, medidas[2] * holgura))
    if voladizos["voladizo_pct"] >= 15:
        informe["avisos"].append(
            "%.1f %% de la superficie son voladizos: van a hacer falta soportes en casi toda "
            "la pieza, y dejan marca" % voladizos["voladizo_pct"])
    elif voladizos["voladizo_pct"] >= 5:
        informe["avisos"].append(
            "%.1f %% de voladizos: hara falta algo de soporte" % voladizos["voladizo_pct"])
    if informe["huella_mm2"] < 100:
        informe["avisos"].append(
            "apoya en solo %.0f mm2: se despega o se cae; hace falta balsa o una peana mas ancha"
            % informe["huella_mm2"])
    if margen is not None and margen <= 0:
        informe["avisos"].append(
            "el centro de masa cae FUERA de la huella: la pieza vuelca sola")
    elif margen is not None and margen < 5:
        informe["avisos"].append(
            "el centro de masa queda a %.1f mm del borde de la huella: es inestable" % margen)

    informe["apto"] = not informe["avisos"]
    return informe


def resumen(informe):
    m = informe["medidas_mm"]
    lineas = [
        "medidas      %.1f x %.1f x %.1f mm (cama %.0f x %.0f x %.0f)"
        % (m[0], m[1], m[2], *informe["cama_mm"]),
        "cabe         %s" % ("si, sobra x%.1f" % informe["holgura"] if informe["cabe"] else "NO"),
        "voladizos    %.1f %% de la superficie (mas de 45 grados)" % informe["voladizo_pct"],
        "apoyo        %.0f mm2 de huella, %.0f %% de su sombra" % (informe["huella_mm2"],
                                                                  informe["huella_pct"]),
    ]
    if informe["margen_vuelco_mm"] is not None:
        lineas.append("estabilidad  centro de masa a %.1f mm del borde de la huella, "
                      "a %.1f mm de alto" % (informe["margen_vuelco_mm"],
                                             informe["altura_centro_mm"]))
    lineas.append("resultado    %s" % ("lista para imprimir" if informe["apto"]
                                       else "revisar antes de imprimir"))
    lineas += ["  - " + a for a in informe["avisos"]]
    return "\n".join(lineas)
