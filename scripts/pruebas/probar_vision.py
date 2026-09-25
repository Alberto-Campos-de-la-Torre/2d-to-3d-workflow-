"""Comprueba si la IA local puede mirar una imagen y juzgarla (necesario para el bucle de correccion).

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\probar_vision.py [imagen.png]
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prompt_ia import ajustes, modelo_disponible

SALIDA = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\output\qwen21")
ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(SALIDA.glob("*.png"))[-1]

cfg = ajustes()
url = cfg["ia_url"].rstrip("/")
modelo = cfg["ia_modelo"] or modelo_disponible(url)
datos = base64.b64encode(ruta.read_bytes()).decode()

pregunta = (
    "Mira la imagen y responde SOLO con este JSON, sin texto alrededor:\n"
    '{"objetos": <cuantos objetos principales>, "recortado": <true si algo se sale del encuadre>, '
    '"fondo_liso": <true/false>, "sombras_duras": <true/false>, "texto_o_marca": <true/false>, '
    '"partes_finas": <true/false>, "transparente": <true/false>, "que_es": "<en 3 palabras>", '
    '"apto_para_3d": <true/false>, "problemas": ["..."]}'
)

cuerpo = {
    "model": modelo,
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": pregunta},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{datos}"}},
    ]}],
    "max_tokens": 500,
    "temperature": 0.2,
    "stream": False,
    "chat_template_kwargs": {"enable_thinking": False},
}

print(f"imagen: {ruta.name} ({round(ruta.stat().st_size / 1024)} KB) · modelo: {modelo}")
inicio = time.time()
peticion = urllib.request.Request(url + "/chat/completions", data=json.dumps(cuerpo).encode(),
                                  headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(peticion, timeout=240) as r:
        respuesta = json.loads(r.read())
except Exception as e:
    raise SystemExit(f"FALLO: {e}")

texto = respuesta["choices"][0]["message"].get("content", "")
print(f"tiempo: {time.time() - inicio:.1f} s\n--- respuesta:\n{texto}")
