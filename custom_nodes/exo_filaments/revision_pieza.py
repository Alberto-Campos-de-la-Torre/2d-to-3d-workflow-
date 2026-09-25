"""Revisa la pieza terminada: la renderiza desde varias vistas y se la ensena a la IA.

Es el unico punto del sistema donde algo mira la PIEZA, no la imagen ni los numeros. La
malla puede estar cerrada, con buen grosor y buen peso, y aun asi no parecerse a lo que
pidio el cliente: el conejo salio como cascara hueca y solo se vio leyendo el volumen.

Usa los nodos nativos RotateMesh y RenderMesh, asi que no depende de Blender.
"""
import io
import json

import numpy as np
import torch

from .critica import _extraer_json, _preguntar

# Cuatro vistas: frente, perfil, espalda y tres cuartos desde arriba.
VISTAS = [
    ("frente", (0.0, 0.0, 0.0)),
    ("perfil", (0.0, 90.0, 0.0)),
    ("espalda", (0.0, 180.0, 0.0)),
    ("tres cuartos", (-25.0, 225.0, 0.0)),
]

PREGUNTA = (
    "Estas revisando una pieza 3D antes de imprimirla. La imagen muestra la MISMA pieza "
    "desde cuatro angulos: frente, perfil, espalda y tres cuartos.\n"
    "PASO 1: describe que ves en cada vista y si las cuatro son coherentes entre si. "
    "Fijate en si falta alguna parte por detras, si hay bultos o hundimientos raros, si la "
    "figura esta deformada y si se sostiene de pie.\n"
    "PASO 2: termina con una unica linea que empiece por JSON: y contenga\n"
    '{"que_parece":"<en 3 palabras>","coincide":<true si corresponde a lo pedido>,'
    '"partes_faltantes":<true/false>,"deforme":<true/false>,"espalda_mal":<true/false>,'
    '"se_sostiene":<true/false>,"defectos":["<que y donde>"]}'
)

PESOS = {"no_coincide": 3, "partes_faltantes": 3, "deforme": 3, "espalda_mal": 2,
         "no_se_sostiene": 2, "hueca": 3}

# Respuestas que significan "sin defectos" y no deben contarse como uno.
NO_ES_DEFECTO = {"ninguno", "ninguna", "none", "n/a", "na", "sin defectos", "no hay",
                 "nada", "sin problemas", "correcto", "-"}

# Por debajo de esta fraccion de su caja envolvente, la pieza es una cascara hueca.
# El conejo ocupaba 0,07 de su caja (31 cm3 en una caja de 424) y en el render no se nota:
# la vista no distingue macizo de hueco, para eso estan los numeros.
LLENADO_MINIMO = 0.10


def _girar(mesh, angulos):
    from comfy_extras.nodes_save_3d import RotateMesh

    if angulos == (0.0, 0.0, 0.0):
        return mesh
    modo = {"mode": "euler_xyz", "angle_x": angulos[0], "angle_y": angulos[1], "angle_z": angulos[2]}
    return RotateMesh.execute(mesh=mesh, mode=modo).result[0]


def _render(mesh, lado=512, fondo="#202020"):
    from comfy_extras.nodes_mesh_postprocess import RenderMesh

    salida = RenderMesh.execute(mesh=mesh, mode="auto", width=lado, height=lado, background=fondo)
    return salida.result[0]


def hoja_de_vistas(mesh, lado=512):
    """Las cuatro vistas en una sola imagen 2x2: una consulta en vez de cuatro."""
    from PIL import Image

    hoja = Image.new("RGB", (lado * 2, lado * 2), (32, 32, 32))
    for i, (_nombre, angulos) in enumerate(VISTAS):
        imagen = _render(_girar(mesh, angulos), lado)
        datos = np.clip(imagen[0].detach().cpu().numpy() * 255, 0, 255).astype(np.uint8)
        hoja.paste(Image.fromarray(datos), ((i % 2) * lado, (i // 2) * lado))
    return hoja


def medir_llenado(mesh):
    """Que fraccion de su caja envolvente ocupa la pieza. Delata las cascaras huecas."""
    vertices = mesh.vertices[0].detach().cpu().numpy().astype(np.float64)
    caras = mesh.faces[0].detach().cpu().numpy().astype(np.int64)
    a, b, c = vertices[caras[:, 0]], vertices[caras[:, 1]], vertices[caras[:, 2]]
    volumen = abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    caja = float(np.prod(vertices.max(axis=0) - vertices.min(axis=0))) or 1.0
    return round(volumen / caja, 3)


def revisar_pieza(mesh, descripcion="", lado=512):
    """Devuelve (informe, hoja de vistas). 'descripcion' es lo que se pidio, para comparar."""
    hoja = hoja_de_vistas(mesh, lado)
    llenado = medir_llenado(mesh)

    pregunta = PREGUNTA
    if descripcion.strip():
        pregunta += f"\n\nLo que se pidio era: {descripcion.strip()}"

    texto, aviso = _preguntar(hoja, pregunta, tokens=900, temperatura=0.2)
    if aviso:
        return {"avisos": [aviso], "defectos": [], "puntuacion": None, "apto": None}, hoja

    datos = _extraer_json(texto)
    defectos, detalle = [], []

    def marcar(clave, motivo):
        defectos.append(clave)
        detalle.append(motivo)

    # Solo se exige coincidencia si se dijo que se pedia.
    if descripcion.strip() and datos.get("coincide") is False:
        marcar("no_coincide", f"no se parece a lo pedido; parece {datos.get('que_parece', '?')}")
    if datos.get("partes_faltantes"):
        marcar("partes_faltantes", "faltan partes de la figura")
    if datos.get("deforme"):
        marcar("deforme", "la figura esta deformada")
    if datos.get("espalda_mal"):
        marcar("espalda_mal", "la parte de atras esta mal resuelta")
    if datos.get("se_sostiene") is False:
        marcar("no_se_sostiene", "no se sostiene de pie: hara falta base o soportes")

    # La lista en texto manda: en las pruebas las banderas se quedaban cortas.
    for problema in (datos.get("defectos") or []):
        texto_problema = str(problema).strip()
        if not texto_problema or texto_problema.lower().strip(" .") in NO_ES_DEFECTO:
            continue
        if texto_problema not in detalle:
            detalle.append(texto_problema)
            if not defectos:
                defectos.append("otros")

    # Lo que la vista no puede ver: una cascara hueca se renderiza igual que un macizo.
    if llenado < LLENADO_MINIMO:
        marcar("hueca", f"parece hueca: ocupa {llenado} de su caja (gastara poco material)")

    informe = {
        "que_parece": datos.get("que_parece", ""),
        "llenado": llenado,
        "defectos": defectos,
        "detalle": detalle,
        "puntuacion": round(10.0 - sum(PESOS.get(d, 1) for d in defectos), 1),
        "apto": not defectos,
        "avisos": [],
        "descripcion": descripcion,
    }
    return informe, hoja


def resumen(informe):
    if informe.get("avisos"):
        return "AVISO: " + "; ".join(informe["avisos"])
    lineas = [f"parece: {informe.get('que_parece', '?')} · puntuacion {informe.get('puntuacion')}/10"
              f" · llena {informe.get('llenado')} de su caja"]
    lineas += [f"  - {d}" for d in informe.get("detalle", [])] or ["  sin problemas a la vista"]
    if "no_coincide" in informe.get("defectos", []):
        lineas.append("  (ojo: con piezas abstractas o muy estilizadas suele equivocarse aqui)")
    return "\n".join(lineas)


def a_imagen_comfy(pil):
    """PIL -> IMAGE de ComfyUI, para poder ver la hoja de vistas en el grafo."""
    datos = np.asarray(pil.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(datos).unsqueeze(0)
