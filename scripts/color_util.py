"""Agrupacion de colores en filamentos y escritura de OBJ/MTL con color.

Lo usan colores_a_piezas.py (separar en piezas) y preparar_impresion.py (sacar el
modelo reparado con color). El agrupamiento es perceptual: si se hace en RGB crudo,
el reparto separa luces y sombras del mismo color en vez de colores distintos.
"""
import numpy as np


def rgb_a_lab(rgb):
    """sRGB 0..1 -> CIELab."""
    lineal = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], dtype=np.float32)
    xyz = lineal @ m.T / np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(np.clip(xyz, 0, None)), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1).astype(np.float32)


def lineal_a_srgb(valores):
    """glTF guarda COLOR_0 en espacio lineal; para comparar con bobinas hace falta sRGB."""
    return np.where(valores <= 0.0031308, valores * 12.92,
                    1.055 * np.power(np.clip(valores, 0, None), 1 / 2.4) - 0.055)


def hex_a_rgb(texto):
    texto = texto.strip().lstrip("#")
    return np.array([int(texto[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def kmeans(datos, k, iteraciones=40, semilla=0):
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
    return etiquetas, centros


def fusionar_grupos(etiquetas, centros, min_distancia, min_porcentaje):
    """Une grupos de color casi identico y reparte los residuales entre los que quedan."""
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
    """Devuelve (etiqueta por cara, color RGB de cada grupo)."""
    def a_espacio(rgb):
        lab = rgb_a_lab(rgb)
        lab[:, 0] *= peso_luz
        return lab

    espacio = a_espacio(colores)
    if paleta is not None and len(paleta):
        centros_rgb = np.asarray(paleta, dtype=np.float32)
        etiquetas = np.argmin(((espacio[:, None, :] - a_espacio(centros_rgb)[None, :, :]) ** 2).sum(axis=2), axis=1)
        return etiquetas, centros_rgb

    muestra = (np.arange(len(espacio)) if len(espacio) <= 200_000
               else np.random.default_rng(0).choice(len(espacio), 200_000, replace=False))
    _, centros = kmeans(espacio[muestra], n_colores)
    etiquetas = np.argmin(((espacio[:, None, :] - centros[None, :, :]) ** 2).sum(axis=2), axis=1)
    etiquetas, centros = fusionar_grupos(etiquetas, centros, min_distancia, min_porcentaje)
    centros_rgb = np.array([colores[etiquetas == i].mean(axis=0) for i in range(len(centros))], dtype=np.float32)
    return etiquetas, centros_rgb


def vecindad(triangulos):
    """Pares de caras que comparten arista."""
    aristas = np.sort(np.concatenate([triangulos[:, [0, 1]], triangulos[:, [1, 2]], triangulos[:, [2, 0]]]), axis=1)
    clave = aristas[:, 0].astype(np.int64) * (int(triangulos.max()) + 1) + aristas[:, 1]
    cara = np.tile(np.arange(len(triangulos), dtype=np.int64), 3)
    orden = np.argsort(clave, kind="stable")
    clave, cara = clave[orden], cara[orden]
    iguales = np.flatnonzero(clave[:-1] == clave[1:])
    return np.stack([cara[iguales], cara[iguales + 1]], axis=1)


def quitar_islas(triangulos, etiquetas, min_caras, vecinas=None):
    """Absorbe manchas de color pequenas en el color que las rodea.

    El filtro de mayoria solo borra caras sueltas; las manchas de decenas de caras
    (sombras de la foto original que se colaron como color) sobreviven. Aqui se buscan
    las regiones conexas de cada color y las que no llegan a 'min_caras' pasan al color
    dominante de su contorno: menos cambios de filamento y menos manchas en la pieza.
    """
    vecinas = vecindad(triangulos) if vecinas is None else vecinas
    mismo = vecinas[etiquetas[vecinas[:, 0]] == etiquetas[vecinas[:, 1]]]

    padre = np.arange(len(triangulos), dtype=np.int64)
    for _ in range(100):
        ra, rb = padre[mismo[:, 0]], padre[mismo[:, 1]]
        distintos = ra != rb
        if not distintos.any():
            break
        menor = np.minimum(ra, rb)[distintos]
        np.minimum.at(padre, ra[distintos], menor)
        np.minimum.at(padre, rb[distintos], menor)
        padre = padre[padre]

    regiones, inverso, tamanos = np.unique(padre, return_inverse=True, return_counts=True)
    pequenas = set(np.flatnonzero(tamanos < min_caras).tolist())
    if not pequenas:
        return etiquetas

    # Para cada region pequena, el color mas frecuente entre las caras que la tocan.
    etiquetas = etiquetas.copy()
    frontera = vecinas[etiquetas[vecinas[:, 0]] != etiquetas[vecinas[:, 1]]]
    for region in pequenas:
        caras = np.flatnonzero(inverso == region)
        if not len(caras):
            continue
        dentro = np.isin(frontera, caras)
        vecinos = np.where(dentro[:, 0], frontera[:, 1], frontera[:, 0])[dentro.any(axis=1)]
        if not len(vecinos):
            continue
        etiquetas[caras] = np.bincount(etiquetas[vecinos]).argmax()
    return etiquetas


def suavizar_etiquetas(triangulos, etiquetas, n_colores, pasos=2, apego=1.5, vecinas=None):
    """Filtro de mayoria sobre caras vecinas: alisa los bordes dentados entre colores."""
    vecinas = vecindad(triangulos) if vecinas is None else vecinas
    for _ in range(pasos):
        votos = np.zeros((len(triangulos), n_colores), dtype=np.float32)
        votos[np.arange(len(triangulos)), etiquetas] = apego
        np.add.at(votos, (vecinas[:, 0], etiquetas[vecinas[:, 1]]), 1.0)
        np.add.at(votos, (vecinas[:, 1], etiquetas[vecinas[:, 0]]), 1.0)
        nuevas = votos.argmax(axis=1).astype(etiquetas.dtype)
        if np.array_equal(nuevas, etiquetas):
            break
        etiquetas = nuevas
    return etiquetas


def color_por_vertice(triangulos, etiquetas, centros, n_verts):
    """Cada vertice toma el color del grupo que mas aparece entre sus caras."""
    votos = np.zeros((n_verts, len(centros)), dtype=np.int32)
    for columna in range(3):
        np.add.at(votos, (triangulos[:, columna], etiquetas), 1)
    return centros[votos.argmax(axis=1)]


def escribir_obj_color(destino, vertices, triangulos, etiquetas, centros, nombre="modelo"):
    """OBJ con color por vertice Y materiales MTL, con la estructura que esperan los laminadores.

    El orden importa: 'o' del objeto, luego por cada color 'g' y despues 'usemtl', y solo
    entonces sus caras. Con 'usemtl' antes de 'g' hay laminadores que pierden el material
    (Creality Print importaba el modelo en gris).
    """
    mtl = destino.with_suffix(".mtl")
    with open(mtl, "w", encoding="utf-8") as f:
        f.write("# Exo filaments - un material por filamento\n")
        for i, rgb in enumerate(centros):
            r, g, b = (float(c) for c in rgb)
            f.write(f"newmtl color_{i + 1}\n"
                    f"Ka {r:.4f} {g:.4f} {b:.4f}\n"
                    f"Kd {r:.4f} {g:.4f} {b:.4f}\n"
                    f"Ks 0.0000 0.0000 0.0000\n"
                    f"Ns 10.0\nd 1.0\nillum 2\n\n")

    color_vertice = color_por_vertice(triangulos, etiquetas, centros, len(vertices))
    with open(destino, "w", encoding="utf-8") as f:
        f.write(f"# Exo filaments - color por vertice + materiales\nmtllib {mtl.name}\no {nombre}\n")
        _volcar(f, np.hstack([vertices, color_vertice]), "v %.4f %.4f %.4f %.4f %.4f %.4f\n")
        f.write("s off\n")
        orden = np.argsort(etiquetas, kind="stable")
        for i in range(len(centros)):
            caras = triangulos[orden[etiquetas[orden] == i]]
            if not len(caras):
                continue
            f.write(f"g color_{i + 1}\nusemtl color_{i + 1}\n")
            _volcar(f, caras + 1, "f %d %d %d\n")
    return mtl


def _volcar(f, datos, formato, bloque=50_000):
    """Escribe filas con formato repetido. np.savetxt tarda minutos con mallas de 700k caras."""
    for inicio in range(0, len(datos), bloque):
        trozo = datos[inicio:inicio + bloque]
        f.write((formato * len(trozo)) % tuple(trozo.ravel().tolist()))
