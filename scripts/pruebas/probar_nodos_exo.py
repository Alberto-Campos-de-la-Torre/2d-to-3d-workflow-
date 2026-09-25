"""Prueba los nodos de Exo filaments sobre una imagen real, de punta a punta.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_nodos_exo.py <imagen>
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generar_3d import peticion, subir_imagen, workflow

imagen = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\AI3D\pruebas\entrada\images.jpg")
paleta = sys.argv[2] if len(sys.argv) > 2 else "#c41e3a,#ffd500,#0046ad,#1a1a1a"

nombre = subir_imagen(imagen)
grafo = workflow("trellis2", nombre, "3d/trellis2/nodo_exo", 20, 7.5, 0, 42, True, "#FFFFFF", True)

# La malla con color ya limpia sale de PaintMesh (nodo 73 del ramal de texturas).
grafo["200"] = {"class_type": "ExoPaletaFilamentos", "inputs": {
    "mesh": ["73", 0], "paleta": paleta, "colores": 4,
    "peso_luz": 0.25, "min_mancha": 0.3, "suavizar_bordes": 3}}
grafo["201"] = {"class_type": "ExoInformeImpresion", "inputs": {
    "mesh": ["200", 0], "altura_mm": 60.0, "material": "PLA", "relleno": 15.0, "pared_mm": 1.2}}
grafo["202"] = {"class_type": "ExoRevisarGrosor", "inputs": {
    "mesh": ["201", 0], "grosor_min_mm": 1.2, "aviso_pct": 5.0, "muestras": 4000}}
grafo["203"] = {"class_type": "ExoGuardarImpresion", "inputs": {
    "mesh": ["202", 0], "nombre": "exo/cubo", "guardar_obj": True, "poner_de_pie": True}}

inicio = time.time()
respuesta = peticion("/prompt", json.dumps({"prompt": grafo}).encode(), {"Content-Type": "application/json"})
if respuesta.get("node_errors"):
    raise SystemExit("nodos rechazados: " + json.dumps(respuesta["node_errors"], indent=1)[:2000])

pid = respuesta["prompt_id"]
while True:
    historial = peticion(f"/history/{pid}")
    if pid in historial:
        break
    time.sleep(2)

estado = historial[pid].get("status", {})
print(f"estado: {estado.get('status_str')} en {time.time() - inicio:.0f} s")
if estado.get("status_str") != "success":
    print(json.dumps(estado.get("messages", []), indent=1)[:3000])
    raise SystemExit(1)

for nodo, salida in historial[pid]["outputs"].items():
    print(f"--- nodo {nodo}: {json.dumps(salida)[:800]}")


