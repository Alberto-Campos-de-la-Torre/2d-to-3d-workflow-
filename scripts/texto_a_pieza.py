"""De un prompt a una pieza imprimible, en una sola orden.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\texto_a_pieza.py "un gato sentado, figura de resina" [--altura 80] [--semilla 42] [--paleta "#1a1a1a,#f2f2f2"]

Genera la imagen con Qwen-Image 2.1, la pasa a 3D, la solidifica y guarda STL y OBJ.
Uso NO comercial: la licencia de Qwen no cubre pedidos de clientes.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from crear_flujo_texto_a_pieza import grafo_completo
from generar_3d import peticion
from prompt_ia import mejorar

AYUDA_PROMPT = (", single complete object, centered, plain neutral background, "
                "soft even lighting, no text, full object visible")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt")
    p.add_argument("--altura", type=float, default=80.0, help="altura final de la pieza en mm")
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--paleta", default="", help="colores de tus bobinas: '#1a1a1a,#f2f2f2,...'")
    p.add_argument("--tal-cual", action="store_true",
                   help="usa el texto tal cual, sin pasarlo por la IA ni anadir indicaciones")
    p.add_argument("--sin-ia", action="store_true",
                   help="no usar la IA local: solo anade las indicaciones de encuadre")
    args = p.parse_args()

    # Por defecto la idea corta la amplia la IA local; si no contesta, se sigue igual.
    if args.tal_cual:
        prompt = args.prompt
    elif args.sin_ia:
        prompt = args.prompt + AYUDA_PROMPT
    else:
        prompt, aviso = mejorar(args.prompt, "3d", semilla=args.semilla)
        if aviso:
            print(f"AVISO: {aviso}")
            prompt = args.prompt + AYUDA_PROMPT
    print(f"prompt: {prompt}\n", flush=True)

    inicio = time.time()
    grafo = grafo_completo(prompt, args.semilla, args.altura, args.paleta)
    respuesta = peticion("/prompt", json.dumps({"prompt": grafo}).encode(), {"Content-Type": "application/json"})
    if respuesta.get("node_errors"):
        raise SystemExit("nodos rechazados: " + json.dumps(respuesta["node_errors"], indent=1)[:1500])

    pid = respuesta["prompt_id"]
    while True:
        historial = peticion(f"/history/{pid}")
        if pid in historial:
            break
        time.sleep(3)

    estado = historial[pid].get("status", {})
    salidas = historial[pid]["outputs"]
    for nodo, titulo in [("62", "solidificado"), ("200", "paleta"), ("201", "informe"), ("202", "grosor"), ("203", "archivos")]:
        texto = salidas.get(nodo, {}).get("text")
        if texto:
            print(f"--- {titulo}\n{texto[0]}")
    imagen = salidas.get("9", {}).get("images")
    if imagen:
        print(f"--- imagen generada\noutput\\{imagen[0].get('subfolder', '')}\\{imagen[0]['filename']}")
    print(f"\nestado: {estado.get('status_str')} en {time.time() - inicio:.0f} s")
    if estado.get("status_str") != "success":
        print(json.dumps(estado.get("messages", []))[:1000])


if __name__ == "__main__":
    main()

