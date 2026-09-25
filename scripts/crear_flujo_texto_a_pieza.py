"""Genera el flujo 'Exo - texto a pieza (Qwen)': de un prompt a un STL imprimible.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\crear_flujo_texto_a_pieza.py

Encadena el grafo de Qwen-Image 2.1 con el de pieza imprimible: la imagen generada entra
directamente al recorte de fondo, sin pasar por disco ni por el nodo Load Image.

OJO CON LA LICENCIA: Qwen-Image 2.1 es Qwen Research License, solo uso NO comercial.
Para pedidos de clientes hay que generar la imagen con FLUX.2 Klein (Apache 2.0) o con
una foto del propio cliente.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from crear_flujo_exo import catalogo, construir
from generar_3d import workflow

DESTINO = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\user\default\workflows\Exo - texto a pieza (Qwen).json")

PROMPT = ("Small vinyl-toy style dragon figurine sitting, single complete object, centered, "
          "plain neutral background, soft even lighting, no text.")


def grafo_qwen(prompt, semilla=42, lado=1024, pasos=25, idea=None):
    """Texto -> imagen. La salida ["7", 0] es la imagen que alimenta la parte 3D.

    Con 'idea', el prompt lo escribe la IA local a partir de esa frase corta (nodo 8),
    y lo que se teclea en 'prompt' se ignora.
    """
    escritor = {}
    if idea is not None:
        escritor = {"8": {"class_type": "ExoPromptIA", "inputs": {
            "idea": idea, "modo": "3d", "servidor": "", "modelo": "",
            "temperatura": 0.8, "semilla": semilla}}}
        prompt = ["8", 0]
    return {
        **escritor,
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen-image-2.1-UC-Q8_0.gguf"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["2", 0], "vae": ["3", 0], "resolution": lado,
            "negative_prompt": "varios objetos, recortado, texto, marca de agua, fondo con cosas",
            "prompt": prompt}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": lado, "height": lado, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1], "latent_image": ["5", 0],
            "seed": semilla, "steps": pasos, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        # Se guarda la imagen: sirve para revisarla y para repetir la pieza sin regenerarla.
        "9": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "qwen21/pieza"}},
    }


def grafo_pieza(origen_imagen, prefijo="3d/texto/pieza", nombre_salida="texto/pieza", paleta="", altura_mm=80.0):
    """El grafo de pieza imprimible, pero alimentado por una imagen ya en memoria."""
    grafo = workflow("trellis2", "ejemplo.png", prefijo, 20, 7.5, 0, 42, True, "#FFFFFF", True)
    del grafo["56"]   # fuera el Load Image: la imagen llega del generador
    for nodo in grafo.values():
        for entrada, valor in nodo["inputs"].items():
            if isinstance(valor, list) and len(valor) == 2 and str(valor[0]) == "56":
                nodo["inputs"][entrada] = list(origen_imagen)

    grafo["200"] = {"class_type": "ExoPaletaFilamentos", "inputs": {
        "mesh": ["73", 0], "paleta": paleta, "colores": 4,
        "peso_luz": 0.25, "min_mancha": 0.3, "suavizar_bordes": 3}}
    grafo["201"] = {"class_type": "ExoInformeImpresion", "inputs": {
        "mesh": ["200", 0], "altura_mm": altura_mm, "material": "PLA", "relleno": 15.0, "pared_mm": 1.2}}
    grafo["202"] = {"class_type": "ExoRevisarGrosor", "inputs": {
        "mesh": ["201", 0], "grosor_min_mm": 1.2, "aviso_pct": 5.0, "muestras": 4000}}
    grafo["203"] = {"class_type": "ExoGuardarImpresion", "inputs": {
        "mesh": ["202", 0], "nombre": nombre_salida, "guardar_obj": True, "poner_de_pie": True}}
    return grafo


def grafo_completo(prompt=PROMPT, semilla=42, altura_mm=80.0, paleta="", idea=None):
    return {**grafo_qwen(prompt, semilla, idea=idea),
            **grafo_pieza(["7", 0], altura_mm=altura_mm, paleta=paleta)}


def main():
    # El flujo guardado trae el escritor de prompts delante: se teclea una idea corta.
    flujo = construir(grafo_completo(idea="un buho estilizado de ceramica"), catalogo())
    flujo["id"] = "exo-texto-a-pieza"
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(flujo, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"guardado: {DESTINO}")
    print(f"nodos: {len(flujo['nodes'])} Â· enlaces: {len(flujo['links'])}")


if __name__ == "__main__":
    main()

