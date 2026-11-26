"""Consulta el color sobre la superficie original, no sobre el volumen reparado."""
import numpy as np
import logging
from scipy.spatial import cKDTree


def transferir(destino, referencia, posiciones_voxel, colores_voxel, resolucion=None):
    # Las rejillas de reparacion y textura no coinciden. Proyectar primero al
    # original impide consultar colores interiores tras dilatar/suavizar.
    tree = cKDTree(referencia)
    distancias, indices = tree.query(destino, k=1, workers=2)
    # TRELLIS usa vertices duales desplazados hasta 1.5 celdas. El decoder
    # de textura comparte las subdivisiones y el orden de esos mismos voxeles.
    # Vecino espacial mas cercano NO equivale al voxel propietario del vertice.
    if resolucion is not None and len(referencia) == len(posiciones_voxel):
        valido = True
        for i in range(0, len(referencia), 200000):
            delta = referencia[i:i+200000] - posiciones_voxel[i:i+200000]
            if np.max(np.abs(delta)) > 1.501 / resolucion:
                valido = False
                break
        if valido:
            logging.info('Exo color: correspondencia dual TRELLIS validada por indice (%s vertices)', len(referencia))
            return np.clip(colores_voxel[indices, :3], 0, 1), distancias
    logging.info('Exo color: orden dual no validado; transferencia espacial de superficie')
    puntos = referencia[indices]
    del tree
    tree = cKDTree(posiciones_voxel)
    _, indices_color = tree.query(puntos, k=1, workers=2)
    return np.clip(colores_voxel[indices_color, :3], 0, 1), distancias
