"""Genera el flujo 'Exo - imagen a pieza imprimible' y lo guarda en ComfyUI.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\crear_flujo_exo.py

Convierte el grafo en formato API (el que usa generar_3d.py) al formato del editor,
consultando /object_info para saber el orden y el tipo de cada entrada. Queda en
ComfyUI\\user\\default\\workflows, listo para abrirlo desde la interfaz.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generar_3d import SERVIDOR, workflow

DESTINO = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\user\default\workflows\Exo - imagen a pieza imprimible.json")
COLUMNA, FILA = 380, 210


def catalogo():
    with urllib.request.urlopen(SERVIDOR + "/object_info", timeout=60) as r:
        return json.loads(r.read())


def entradas_de(info):
    """Nombre, tipo y si es un widget (valor escrito) o una conexion."""
    salida = []
    for grupo in ("required", "optional"):
        for nombre, definicion in (info["input"].get(grupo) or {}).items():
            tipo = definicion[0]
            es_lista = isinstance(tipo, list)
            opciones = definicion[1] if len(definicion) > 1 else {}
            salida.append({
                "nombre": nombre,
                "tipo": "COMBO" if es_lista else tipo,
                "widget": es_lista or tipo in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO", "COMFY_DYNAMICCOMBO_V3", "COLOR"),
                "opciones": opciones,
            })
    return salida


def colocar(grafo):
    """Coloca cada nodo en la columna de su profundidad: el grafo se lee de izquierda a
    derecha y los cables dejan de cruzarse."""
    profundidad = {}

    def calcular(nid, visitando=()):
        if nid in profundidad:
            return profundidad[nid]
        if nid in visitando:
            return 0
        padres = [str(v[0]) for v in grafo[nid]["inputs"].values()
                  if isinstance(v, list) and len(v) == 2 and str(v[0]) in grafo]
        profundidad[nid] = 0 if not padres else 1 + max(calcular(p, visitando + (nid,)) for p in padres)
        return profundidad[nid]

    for nid in grafo:
        calcular(nid)

    posicion, usados = {}, {}
    for nid in sorted(grafo, key=lambda n: (profundidad[n], int(n))):
        columna = profundidad[nid]
        fila = usados.get(columna, 0)
        usados[columna] = fila + 1
        posicion[nid] = (COLUMNA * columna, FILA * fila)
    return posicion


def construir(grafo, info_nodos):
    nodos, enlaces, siguiente_enlace = [], [], 1
    orden = list(grafo)
    posicion = colocar(grafo)

    # Primero las salidas de cada nodo, para poder enlazarlas despues.
    salidas_por_nodo = {nid: (info_nodos[grafo[nid]["class_type"]].get("output") or []) for nid in orden}
    enlaces_salida = {nid: [[] for _ in salidas_por_nodo[nid]] for nid in orden}

    borradores = {}
    for nid in orden:
        clase = grafo[nid]["class_type"]
        info = info_nodos[clase]
        campos = entradas_de(info)
        entradas_nodo, widgets = [], []
        for campo in campos:
            valor = grafo[nid]["inputs"].get(campo["nombre"])
            if isinstance(valor, list) and len(valor) == 2 and str(valor[0]) in grafo:
                origen, ranura = str(valor[0]), int(valor[1])
                entrada = {"name": campo["nombre"], "type": campo["tipo"], "link": siguiente_enlace}
                if campo["widget"]:
                    # Campo que normalmente se teclea y aqui llega por cable: el editor
                    # necesita saber que widget sustituye, o lo dibuja como entrada suelta.
                    entrada["widget"] = {"name": campo["nombre"]}
                entradas_nodo.append(entrada)
                enlaces.append([siguiente_enlace, int(origen), ranura, int(nid), len(entradas_nodo) - 1, campo["tipo"]])
                enlaces_salida[origen][ranura].append(siguiente_enlace)
                siguiente_enlace += 1
            elif campo["widget"]:
                if valor is None:
                    valor = campo["opciones"].get("default", "")
                widgets.append(valor)
                # Las semillas llevan un segundo valor (el control de "aleatorio").
                if campo["nombre"] == "seed":
                    widgets.append("fixed")
            elif valor is not None:
                entradas_nodo.append({"name": campo["nombre"], "type": campo["tipo"], "link": None})

        borradores[nid] = {
            "id": int(nid), "type": clase, "pos": list(posicion[nid]), "size": [330, 120],
            "flags": {}, "order": orden.index(nid), "mode": 0,
            "inputs": entradas_nodo, "widgets_values": widgets,
            "properties": {"Node name for S&R": clase},
        }

    for nid in orden:
        salidas = []
        for i, tipo in enumerate(salidas_por_nodo[nid]):
            nombre = (info_nodos[grafo[nid]["class_type"]].get("output_name") or [])
            salidas.append({
                "name": nombre[i] if i < len(nombre) else str(tipo),
                "type": tipo, "links": enlaces_salida[nid][i], "slot_index": i,
            })
        borradores[nid]["outputs"] = salidas
        nodos.append(borradores[nid])

    return {
        "id": "exo-imagen-a-pieza", "revision": 0, "last_node_id": max(int(n) for n in orden),
        "last_link_id": siguiente_enlace - 1, "nodes": nodos, "links": enlaces, "groups": [],
        "config": {}, "extra": {}, "version": 0.4,
    }


def main():
    info_nodos = catalogo()
    grafo = workflow("trellis2", "ejemplo.png", "3d/exo/pieza", 20, 7.5, 0, 42, True, "#FFFFFF", True)
    # Los tres nodos propios, encadenados detras del color por vertice (PaintMesh).
    grafo["200"] = {"class_type": "ExoPaletaFilamentos", "inputs": {
        "mesh": ["73", 0], "paleta": "#1a1a1a,#f2f2f2,#8a8d8c,#ffd500",
        "colores": 4, "peso_luz": 0.25, "min_mancha": 0.3, "suavizar_bordes": 3}}
    grafo["201"] = {"class_type": "ExoInformeImpresion", "inputs": {
        "mesh": ["200", 0], "altura_mm": 80.0, "material": "PLA", "relleno": 15.0, "pared_mm": 1.2}}
    grafo["202"] = {"class_type": "ExoRevisarGrosor", "inputs": {
        "mesh": ["201", 0], "grosor_min_mm": 1.2, "aviso_pct": 5.0, "muestras": 4000}}
    grafo["203"] = {"class_type": "ExoGuardarImpresion", "inputs": {
        "mesh": ["202", 0], "nombre": "exo/pieza", "guardar_obj": True, "poner_de_pie": True}}

    flujo = construir(grafo, info_nodos)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(flujo, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"guardado: {DESTINO}")
    print(f"nodos: {len(flujo['nodes'])} Â· enlaces: {len(flujo['links'])}")


if __name__ == "__main__":
    main()

