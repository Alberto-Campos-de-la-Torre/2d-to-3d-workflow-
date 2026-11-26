"""Medidas de la malla que no se fian de la orientacion de las caras.

El volumen firmado (teorema de la divergencia) es exacto y barato, pero solo si la
superficie esta cerrada Y todas las caras miran hacia el mismo lado. Despues de
solidificar y decimar eso no se cumple siempre, y cuando falla no falla poco: en un dragon
de 80 mm daba 22,1 cm3 cuando el solido real son 105,3, casi cinco veces menos. De ese
numero salen el peso y el precio, asi que aqui se contrasta con una medida por voxeles, que
no depende de la orientacion, y si discrepan se usa la de voxeles.
"""
import numpy as np


def volumen_firmado(vertices, caras):
    """Exacto si la malla esta cerrada y bien orientada; engana si no lo esta."""
    a, b, c = vertices[caras[:, 0]], vertices[caras[:, 1]], vertices[caras[:, 2]]
    return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0))


def _puntos_de_la_superficie(vertices, caras, escala, tope=512):
    """Puntos que cubren cada triangulo con paso menor que un voxel.

    No basta con los vertices y los centros: un cubo son 12 triangulos enormes y quedaria
    una jaula agujereada por la que se escapa el relleno. Cada triangulo se subdivide segun
    su tamano, asi que los grandes cuestan muestras y los pequenos no.
    """
    a = vertices[caras[:, 0]]
    b = vertices[caras[:, 1]]
    c = vertices[caras[:, 2]]
    lado = np.maximum(np.linalg.norm(b - a, axis=1),
                      np.maximum(np.linalg.norm(c - b, axis=1),
                                 np.linalg.norm(a - c, axis=1)))
    # Paso y medio por voxel: con uno justo, un triangulo en diagonal deja huecos
    # por los que el relleno se escapa y el volumen sale casi cero.
    pasos = np.clip(np.ceil(lado * escala * 1.5).astype(np.int32), 1, tope)

    trozos = [vertices]
    for n in np.unique(pasos):
        elegidos = pasos == n
        eje = np.linspace(0.0, 1.0, n + 1)
        u, v = np.meshgrid(eje, eje, indexing="ij")
        dentro = (u + v) <= 1.0 + 1e-9
        u, v = u[dentro], v[dentro]
        w = 1.0 - u - v
        # Por bloques: con mallas de 700k caras, todo junto no cabe en memoria.
        indices = np.flatnonzero(elegidos)
        bloque = max(1, int(4e6 // max(len(u), 1)))
        for i in range(0, len(indices), bloque):
            corte = indices[i:i + bloque]
            puntos = (a[corte][:, None, :] * w[None, :, None]
                      + b[corte][:, None, :] * u[None, :, None]
                      + c[corte][:, None, :] * v[None, :, None])
            trozos.append(puntos.reshape(-1, 3))
    return np.concatenate(trozos)


def volumen_voxeles(vertices, caras, resolucion=160):
    """Rasteriza la superficie, rellena el interior y cuenta. Ignora la orientacion."""
    from scipy import ndimage

    minimo = vertices.min(axis=0)
    lado = float((vertices.max(axis=0) - minimo).max())
    if lado <= 0:
        return 0.0
    escala = (resolucion - 4) / lado

    puntos = _puntos_de_la_superficie(vertices, caras, escala, tope=resolucion * 3)
    indices = np.clip(((puntos - minimo) * escala + 2).astype(np.int32), 0, resolucion - 1)

    rejilla = np.zeros((resolucion,) * 3, dtype=bool)
    rejilla[indices[:, 0], indices[:, 1], indices[:, 2]] = True
    # Sin dilatar, dos muestras seguidas pueden caer en voxeles que solo se tocan por una
    # esquina: para el relleno eso es un agujero, se escapa y devuelve la cascara en vez
    # del solido (22 cm3 en vez de 105 en el dragon). Un voxel de dilatacion lo cierra.
    rejilla = ndimage.binary_dilation(rejilla, iterations=1)
    lleno = ndimage.binary_fill_holes(rejilla)
    # Se deshace la dilatacion, o el solido saldria una capa mas gordo de lo que es.
    # Medido contra cubo, esfera y cilindro: queda entre +2 % y +4 %, siempre por arriba,
    # que para calcular material es el lado seguro.
    solido = ndimage.binary_erosion(lleno, iterations=1)
    return max(float(solido.sum()) / (escala ** 3), 0.0)


def volumen(vertices, caras, resolucion=160):
    """Volumen del solido, en las unidades de los vertices. Devuelve (valor, metodo).

    Si el firmado se queda muy por debajo del de voxeles es que la superficie no esta
    bien orientada y su integral se cancela sola: entonces manda el de voxeles.
    """
    firmado = volumen_firmado(vertices, caras)
    try:
        por_voxeles = volumen_voxeles(vertices, caras, resolucion)
    except Exception:
        return firmado, "firmado"
    if por_voxeles <= 0 or firmado >= por_voxeles * 0.85:
        return firmado, "firmado"
    return por_voxeles, "voxeles"


def area(vertices, caras):
    a, b, c = vertices[caras[:, 0]], vertices[caras[:, 1]], vertices[caras[:, 2]]
    return float(np.linalg.norm(np.cross(b - a, c - a), axis=1).sum() / 2.0)
