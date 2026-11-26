"""Agrupacion de colores en filamentos, para los nodos de Exo filaments.

El agrupamiento es perceptual (CIELab con la luminosidad rebajada): en RGB crudo el
reparto separa luces y sombras del mismo color en vez de colores distintos, y una
manzana roja salia en tres rojos.
"""
import numpy as np


def lineal_a_srgb(valores):
    """glTF y ComfyUI guardan el color por vertice en espacio lineal."""
    return np.where(valores <= 0.0031308, valores * 12.92,
                    1.055 * np.power(np.clip(valores, 0, None), 1 / 2.4) - 0.055)


def srgb_a_lineal(valores):
    return np.where(valores <= 0.04045, valores / 12.92, ((valores + 0.055) / 1.055) ** 2.4)


def rgb_a_lab(rgb):
    lineal = srgb_a_lineal(rgb)
    m = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]], dtype=np.float32)
    xyz = lineal @ m.T / np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(np.clip(xyz, 0, None)), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16,
                     500 * (f[:, 0] - f[:, 1]),
                     200 * (f[:, 1] - f[:, 2])], axis=1).astype(np.float32)


def hex_a_rgb(texto):
    texto = texto.strip().lstrip("#")
    return np.array([int(texto[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def rgb_a_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(float(c) * 255)) for c in np.clip(rgb, 0, 1))


def leer_paleta(texto):
    """'#c41e3a, #ffd500' -> array Nx3. Devuelve None si el texto esta vacio."""
    colores = [hex_a_rgb(c) for c in texto.replace(";", ",").split(",") if c.strip()]
    return np.array(colores, dtype=np.float32) if colores else None


def _kmeans(datos, k, iteraciones=40, semilla=0):
    rng = np.random.default_rng(semilla)
    centros = [datos[rng.integers(len(datos))]]
    for _ in range(k - 1):
        dist = np.min([np.sum((datos - c) ** 2, axis=1) for c in centros], axis=0)
        total = dist.sum()
        centros.append(datos[rng.choice(len(datos), p=dist / total) if total > 0 else rng.integers(len(datos))])
    centros = np.array(centros, dtype=np.float32)
    for _ in range(iteraciones):
        etiquetas = np.argmin(((datos[:, None, :] - centros[None, :, :]) ** 2).sum(axis=2), axis=1)
        nuevos = np.array([datos[etiquetas == i].mean(axis=0) if np.any(etiquetas == i) else centros[i]
                           for i in range(k)], dtype=np.float32)
        if np.allclose(nuevos, centros):
            break
        centros = nuevos
    return centros


def _fusionar(etiquetas, centros, min_distancia, min_porcentaje):
    """Une grupos de color casi identico y reparte los residuales."""
    total = len(etiquetas)
    vivos = list(range(len(centros)))
    while True:
        cuentas = {i: int(np.count_nonzero(etiquetas == i)) for i in vivos}
        fusion = None
        for pos, i in enumerate(vivos):
            for j in vivos[pos + 1:]:
                if np.linalg.norm(centros[i] - centros[j]) < min_distancia:
                    fusion = (i, j) if cuentas[i] >= cuentas[j] else (j, i)
                    break
            if fusion:
                break
        if not fusion:
            pequenos = [i for i in vivos if 100 * cuentas[i] / total < min_porcentaje]
            if not pequenos or len(vivos) <= 2:
                break
            menor = min(pequenos, key=lambda i: cuentas[i])
            otros = [i for i in vivos if i != menor]
            destino = min(otros, key=lambda i: np.linalg.norm(centros[i] - centros[menor]))
            fusion = (destino, menor)
        destino, absorbido = fusion
        etiquetas[etiquetas == absorbido] = destino
        vivos.remove(absorbido)
    renumerado = np.zeros_like(etiquetas)
    for nuevo, viejo in enumerate(vivos):
        renumerado[etiquetas == viejo] = nuevo
    return renumerado, centros[vivos]


def agrupar(colores, paleta=None, n_colores=4, peso_luz=0.25, min_distancia=14.0, min_porcentaje=2.0):
    """Devuelve (etiqueta por elemento, color RGB de cada grupo)."""
    def a_espacio(rgb):
        lab = rgb_a_lab(rgb)
        lab[:, 0] *= peso_luz
        return lab

    espacio = a_espacio(colores)
    if paleta is not None and len(paleta):
        etiquetas = np.argmin(((espacio[:, None, :] - a_espacio(paleta)[None, :, :]) ** 2).sum(axis=2), axis=1)
        return etiquetas.astype(np.int32), np.asarray(paleta, dtype=np.float32)

    muestra = (np.arange(len(espacio)) if len(espacio) <= 200_000
               else np.random.default_rng(0).choice(len(espacio), 200_000, replace=False))
    centros = _kmeans(espacio[muestra], min(n_colores, len(espacio)))
    etiquetas = np.argmin(((espacio[:, None, :] - centros[None, :, :]) ** 2).sum(axis=2), axis=1).astype(np.int32)
    etiquetas, centros = _fusionar(etiquetas, centros, min_distancia, min_porcentaje)
    centros_rgb = np.array([colores[etiquetas == i].mean(axis=0) for i in range(len(centros))], dtype=np.float32)
    return etiquetas, centros_rgb


def vecindad(caras):
    """Pares de caras que comparten arista."""
    aristas = np.sort(np.concatenate([caras[:, [0, 1]], caras[:, [1, 2]], caras[:, [2, 0]]]), axis=1)
    clave = aristas[:, 0].astype(np.int64) * (int(caras.max()) + 1) + aristas[:, 1]
    cara = np.tile(np.arange(len(caras), dtype=np.int64), 3)
    orden = np.argsort(clave, kind="stable")
    clave, cara = clave[orden], cara[orden]
    iguales = np.flatnonzero(clave[:-1] == clave[1:])
    return np.stack([cara[iguales], cara[iguales + 1]], axis=1)


def quitar_islas(caras, etiquetas, min_caras, vecinas=None):
    """Absorbe manchas pequenas en el color que las rodea.

    Son sombras de la foto original coladas como color: en el cubo de Rubik dejaban
    manchas negras en mitad de las caras azules.
    """
    vecinas = vecindad(caras) if vecinas is None else vecinas
    mismo = vecinas[etiquetas[vecinas[:, 0]] == etiquetas[vecinas[:, 1]]]
    padre = np.arange(len(caras), dtype=np.int64)
    for _ in range(100):
        ra, rb = padre[mismo[:, 0]], padre[mismo[:, 1]]
        distintos = ra != rb
        if not distintos.any():
            break
        menor = np.minimum(ra, rb)[distintos]
        np.minimum.at(padre, ra[distintos], menor)
        np.minimum.at(padre, rb[distintos], menor)
        padre = padre[padre]

    _regiones, inverso, tamanos = np.unique(padre, return_inverse=True, return_counts=True)
    pequenas = np.flatnonzero(tamanos < min_caras)
    if not len(pequenas):
        return etiquetas
    etiquetas = etiquetas.copy()
    frontera = vecinas[etiquetas[vecinas[:, 0]] != etiquetas[vecinas[:, 1]]]
    for region in pequenas.tolist():
        indices = np.flatnonzero(inverso == region)
        if not len(indices):
            continue
        dentro = np.isin(frontera, indices)
        vecinos = np.where(dentro[:, 0], frontera[:, 1], frontera[:, 0])[dentro.any(axis=1)]
        if not len(vecinos):
            continue
        etiquetas[indices] = np.bincount(etiquetas[vecinos]).argmax()
    return etiquetas


def suavizar(caras, etiquetas, n_colores, pasos=2, apego=1.5, vecinas=None):
    """Filtro de mayoria sobre caras vecinas: alisa los bordes dentados entre colores."""
    vecinas = vecindad(caras) if vecinas is None else vecinas
    for _ in range(pasos):
        votos = np.zeros((len(caras), n_colores), dtype=np.float32)
        votos[np.arange(len(caras)), etiquetas] = apego
        np.add.at(votos, (vecinas[:, 0], etiquetas[vecinas[:, 1]]), 1.0)
        np.add.at(votos, (vecinas[:, 1], etiquetas[vecinas[:, 0]]), 1.0)
        nuevas = votos.argmax(axis=1).astype(etiquetas.dtype)
        if np.array_equal(nuevas, etiquetas):
            break
        etiquetas = nuevas
    return etiquetas


def color_por_vertice(caras, etiquetas, centros, n_verts):
    """Cada vertice toma el color del grupo que mas aparece entre sus caras."""
    votos = np.zeros((n_verts, len(centros)), dtype=np.int32)
    for columna in range(3):
        np.add.at(votos, (caras[:, columna], etiquetas), 1)
    return centros[votos.argmax(axis=1)]
