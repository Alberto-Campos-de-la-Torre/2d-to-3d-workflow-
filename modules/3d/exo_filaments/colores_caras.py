"""Reduce vertices a filamentos sin crear colores mezclados en las fronteras."""
import numpy as np
from .paleta import agrupar, leer_paleta


def paleta_por_cara(caras, color_vert, max_colores, texto_paleta):
    paleta = leer_paleta(texto_paleta)
    if paleta is not None and len(paleta) > max_colores:
        raise ValueError('La paleta tiene mas colores que las plazas configuradas')
    etiquetas, colores = agrupar(np.asarray(color_vert), paleta, max_colores,
                                 peso_luz=0.25, min_distancia=6.0, min_porcentaje=0)
    ternas = etiquetas[caras]
    # Mayoria de los tres vertices. Si son todos distintos, escoger uno real,
    # nunca el promedio RGB que inventaba un tono entre piel, ropa y sombras.
    resultado = np.where(ternas[:, 1] == ternas[:, 2], ternas[:, 1], ternas[:, 0])
    return resultado, colores
