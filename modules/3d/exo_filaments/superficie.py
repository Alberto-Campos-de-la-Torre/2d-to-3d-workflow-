"""Reconstruccion CPU de un volumen binario, sin cambiar el sistema de ejes."""
import numpy as np
from skimage.measure import marching_cubes


def reconstruir(solido, origen, escala):
    # Aire exterior garantiza cierre aun si el objeto toca el limite de la rejilla.
    campo = np.pad(solido, 1).astype(np.float32)
    vertices, caras, _, _ = marching_cubes(campo, level=0.5, method='lewiner',
                                         allow_degenerate=False, gradient_direction='descent')
    vertices = (vertices - 1) / escala + origen
    # descent devuelve winding hacia dentro: el volumen firmado debe ser positivo.
    a, b, c = vertices[caras[:, 0]], vertices[caras[:, 1]], vertices[caras[:, 2]]
    if np.einsum('ij,ij->i', a, np.cross(b, c)).sum() < 0:
        caras = caras[:, [0, 2, 1]]
    return vertices.astype(np.float32), caras.astype(np.int64)
