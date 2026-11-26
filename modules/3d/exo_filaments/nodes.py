"""Nodos de Exo filaments: pasar de una malla generada a una pieza imprimible.

- Paleta de filamentos: reduce el color del modelo a los filamentos que hay cargados.
- Informe de impresion: escala a milimetros y calcula volumen, peso y estanqueidad.
- Guardar para imprimir: escribe STL y OBJ+MTL en la carpeta de salida de ComfyUI.
"""
import json
import os
import struct

import numpy as np
from manifold3d import Manifold, Mesh as MeshManifold
import torch
from typing_extensions import override

import folder_paths
from comfy_api.latest import ComfyExtension, IO

from .paleta import (agrupar, color_por_vertice, leer_paleta, lineal_a_srgb, quitar_islas,
                     rgb_a_hex, srgb_a_lineal, suavizar, vecindad)

DENSIDAD = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "TPU": 1.21, "ASA": 1.07}


def _primera_malla(mesh):
    """ComfyUI trabaja con lotes (B, N, 3); aqui se usa el primer elemento."""
    vertices = mesh.vertices[0].detach().cpu().numpy().astype(np.float64)
    caras = mesh.faces[0].detach().cpu().numpy().astype(np.int64)
    if mesh.vertex_counts is not None:
        vertices = vertices[:int(mesh.vertex_counts[0])]
        caras = caras[:int(mesh.face_counts[0])]
    return vertices, caras


def _colores_srgb(mesh, n_verts):
    if mesh.vertex_colors is None:
        return None
    colores = mesh.vertex_colors[0].detach().cpu().numpy()[:n_verts, :3].astype(np.float32)
    return np.clip(lineal_a_srgb(colores), 0, 1)


def _clasificar_aristas(vertices, caras):
    """Devuelve (agujeros, no_manifold).

    - agujeros: aristas con una sola cara. Son huecos reales y el laminador rellena mal.
    - no_manifold: aristas con tres o mas caras. Feo, pero los laminadores lo resuelven.

    Se sueldan antes los vertices por posicion, con tolerancia relativa al tamano: los
    STL repiten cada vertice en cada cara y sin soldar todo saldria como agujero.
    """
    diagonal = float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0))) or 1.0
    clave_v = np.round(vertices / (diagonal * 1e-6)).astype(np.int64)
    _, soldado = np.unique(clave_v, axis=0, return_inverse=True)
    caras = soldado[caras]
    aristas = np.sort(np.concatenate([caras[:, [0, 1]], caras[:, [1, 2]], caras[:, [2, 0]]]), axis=1)
    clave = aristas[:, 0].astype(np.int64) * (int(caras.max()) + 1) + aristas[:, 1]
    _, cuentas = np.unique(clave, return_counts=True)
    return int(np.count_nonzero(cuentas == 1)), int(np.count_nonzero(cuentas > 2))


def _aristas_abiertas(vertices, caras):
    """Solo los agujeros: es lo que impide imprimir."""
    return _clasificar_aristas(vertices, caras)[0]


def _volumen_area(vertices, caras):
    """Volumen y area. El volumen no se fia de como esten orientadas las caras.

    El firmado se cancela solo cuando parte de la superficie mira del reves, y eso pasa
    tras solidificar y decimar: en un dragon de 80 mm daba 22,1 cm3 contra los 105,3 reales.
    De ese numero sale el peso que se cobra, asi que se contrasta con una medida por
    voxeles (ver geometria.py y scripts/pruebas/probar_volumen.py).
    """
    from .geometria import area, volumen

    valor, metodo = volumen(vertices, caras)
    return float(valor), float(area(vertices, caras)), metodo


class ExoPaletaFilamentos(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoPaletaFilamentos",
            display_name="Paleta de filamentos (Exo)",
            category="3d/exo filaments",
            description=(
                "Reduce el color del modelo a unos pocos filamentos, listos para el AMS o el CFS. "
                "Agrupa en espacio perceptual con la luminosidad rebajada, para separar colores y no "
                "luces y sombras del mismo color. Con 'paleta' vacia elige los colores solo."
            ),
            inputs=[
                IO.Mesh.Input("mesh"),
                IO.String.Input("paleta", default="", multiline=False,
                                tooltip="Colores reales de tus bobinas: '#1a1a1a,#f2f2f2,#ffd500'. Vacio = los elige el nodo."),
                IO.Int.Input("colores", default=4, min=2, max=8,
                             tooltip="Maximo de filamentos cuando la paleta esta vacia. Los grupos casi iguales se funden."),
                IO.Float.Input("peso_luz", default=0.25, min=0.0, max=1.0, step=0.05,
                               tooltip="Cuanto pesa el brillo al agrupar. 0 = solo color; 1 = separa tambien por sombra."),
                IO.Float.Input("min_mancha", default=0.3, min=0.0, max=10.0, step=0.1,
                               tooltip="Absorbe manchas que ocupen menos de este %% de las caras. 0 = no tocar."),
                IO.Int.Input("suavizar_bordes", default=3, min=0, max=10,
                             tooltip="Pasadas del filtro de mayoria para alisar los limites entre colores."),
            ],
            outputs=[
                IO.Mesh.Output("mesh", tooltip="La misma malla con el color reducido a la paleta."),
                IO.String.Output("informe", tooltip="Hex y porcentaje de superficie de cada filamento."),
            ],
            is_output_node=True,  # para ver el reparto de filamentos en el propio nodo
        )

    @classmethod
    def execute(cls, mesh, paleta, colores, peso_luz, min_mancha, suavizar_bordes):
        vertices, caras = _primera_malla(mesh)
        color_vert = _colores_srgb(mesh, len(vertices))
        if color_vert is None:
            raise ValueError("La malla no trae color por vertice. Conectala despues de 'Paint Mesh'.")

        color_cara = color_vert[caras].mean(axis=1)
        etiquetas, centros = agrupar(color_cara, leer_paleta(paleta), colores, peso_luz)

        if min_mancha > 0 or suavizar_bordes > 0:
            vecinas = vecindad(caras)
            if min_mancha > 0:
                etiquetas = quitar_islas(caras, etiquetas, max(1, int(len(caras) * min_mancha / 100.0)), vecinas)
            if suavizar_bordes > 0:
                etiquetas = suavizar(caras, etiquetas, len(centros), suavizar_bordes, vecinas=vecinas)

        nuevos = color_por_vertice(caras, etiquetas, centros, len(vertices))
        salida = mesh.clone() if hasattr(mesh, "clone") else __import__("copy").deepcopy(mesh)
        lineal = torch.from_numpy(srgb_a_lineal(nuevos).astype(np.float32))
        relleno = mesh.vertex_colors[0].detach().cpu().clone()
        relleno[:len(vertices), :3] = lineal
        salida.vertex_colors = relleno.unsqueeze(0).to(mesh.vertex_colors.device)

        lineas = ["filamento  color     superficie"]
        for i, centro in enumerate(centros):
            porcentaje = 100.0 * float(np.count_nonzero(etiquetas == i)) / len(caras)
            if porcentaje <= 0:
                continue
            lineas.append(f"{i + 1:>9}  {rgb_a_hex(centro)}  {porcentaje:8.1f} %")
        informe = "\n".join(lineas)
        return IO.NodeOutput(salida, informe, ui={"text": (informe,)})


class ExoInformeImpresion(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoInformeImpresion",
            display_name="Informe de impresion (Exo)",
            category="3d/exo filaments",
            description=(
                "Escala la malla a milimetros y calcula lo que hace falta para presupuestar: "
                "medidas, volumen, peso estimado con el relleno indicado y si la malla esta cerrada."
            ),
            inputs=[
                IO.Mesh.Input("mesh"),
                IO.Float.Input("altura_mm", default=80.0, min=5.0, max=500.0, step=1.0,
                               tooltip="Altura final de la pieza; se aplica al eje mas largo."),
                IO.Combo.Input("material", options=list(DENSIDAD), default="PLA"),
                IO.Float.Input("relleno", default=15.0, min=0.0, max=100.0, step=5.0,
                               tooltip="Relleno en %% para estimar el peso."),
                IO.Float.Input("pared_mm", default=1.2, min=0.4, max=5.0, step=0.2,
                               tooltip="Grosor de pared del laminador, para estimar el material de la cascara."),
            ],
            outputs=[
                IO.Mesh.Output("mesh", tooltip="La malla escalada a milimetros."),
                IO.String.Output("informe"),
                IO.Float.Output("peso_g"),
            ],
            is_output_node=True,  # el informe se lee en el propio nodo
        )

    @classmethod
    def execute(cls, mesh, altura_mm, material, relleno, pared_mm):
        vertices, caras = _primera_malla(mesh)
        medidas = vertices.max(axis=0) - vertices.min(axis=0)
        factor = altura_mm / float(medidas.max())
        centrado = (vertices - (vertices.max(axis=0) + vertices.min(axis=0)) / 2.0) * factor

        volumen_mm3, area_mm2, metodo_volumen = _volumen_area(centrado, caras)
        volumen_cm3, area_cm2 = volumen_mm3 / 1000.0, area_mm2 / 100.0
        aviso_volumen = ("  (medido por voxeles: la malla no esta bien orientada)"
                         if metodo_volumen == "voxeles" else "")
        volumen_pared = min(area_cm2 * pared_mm / 10.0, volumen_cm3)
        material_cm3 = volumen_pared + max(volumen_cm3 - volumen_pared, 0.0) * relleno / 100.0
        peso = material_cm3 * DENSIDAD[material]
        abiertas = _aristas_abiertas(centrado, caras)
        # Con la malla abierta el volumen no significa nada (un cubo de 6 cm daba 0,2 cm3),
        # asi que no se devuelve un peso que parezca un presupuesto.
        fiable = abiertas == 0

        salida = mesh.clone() if hasattr(mesh, "clone") else __import__("copy").deepcopy(mesh)
        nuevas = mesh.vertices[0].detach().cpu().clone()
        nuevas[:len(centrado)] = torch.from_numpy(centrado.astype(np.float32))
        salida.vertices = nuevas.unsqueeze(0).to(mesh.vertices.device)

        lineas = [
            f"medidas     {medidas[0] * factor:.1f} x {medidas[1] * factor:.1f} x {medidas[2] * factor:.1f} mm",
            f"superficie  {area_cm2:.1f} cm2",
            f"caras       {len(caras):,}",
            f"malla       {'cerrada' if fiable else f'ABIERTA: {abiertas} aristas sueltas'}",
        ]
        if fiable:
            lineas += [
                f"volumen     {volumen_cm3:.1f} cm3{aviso_volumen}",
                f"material    {material} al {relleno:.0f} % de relleno",
                f"peso aprox  {peso:.1f} g",
            ]
        else:
            lineas += [
                "volumen     no se puede calcular con la malla abierta",
                "peso        sin dato: repara la malla antes de presupuestar",
                "            (Remesh Mesh en modo sdf + Decimate Mesh antes de este nodo)",
            ]
        informe = "\n".join(lineas)
        return IO.NodeOutput(salida, informe, float(peso) if fiable else 0.0, ui={"text": (informe,)})


def _a_pil(imagen):
    """IMAGE de ComfyUI (B,H,W,C en 0..1) -> PIL, primera del lote."""
    from PIL import Image

    datos = imagen[0].detach().cpu().numpy()
    return Image.fromarray(np.clip(datos * 255, 0, 255).astype(np.uint8))




class ExoRevisarPieza(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoRevisarPieza",
            display_name="Revisar pieza terminada (Exo)",
            category="3d/exo filaments",
            description=(
                "Renderiza la pieza desde cuatro angulos y se la ensena a tu IA local: si se parece "
                "a lo pedido, si le faltan partes, si esta deformada o si no se sostiene. Ademas mide "
                "que fraccion de su caja ocupa, que es como se detectan las cascaras huecas: eso no "
                "se ve en un render pero se imprime como un papel."
            ),
            inputs=[
                IO.Mesh.Input("mesh"),
                IO.String.Input("descripcion", multiline=False, default="",
                                tooltip="Lo que se pidio, para comparar. Vacio = solo busca defectos."),
                IO.Image.Input("imagen_referencia", optional=True),
                IO.Int.Input("resolucion_vista", default=448, min=256, max=1024, step=64,
                             tooltip="Lado de cada una de las cuatro vistas."),
            ],
            outputs=[
                IO.Image.Output("vistas"),
                IO.String.Output("informe"),
                IO.Boolean.Output("apto"),
                IO.Float.Output("puntuacion"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, mesh, descripcion, resolucion_vista, imagen_referencia=None):
        from .revision_pieza import a_imagen_comfy, resumen, revisar_pieza

        referencia = None
        if imagen_referencia is not None:
            from PIL import Image
            referencia=Image.fromarray(np.clip(imagen_referencia[0].detach().cpu().numpy()*255,0,255).astype(np.uint8))
        informe, hoja = revisar_pieza(mesh, descripcion, resolucion_vista, referencia)
        return IO.NodeOutput(a_imagen_comfy(hoja), json.dumps(informe, ensure_ascii=False),
                             bool(informe.get("apto")), float(informe.get("puntuacion") or 0.0),
                             ui={"text": (resumen(informe),), "revision_pieza": [informe]})






def _rasterizar(vertices, caras, resolucion):
    """Marca en una rejilla los voxeles que toca la superficie.

    Se siembran puntos sobre cada triangulo, suficientes para que no queden huecos entre
    muestras (aprox. dos por arista de voxel), y se marcan sus voxeles.
    """
    minimo, maximo = vertices.min(axis=0), vertices.max(axis=0)
    lado = float((maximo - minimo).max()) or 1.0
    # Tres voxeles de aire alrededor: si la pieza toca el borde de la rejilla, la
    # reconstruccion deja la malla abierta justo ahi.
    margen = lado * 3.0 / resolucion
    escala = (resolucion - 1) / (lado + 2 * margen)
    origen = minimo - margen

    a = (vertices[caras[:, 0]] - origen) * escala
    b = (vertices[caras[:, 1]] - origen) * escala
    c = (vertices[caras[:, 2]] - origen) * escala

    lados = np.maximum.reduce([np.linalg.norm(b - a, axis=1),
                               np.linalg.norm(c - b, axis=1),
                               np.linalg.norm(a - c, axis=1)])
    muestras = np.clip(np.ceil(lados * 2).astype(np.int64), 1, 64)

    rejilla = np.zeros((resolucion, resolucion, resolucion), dtype=bool)
    rng = np.random.default_rng(0)
    # Por bloques de triangulos con el mismo numero de muestras, para no salirse de memoria.
    for cantidad in np.unique(muestras):
        grupo = muestras == cantidad
        n = int(grupo.sum()) * int(cantidad)
        u = rng.random(n, dtype=np.float32)
        v = rng.random(n, dtype=np.float32)
        fuera = u + v > 1.0
        u[fuera], v[fuera] = 1.0 - u[fuera], 1.0 - v[fuera]
        ga = np.repeat(a[grupo], cantidad, axis=0)
        gb = np.repeat(b[grupo], cantidad, axis=0)
        gc = np.repeat(c[grupo], cantidad, axis=0)
        puntos = ga + (gb - ga) * u[:, None] + (gc - ga) * v[:, None]
        # Los vertices tambien, para que las esquinas no se escapen.
        puntos = np.concatenate([puntos, a[grupo], b[grupo], c[grupo]])
        idx = np.clip(np.rint(puntos).astype(np.int32), 0, resolucion - 1)
        rejilla[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return rejilla, origen, escala


def _soldar(vertices, caras, tolerancia_rel=1e-6):
    """Une los vertices que ocupan la misma posicion.

    El reconstructor de voxeles saca cada cara con sus propios vertices: sin soldar, la
    malla parece abierta y el suavizado separa las copias en vez de mover una esquina.
    La tolerancia es relativa al tamano de la pieza: con una fija, un modelo pequeno
    fusiona vertices que no se tocan y aparecen agujeros donde no los hay.
    """
    diagonal = float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0))) or 1.0
    clave = np.round(vertices / (diagonal * tolerancia_rel)).astype(np.int64)
    _, primeros, indice = np.unique(clave, axis=0, return_index=True, return_inverse=True)
    caras = indice[caras]
    validas = (caras[:, 0] != caras[:, 1]) & (caras[:, 1] != caras[:, 2]) & (caras[:, 0] != caras[:, 2])
    return vertices[primeros].astype(np.float32), caras[validas]


def _suavizar_forma(vertices, caras, pasos):
    """Suavizado laplaciano: cada vertice se acerca a la media de sus vecinos.

    Quita el escalonado que deja la rejilla sin tocar la topologia, asi que la malla
    sigue igual de cerrada. Con muchas pasadas se pierden las aristas vivas.
    """
    if pasos <= 0:
        return vertices
    aristas = np.concatenate([caras[:, [0, 1]], caras[:, [1, 2]], caras[:, [2, 0]]])
    aristas = np.concatenate([aristas, aristas[:, ::-1]])
    grado = np.bincount(aristas[:, 0], minlength=len(vertices)).astype(np.float32)
    grado[grado == 0] = 1.0
    for _ in range(int(pasos)):
        suma = np.zeros_like(vertices)
        np.add.at(suma, aristas[:, 0], vertices[aristas[:, 1]])
        vertices = 0.5 * vertices + 0.5 * (suma / grado[:, None])
    return vertices


class ExoSolidificar(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoSolidificar",
            display_name="Solidificar malla (Exo)",
            category="3d/exo filaments",
            description=(
                "Convierte la superficie en un solido cerrado, que es lo que necesita el laminador. "
                "Lleva la malla a una rejilla, cierra las grietas, rellena el interior y reconstruye "
                "la superficie. Es lo que 'Remesh Mesh' NO hace: aquel trabaja solo en una banda "
                "alrededor de la superficie y deja la malla igual de abierta o peor."
            ),
            inputs=[
                IO.Mesh.Input("mesh"),
                IO.Int.Input("resolucion", default=384, min=64, max=768, step=32,
                             tooltip="Voxeles por lado. El escalon de la rejilla mide altura_mm / resolucion: con 320 "
                                     "una pieza de 80 mm tiene muestreo de 0,25 mm. La superficie se interpola; mas resolucion conserva mas detalle."),
                IO.Int.Input("cerrar_grietas", default=1, min=0, max=4,
                             tooltip="Cuantos voxeles se engordan antes de rellenar, para tapar agujeros. Sube a 2 si la malla viene muy rota."),
                IO.Int.Input("suavizar_forma", default=5, min=0, max=12,
                             tooltip="Pasadas de suavizado para quitar el escalonado de la rejilla. Es lo que mas se "
                                     "nota: suavizar no recupera detalles perdidos por la rejilla. Baja a 2 en piezas "
                                     "con aristas vivas (cubos, cajas), que se redondean."),
            ],
            outputs=[
                IO.Mesh.Output("mesh"),
                IO.String.Output("informe"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, mesh, resolucion, cerrar_grietas, suavizar_forma):
        from scipy import ndimage

        vertices, caras = _primera_malla(mesh)
        abiertas_antes = _aristas_abiertas(vertices, caras)

        rejilla, origen, escala = _rasterizar(vertices, caras, resolucion)
        ocupados = int(rejilla.sum())

        # Se engorda la superficie hasta que el relleno encuentre interior de verdad: si
        # la malla tiene una grieta, el relleno se escapa y devuelve una cascara hueca.
        # El cubo de Rubik necesitaba 4 voxeles; la camara, 1.
        solido, usados, interior = rejilla, 0, 0
        for intento in range(int(cerrar_grietas), 7):
            # Se rodea la rejilla de aire antes de engordar: si la pieza llega al borde,
            # el relleno se escapa por ahi y devuelve la cascara hueca.
            hueco = intento + 1
            engordada = np.pad(rejilla, hueco)
            if intento:
                engordada = ndimage.binary_dilation(engordada, iterations=intento)
            lleno = ndimage.binary_fill_holes(engordada)
            ganado = int(lleno.sum()) - int(engordada.sum())
            if ganado > max(ocupados * 0.2, 1000) or intento == 6:
                if intento:
                    lleno = ndimage.binary_erosion(lleno, iterations=intento, border_value=0)
                recorte = slice(hueco, -hueco)
                solido, usados, interior = lleno[recorte, recorte, recorte], intento, ganado
                break

        # Sin burbujas internas y sin motas sueltas: cada hueco o mota anadiria superficie
        # (y aristas abiertas) dentro de la pieza.
        solido = ndimage.binary_fill_holes(solido)
        etiquetas, cuantos = ndimage.label(solido)
        if cuantos > 1:
            tamanos = ndimage.sum(solido, etiquetas, range(1, cuantos + 1))
            solido = etiquetas == (int(np.argmax(tamanos)) + 1)
        if not solido.any():   # nada cerro: se sigue con la cascara, y el informe lo dice
            solido, interior = rejilla, 0

        from .superficie import reconstruir
        vertices_salida, nuevas_caras = reconstruir(solido, origen, escala)
        vertices_salida = _suavizar_forma(vertices_salida, nuevas_caras, suavizar_forma)

        salida = mesh.clone() if hasattr(mesh, "clone") else __import__("copy").deepcopy(mesh)
        salida.vertices = torch.from_numpy(vertices_salida).unsqueeze(0)
        salida.faces = torch.from_numpy(nuevas_caras).unsqueeze(0)
        salida.vertex_colors = None   # el color se vuelve a poner con 'Paint Mesh' o la paleta
        salida.uvs = None
        salida.normals = None
        salida.vertex_counts = None
        salida.face_counts = None

        agujeros, no_manifold = _clasificar_aristas(vertices_salida, nuevas_caras)
        informe = (
            f"entrada    {len(caras):,} caras Â· {abiertas_antes:,} agujeros\n"
            f"rejilla    {resolucion}^3 Â· {ocupados:,} voxeles de superficie\n"
            f"relleno    grietas cerradas con {usados} voxel(es) Â· interior {interior:,} voxeles\n"
            f"salida     {len(nuevas_caras):,} caras Â· {agujeros:,} agujeros Â· {no_manifold:,} aristas no-manifold\n"
            f"resultado  {'solido cerrado' if agujeros == 0 else 'SIGUE ABIERTA: sube cerrar_grietas'}"
        )
        return IO.NodeOutput(salida, informe, ui={"text": (informe,)})


class ExoRevisarGrosor(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoRevisarGrosor",
            display_name="Revisar grosor de pared (Exo)",
            category="3d/exo filaments",
            description=(
                "Busca las zonas demasiado finas para imprimir. Desde el centro de cada cara lanza "
                "un rayo hacia dentro: si choca con la pared opuesta antes del grosor minimo, esa "
                "zona saldria como un papel. Ponlo DESPUES de escalar a milimetros."
            ),
            inputs=[
                IO.Mesh.Input("mesh"),
                IO.Float.Input("grosor_min_mm", default=1.2, min=0.2, max=10.0, step=0.1,
                               tooltip="Por debajo de esto la pieza queda fragil. Dos perimetros de boquilla de 0,4 = 0,8 mm."),
                IO.Float.Input("aviso_pct", default=5.0, min=0.0, max=100.0, step=1.0,
                               tooltip="A partir de este %% de superficie fina, el informe lo marca como problema."),
                IO.Int.Input("muestras", default=4000, min=200, max=50_000, step=200,
                             tooltip="Caras a comprobar. Mas muestras, mas precision y mas tiempo."),
            ],
            outputs=[
                IO.Mesh.Output("mesh"),
                IO.String.Output("informe"),
                IO.Float.Output("pct_zonas_finas"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, mesh, grosor_min_mm, aviso_pct, muestras):
        from comfy_extras.nodes_mesh_postprocess import _any_hit_rays_bvh, _build_triangle_bvh

        vertices, caras = _primera_malla(mesh)
        a, b, c = vertices[caras[:, 0]], vertices[caras[:, 1]], vertices[caras[:, 2]]
        normales = np.cross(b - a, c - a)
        largo = np.linalg.norm(normales, axis=1, keepdims=True)
        validas = largo[:, 0] > 1e-12
        normales = np.divide(normales, largo, out=np.zeros_like(normales), where=largo > 1e-12)
        centros = (a + b + c) / 3.0

        indices = np.flatnonzero(validas)
        if len(indices) > muestras:
            indices = indices[np.linspace(0, len(indices) - 1, muestras).astype(np.int64)]
        if not len(indices):
            return IO.NodeOutput(mesh, "sin caras validas para medir", 0.0)

        dispositivo = mesh.vertices.device
        tri = torch.from_numpy(np.stack([a, b, c], axis=1).astype(np.float32)).to(dispositivo)
        bvh = _build_triangle_bvh(tri)

        # El rayo sale hacia dentro; el margen evita que choque con su propia cara.
        margen = max(grosor_min_mm * 0.02, 1e-3)
        origen = torch.from_numpy((centros[indices] - normales[indices] * margen).astype(np.float32)).to(dispositivo)
        direccion = torch.from_numpy((-normales[indices]).astype(np.float32)).to(dispositivo)
        finas = _any_hit_rays_bvh(origen, direccion, tri, bvh, tmin=margen, tmax=float(grosor_min_mm)).cpu().numpy()
        # Se pondera por superficie, no por numero de caras: una placa fina tiene pocas
        # caras grandes y muchas caras de canto, y contando caras salia un enganoso 33 %.
        areas = largo[indices, 0] / 2.0
        pct = 100.0 * float(areas[finas].sum()) / float(areas.sum())

        estado = "correcto" if pct <= aviso_pct else "REVISAR"
        informe = (
            f"grosor minimo   {grosor_min_mm:.1f} mm\n"
            f"caras medidas   {len(indices):,} de {len(caras):,}\n"
            f"zonas finas     {pct:.1f} % de la superficie\n"
            f"resultado       {estado}"
        )
        # Saber que hay un 5 % de zonas finas no sirve de nada si no se sabe donde: no es
        # lo mismo que esten en la peana, que se arregla engordandola, que en la cara.
        # La altura de impresion es el eje Y, que es como viene la malla del generador.
        if finas.any():
            alturas = centros[indices][:, 1]
            suelo, techo = float(vertices[:, 1].min()), float(vertices[:, 1].max())
            alto = max(techo - suelo, 1e-9)
            relativa = (alturas[finas] - suelo) / alto
            peso = areas[finas]
            total_fino = float(peso.sum()) or 1.0
            bandas = [("abajo ", relativa < 1 / 3),
                      ("medio ", (relativa >= 1 / 3) & (relativa < 2 / 3)),
                      ("arriba", relativa >= 2 / 3)]
            reparto = " · ".join(
                "%s %.0f %%" % (nombre, float(peso[donde].sum()) / total_fino * 100)
                for nombre, donde in bandas)
            informe += (f"\ndonde estan     {reparto}"
                        f"\n                entre {alturas[finas].min() - suelo:.0f} y "
                        f"{alturas[finas].max() - suelo:.0f} mm de altura")
        if pct > aviso_pct:
            informe += ("\n\nPartes demasiado delgadas: subir la altura de la pieza, engordarlas\n"
                        "en Blender o rechazar el encargo (flores, hojas, aristas de papel).")
        return IO.NodeOutput(mesh, informe, pct, ui={"text": (informe,)})


class ExoRevisarImprimible(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoRevisarImprimible",
            display_name="Revisar que se pueda imprimir (Exo)",
            category="3d/exo filaments",
            description=(
                "Lo que no ve el informe de medidas: si cabe en la cama, cuanta superficie son "
                "voladizos que van a necesitar soportes, cuanto apoya en la cama y si el centro "
                "de masa cae dentro de esa huella o la pieza se cae sola. Ponlo DESPUES de "
                "escalar a milimetros."
            ),
            inputs=[
                IO.Mesh.Input("mesh"),
                IO.Float.Input("cama_x_mm", default=350.0, min=50.0, max=2000.0, step=10.0),
                IO.Float.Input("cama_y_mm", default=350.0, min=50.0, max=2000.0, step=10.0),
                IO.Float.Input("cama_z_mm", default=350.0, min=50.0, max=2000.0, step=10.0),
                IO.Float.Input("angulo_voladizo", default=45.0, min=20.0, max=80.0, step=5.0,
                               tooltip="Inclinacion que tu impresora aguanta sin soportes. 45 grados "
                                       "es lo normal; con refrigeracion buena se puede subir."),
                IO.Boolean.Input("poner_de_pie", default=True,
                                 tooltip="La malla viene con Y arriba y se imprime con Z arriba. "
                                         "Quitalo solo si ya la giraste tu."),
            ],
            outputs=[
                IO.Mesh.Output("mesh"),
                IO.String.Output("informe"),
                IO.Boolean.Output("apto"),
                IO.Float.Output("voladizo_pct"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, mesh, cama_x_mm, cama_y_mm, cama_z_mm, angulo_voladizo, poner_de_pie):
        from .imprimibilidad import resumen, revisar

        vertices, caras = _primera_malla(mesh)
        informe = revisar(vertices.astype(np.float64), caras,
                          cama=(float(cama_x_mm), float(cama_y_mm), float(cama_z_mm)),
                          angulo=float(angulo_voladizo), ya_de_pie=not poner_de_pie)
        texto = resumen(informe)
        return IO.NodeOutput(mesh, texto, bool(informe["apto"]),
                             float(informe["voladizo_pct"]), ui={"text": (texto,)})


class ExoPresupuesto(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoPresupuesto",
            display_name="Presupuesto (Exo)",
            category="3d/exo filaments",
            description=(
                "Del peso de la pieza al precio: material, maquina, preparacion, mermas y "
                "margen. Los numeros del negocio se leen de config_local.json, que no se "
                "publica; si no los has puesto, avisa de que el precio es de ejemplo."
            ),
            inputs=[
                IO.Float.Input("peso_g", default=0.0, min=0.0, max=100_000.0, step=1.0,
                               tooltip="Enchufalo a la salida peso_g del informe de impresion."),
                IO.Float.Input("soportes_pct", default=0.0, min=0.0, max=200.0, step=5.0,
                               tooltip="Material extra que se tira en soportes. Con muchos "
                                       "voladizos, 20-40 %% no es raro."),
            ],
            outputs=[
                IO.String.Output("presupuesto"),
                IO.Float.Output("precio"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, peso_g, soportes_pct):
        from .presupuesto import calcular, resumen

        cuentas = calcular(float(peso_g), soportes_pct=float(soportes_pct))
        texto = resumen(cuentas)
        return IO.NodeOutput(texto, float(cuentas["precio"]), ui={"text": (texto,)})


class ExoGuardarImpresion(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoGuardarImpresion",
            display_name="Guardar para imprimir (Exo)",
            category="3d/exo filaments",
            description=(
                "Escribe el STL y, si la malla trae color, un OBJ con su MTL. "
                "El OBJ conserva una malla cerrada y asigna un material por color. "
                "En el laminador asigna cada material a un filamento distinto."
            ),
            inputs=[
                IO.Mesh.Input("mesh"),
                IO.String.Input("nombre", default="exo/pieza", multiline=False,
                                tooltip="Ruta dentro de la carpeta output de ComfyUI."),
                IO.Boolean.Input("guardar_obj", default=True,
                                 tooltip="Escribe tambien OBJ+MTL con el color, para impresion multicolor."),
                IO.Boolean.Input("poner_de_pie", default=True,
                                 tooltip="Gira SOLO el STL de Y arriba a Z arriba. El STL no lleva convencion de ejes "
                                         "y los laminadores usan Z; el OBJ si la lleva y lo corrige el propio laminador, "
                                         "asi que ese se deja tal cual (girarlo lo dejaria de lado)."),
                IO.Int.Input("max_colores",default=4,min=1,max=16),
                IO.String.Input("paleta_impresion",default=""),
                IO.Boolean.Input("guardar_3mf_experimental", default=False,
                                 tooltip="Pintura por filamento CFS en 3MF. Pendiente de validacion visual en Creality Print."),
            ],
            outputs=[IO.String.Output("rutas")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, mesh, nombre, guardar_obj, poner_de_pie=True, max_colores=4, paleta_impresion="", guardar_3mf_experimental=False):
        vertices, caras = _primera_malla(mesh)
        color_vert = _colores_srgb(mesh, len(vertices))
        # De Y arriba a Z arriba: (x, y, z) -> (x, -z, y). Solo para el STL, que no lleva
        # convencion de ejes: el OBJ si la lleva y el laminador ya lo endereza al importar.
        vertices_stl = (np.stack([vertices[:, 0], -vertices[:, 2], vertices[:, 1]], axis=1)
                        if poner_de_pie else vertices)

        carpeta, prefijo = os.path.split(nombre.strip() or "exo/pieza")
        ruta_base, nombre_archivo, contador, _, _ = folder_paths.get_save_image_path(
            os.path.join(carpeta, prefijo) if carpeta else prefijo, folder_paths.get_output_directory())
        destino = os.path.join(ruta_base, f"{nombre_archivo}_{contador:05}")
        os.makedirs(ruta_base, exist_ok=True)

        rutas = [_escribir_stl(destino + ".stl", vertices_stl, caras)]
        if guardar_obj and color_vert is not None:
            rutas.append(_escribir_obj(destino + ".obj", vertices, caras, color_vert, max_colores, paleta_impresion))
        if guardar_3mf_experimental and color_vert is not None:
            rutas.append(_escribir_3mf(destino + ".3mf", vertices_stl, caras, color_vert, max_colores, paleta_impresion))
        texto = "\n".join(rutas)
        return IO.NodeOutput(texto, ui={"text": (texto,)})


def _malla_exportable(vertices, caras):
    # Soldar posiciones sin unir colores; Manifold separa los contactos no manifold.
    vertices, indice = np.unique(np.asarray(vertices), axis=0, return_inverse=True)
    caras = indice[caras]
    entrada = MeshManifold(np.ascontiguousarray(vertices, dtype=np.float32),
                           np.ascontiguousarray(caras, dtype=np.uint32),
                           face_id=np.arange(len(caras), dtype=np.uint32))
    solido = Manifold(entrada)
    if solido.is_empty():
        raise ValueError(f"Reparar la malla antes de exportar: {solido.status()}")
    salida = solido.to_mesh()
    return np.asarray(salida.vert_properties[:, :3]), np.asarray(salida.tri_verts), np.asarray(salida.face_id)


def _escribir_stl(destino, vertices, caras):
    vertices, caras, _ = _malla_exportable(vertices, caras)
    a, b, c = vertices[caras[:, 0]], vertices[caras[:, 1]], vertices[caras[:, 2]]
    normales = np.cross(b - a, c - a)
    largo = np.linalg.norm(normales, axis=1, keepdims=True)
    normales = np.divide(normales, largo, out=np.zeros_like(normales), where=largo > 0)
    registro = np.zeros(len(caras), dtype=np.dtype([
        ("n", "<f4", 3), ("v1", "<f4", 3), ("v2", "<f4", 3), ("v3", "<f4", 3), ("attr", "<u2")]))
    registro["n"], registro["v1"], registro["v2"], registro["v3"] = normales, a, b, c
    with open(destino, "wb") as f:
        f.write(b"Exo filaments".ljust(80, b" "))
        f.write(struct.pack("<I", len(caras)))
        f.write(registro.tobytes())
    return destino


def _escribir_obj(destino, vertices, caras, color_vert, max_colores=4, paleta_impresion=""):
    """OBJ manifold con material por cara; no abre bordes para separar colores."""
    from .colores_caras import paleta_por_cara
    etiquetas, colores = paleta_por_cara(caras, color_vert, max_colores, paleta_impresion)
    vertices, caras, cara_origen = _malla_exportable(vertices, caras)
    etiquetas = etiquetas[cara_origen]
    mtl = os.path.splitext(destino)[0] + ".mtl"
    with open(mtl, "w", encoding="utf-8") as f:
        f.write("# Exo filaments - un material por filamento\n")
        for i, rgb in enumerate(colores):
            r, g, b = (float(v) for v in rgb)
            f.write(f"newmtl color_{i + 1}\nKa 0.0000 0.0000 0.0000\nKd {r:.4f} {g:.4f} {b:.4f}\n"
                    f"Ks 0.0000 0.0000 0.0000\nNs 10.0\nd 1.0\nillum 2\n\n")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(f"# Exo filaments\nmtllib {os.path.basename(mtl)}\no pieza\n")
        np.savetxt(f, vertices, fmt="v %.9g %.9g %.9g")
        f.write("s off\n")
        for i in range(len(colores)):
            grupo = caras[etiquetas == i].astype(np.int64) + 1
            if not len(grupo):
                continue
            f.write(f"g color_{i + 1}\nusemtl color_{i + 1}\n")
            np.savetxt(f, grupo, fmt="f %d %d %d")
    return destino



class ExoPlanImpresion(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(node_id="ExoPlanImpresion", display_name="Plan de impresion (Exo)",
            category="3d/exo filaments", inputs=[IO.Mesh.Input("mesh"),
            IO.Float.Input("capa_mm", default=0.2, min=0.05, max=1.0),
            IO.Combo.Input("sistema", options=["sin_confirmar", "cfs", "manual"], default="cfs"),
            IO.Int.Input("plazas", default=4, min=1, max=16),
            IO.Combo.Input("material", options=list(DENSIDAD), default="PLA"),
            IO.Float.Input("cama_x", default=350, min=1, max=2000),
            IO.Float.Input("cama_y", default=350, min=1, max=2000),
            IO.Float.Input("cama_z", default=350, min=1, max=2000)],
            outputs=[IO.String.Output("plan_json")], is_output_node=True)
    @classmethod
    def execute(cls, mesh, capa_mm, sistema, plazas, cama_x, cama_y, cama_z, material):
        from .plan_impresion import analizar, resumen
        v,f=_primera_malla(mesh)
        plan=analizar(v,f,_colores_srgb(mesh,len(v)),capa_mm,plazas,sistema,(cama_x,cama_y,cama_z),material)
        from pathlib import Path
        import uuid
        relativa = "3d/exo/plan_" + uuid.uuid4().hex + ".json"
        destino = Path(folder_paths.get_output_directory()) / relativa
        destino.parent.mkdir(parents=True,exist_ok=True)
        destino.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
        return IO.NodeOutput(json.dumps(plan,ensure_ascii=False),ui={"text":(resumen(plan),),"plan_archivo":[relativa]})


class ExoAuditarTextura(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(node_id="ExoAuditarTextura",display_name="Auditar origen del color (Exo)",category="3d/exo filaments",
            inputs=[IO.Mesh.Input("original"),IO.Mesh.Input("reparada"),IO.Voxel.Input("voxel_colors")],
            outputs=[IO.String.Output("informe")],is_output_node=True)
    @classmethod
    def execute(cls,original,reparada,voxel_colors):
        from scipy.spatial import cKDTree
        from pathlib import Path
        import uuid
        coords=voxel_colors.data.detach().cpu().numpy()
        coords=coords[:,-3:]
        posiciones=coords.astype(np.float32)/voxel_colors.resolution-.5
        colores=voxel_colors.voxel_colors.detach().cpu().numpy()[:,:3]
        tree=cKDTree(posiciones)
        carpeta=Path(folder_paths.get_output_directory())/"diagnostico_color"/uuid.uuid4().hex
        carpeta.mkdir(parents=True)
        informe={"resolution":int(voxel_colors.resolution),"voxeles":len(posiciones),"etapas":{}}
        for nombre,mesh in [("antes_reparacion",original),("despues_reparacion",reparada)]:
            total=int(mesh.vertex_counts[0]) if mesh.vertex_counts is not None else mesh.vertices.shape[1]
            indices=torch.linspace(0,total-1,min(total,40000),device=mesh.vertices.device).long()
            v=mesh.vertices[0,indices].detach().cpu().numpy()
            dist,idx=tree.query(v,workers=2)
            c=np.clip(colores[idx],0,1)
            np.savez_compressed(carpeta/(nombre+".npz"),vertices=v,colores=c,distancias=dist)
            informe['etapas'][nombre]={"vertices_originales":total,"bbox_min":v.min(0).tolist(),"bbox_max":v.max(0).tolist(),
                "distancia_mediana":float(np.median(dist)),"distancia_p99":float(np.quantile(dist,.99))}
        (carpeta/'informe.json').write_text(json.dumps(informe,indent=2),encoding='utf-8')
        texto=str(carpeta)
        return IO.NodeOutput(texto,ui={"text":(texto,)})


class ExoTransferirColor(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(node_id="ExoTransferirColor", display_name="Transferir color de superficie (Exo)",
            category="3d/exo filaments", inputs=[IO.Mesh.Input("mesh"), IO.Mesh.Input("referencia"),
            IO.Voxel.Input("voxel_colors")], outputs=[IO.Mesh.Output("mesh"), IO.String.Output("informe")])

    @classmethod
    def execute(cls, mesh, referencia, voxel_colors):
        import copy
        from .transferencia_color import transferir
        if voxel_colors.data.shape[0] == 0:
            raise ValueError("Campo de color vacio: regenerar textura")
        destino = mesh.vertices[0].detach().cpu().numpy()
        original = referencia.vertices[0].detach().cpu().numpy()
        if mesh.vertex_counts is not None:
            destino = destino[:int(mesh.vertex_counts[0])]
        if referencia.vertex_counts is not None:
            original = original[:int(referencia.vertex_counts[0])]
        coords = voxel_colors.data.detach().cpu().numpy()[:, -3:]
        posiciones = coords.astype(np.float32) / voxel_colors.resolution - 0.5
        colores = voxel_colors.voxel_colors.detach().cpu().numpy()
        c, distancias = transferir(destino, original, posiciones, colores, voxel_colors.resolution)
        salida = copy.copy(mesh)
        # glTF exige RGB lineal; conservar el mismo contrato que _colores_srgb.
        lineal = srgb_a_lineal(c).astype(np.float32)
        if mesh.vertex_counts is not None:
            completo = np.zeros((mesh.vertices.shape[1], 3), dtype=np.float32)
            completo[:len(lineal)] = lineal
            lineal = completo
        salida.vertex_colors = torch.from_numpy(lineal).unsqueeze(0).to(mesh.vertices.device)
        informe = f"Color proyectado desde superficie original; distancia p99: {np.quantile(distancias, .99):.6g}"
        return IO.NodeOutput(salida, informe)


class ExoProyectarColorFrontal(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(node_id="ExoProyectarColorFrontal",display_name="Color de foto frontal (Exo)",
            category="3d/exo filaments",description="Proyeccion ortografica para fotos frontales alineadas. Solo colorea superficies visibles; revisar ojos y limites.",
            inputs=[IO.Mesh.Input("mesh"),IO.Image.Input("imagen"),IO.Mask.Input("mascara"), IO.Boolean.Input("completar_oscuras",default=False, tooltip="Infere el color de regiones oscuras conectadas a una zona clara de la referencia. Revisar los perfiles.")],
            outputs=[IO.Mesh.Output("mesh"),IO.String.Output("informe")])
    @classmethod
    def execute(cls,mesh,imagen,mascara,completar_oscuras=False):
        import copy
        from .proyeccion_color import proyectar
        v,f=_primera_malla(mesh)
        colores=_colores_srgb(mesh,len(v))
        if colores is None:raise ValueError("La malla necesita el color generado para las zonas ocultas")
        im=imagen[0].detach().cpu().numpy()
        mask=mascara[0].detach().cpu().numpy()
        c,visibles=proyectar(v,f,colores,im,mask,completar_oscuras)
        salida=copy.copy(mesh)
        salida.vertex_colors=torch.from_numpy(srgb_a_lineal(c).astype(np.float32)).unsqueeze(0)
        informe=f"Foto frontal aplicada a {100*visibles.mean():.1f}% de vertices; completar regiones oscuras: {completar_oscuras}. Revisar alineacion y perfiles."
        return IO.NodeOutput(salida,informe)

class ExoCargarMallaSalida(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(node_id="ExoCargarMallaSalida",display_name="Cargar malla generada (Exo)",
            category="3d/exo filaments",inputs=[IO.String.Input("archivo",default="")],outputs=[IO.Mesh.Output("mesh")])
    @classmethod
    def execute(cls,archivo):
        from pathlib import Path
        from .cargar_glb import cargar
        from comfy_api.latest import Types
        base=Path(folder_paths.get_output_directory()).resolve()
        p=(base/archivo).resolve()
        if not p.is_relative_to(base) or p.suffix.lower()!='.glb':
            raise ValueError("Elegir un GLB dentro de output")
        if p.stat().st_size>64*1024*1024:
            raise ValueError("Elegir la malla reparada, menor de 64 MB; la malla en bruto consume demasiada RAM")
        vertices,caras,colores=cargar(p)
        v=torch.from_numpy(vertices).unsqueeze(0)
        f=torch.from_numpy(caras).unsqueeze(0)
        c=torch.from_numpy(colores).unsqueeze(0)
        return IO.NodeOutput(Types.MESH(vertices=v,faces=f,vertex_colors=c))

class ExoSegmentarColoresImagen(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(node_id="ExoSegmentarColoresImagen",display_name="Colores predominantes del sujeto (Exo)",
            category="3d/exo filaments",inputs=[IO.Image.Input("imagen"),IO.Mask.Input("mascara"),IO.Int.Input("plazas",default=4,min=1,max=16)],
            outputs=[IO.String.Output("paleta")],is_output_node=True)
    @classmethod
    def execute(cls,imagen,mascara,plazas=4):
        from .segmentacion_imagen import segmentar
        datos=segmentar(imagen[0].detach().cpu().numpy(),mascara[0].detach().cpu().numpy(),plazas)
        return IO.NodeOutput(datos["paleta"],ui={"segmentacion":[datos]})









def _escribir_3mf(destino, vertices, caras, color_vert, max_colores=4, paleta_impresion=""):
    from .tresmf import escribir_3mf

    from .colores_caras import paleta_por_cara
    etiquetas, colores = paleta_por_cara(caras, color_vert, max_colores, paleta_impresion)
    vertices, caras, origen = _malla_exportable(vertices, caras)
    return escribir_3mf(destino, vertices, caras, etiquetas[origen], colores)

NODOS = [ExoPaletaFilamentos, ExoInformeImpresion, ExoRevisarPieza, ExoSolidificar, ExoRevisarGrosor, ExoRevisarImprimible, ExoPresupuesto, ExoGuardarImpresion, ExoPlanImpresion, ExoAuditarTextura, ExoTransferirColor, ExoProyectarColorFrontal, ExoCargarMallaSalida, ExoSegmentarColoresImagen]
