"""Genera el flujo 'Exo - Qwen-Image 2.1 (GGUF)' y lo guarda en ComfyUI.

  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\crear_flujo_qwen.py

Es el mismo grafo que lanza el estudio (/exo/estudio), para abrirlo en el editor de
nodos cuando haga falta tocar algo que el estudio no ofrece. Guarda en output/qwen21,
asi que lo que salga de aqui tambien aparece en la galeria del estudio.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from crear_flujo_exo import catalogo, construir

DESTINO = Path(r"D:\AI3D\ComfyUI_windows_portable\ComfyUI\user\default\workflows\Exo - Qwen-Image 2.1 (GGUF).json")

GRAFO = {
    "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "qwen-image-2.1-UC-Q8_0.gguf"}},
    "2": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
    "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
        "clip": ["2", 0], "vae": ["3", 0], "resolution": 1024, "negative_prompt": "",
        "prompt": "Small vinyl-toy style dragon figurine sitting, single complete object, centered, "
                  "plain neutral background, soft even lighting, no text."}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "6": {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1], "latent_image": ["5", 0],
        "seed": 42, "steps": 25, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
    "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
    "9": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "qwen21/qwen"}},
}


def main():
    flujo = construir(GRAFO, catalogo())
    flujo["id"] = "exo-qwen-image-21"
    DESTINO.write_text(json.dumps(flujo, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"guardado: {DESTINO}")


if __name__ == "__main__":
    main()
