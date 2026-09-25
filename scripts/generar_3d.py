"""Genera mallas 3D (solo geometria) a traves de la API local de ComfyUI.

Motores disponibles: hy2.0 (Hunyuan3D 2.0), hy2.1 (Hunyuan3D 2.1) y trellis2 (TRELLIS.2).

Uso (desde D:\\AI3D):
  ComfyUI_windows_portable\\python_embeded\\python.exe scripts\\generar_3d.py [imagen o carpeta] [--motor hy2.1] [--semilla 42]

Por defecto procesa todas las imagenes de D:\\AI3D\\pruebas\\entrada y anade una fila por
imagen a D:\\AI3D\\pruebas\\registro_pruebas.csv. ComfyUI debe estar arrancado (Iniciar_ComfyUI_3D.bat).
"""
import argparse
import csv
import json
import mimetypes
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

SERVIDOR = "http://127.0.0.1:8188"
BASE = Path(r"D:\AI3D")
ENTRADA = BASE / "pruebas" / "entrada"
REGISTRO = BASE / "pruebas" / "registro_pruebas.csv"
SALIDA_COMFY = BASE / "ComfyUI_windows_portable" / "ComfyUI" / "output"
EXTENSIONES = {".png", ".jpg", ".jpeg", ".webp"}

# Valores tomados de las plantillas oficiales de ComfyUI para cada motor.
MOTORES = {
    "hy2.0": {"ckpt": "hunyuan3d-dit-v2_fp16.safetensors", "pasos": 20, "cfg": 5.5, "res": 3072, "crop": "none"},
    "hy2.1": {"ckpt": "hunyuan_3d_v2.1.safetensors", "pasos": 30, "cfg": 5.0, "res": 4096, "crop": "center"},
    "trellis2": {"pasos": 20, "cfg": 7.5},
}


def recorte_fondo(color_fondo):
    """BiRefNet: recorta el objeto para que el fondo no se convierta en geometria."""
    return {
        "90": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": "birefnet.safetensors"}},
        "91": {"class_type": "RemoveBackground", "inputs": {"bg_removal_model": ["90", 0], "image": ["56", 0]}},
        "92": {"class_type": "ImageCropToMask", "inputs": {
            "images": ["56", 0], "masks": ["91", 0], "width": 1024, "height": 1024,
            "pad_factor": 1.05, "grow_mask": 0, "background": color_fondo}},
    }


def workflow_hunyuan(cfg_motor, imagen, prefijo, pasos, cfg, res, semilla, entrada_imagen, extra):
    # Grafo de las plantillas "3d_hunyuan3d_image_to_model" y "3d_hunyuan3d-v2.1".
    return {
        **extra,
        "54": {"class_type": "ImageOnlyCheckpointLoader", "inputs": {"ckpt_name": cfg_motor["ckpt"]}},
        "56": {"class_type": "LoadImage", "inputs": {"image": imagen}},
        "51": {"class_type": "CLIPVisionEncode", "inputs": {"clip_vision": ["54", 1], "image": entrada_imagen, "crop": cfg_motor["crop"]}},
        "80": {"class_type": "Hunyuan3Dv2Conditioning", "inputs": {"clip_vision_output": ["51", 0]}},
        "70": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["54", 0], "shift": 1.0}},
        "66": {"class_type": "EmptyLatentHunyuan3Dv2", "inputs": {"resolution": res, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["70", 0], "positive": ["80", 0], "negative": ["80", 1], "latent_image": ["66", 0],
            "seed": semilla, "steps": pasos, "cfg": cfg, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "61": {"class_type": "VAEDecodeHunyuan3D", "inputs": {"samples": ["3", 0], "vae": ["54", 2], "num_chunks": 8000, "octree_resolution": 256}},
        "81": {"class_type": "VoxelToMesh", "inputs": {"voxel": ["61", 0], "algorithm": "surface net", "threshold": 0.6}},
        "82": {"class_type": "SaveGLB", "inputs": {"mesh": ["81", 0], "filename_prefix": prefijo}},
    }


def workflow_trellis2(imagen, prefijo, pasos, cfg, semilla, entrada_imagen, extra, texturas=False, textura_px=2048):
    # Rama de geometria de la plantilla "3d_pixal3d_trellis2_image_to_model": estructura
    # (voxel) -> forma -> upsample. Se omiten textura, remallado y decimado: eso lo hace
    # despues el script de Blender, y asi la comparacion con Hunyuan es de malla en bruto.
    return {
        **extra,
        "56": {"class_type": "LoadImage", "inputs": {"image": imagen}},
        "10": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "dino_v3_L_naf_fp32.safetensors"}},
        "11": {"class_type": "VAELoader", "inputs": {"vae_name": "trellis_2_shape_vae_bf16.safetensors"}},
        "12": {"class_type": "UNETLoader", "inputs": {"unet_name": "trellis_2_int8_convrot.safetensors", "weight_dtype": "default"}},
        "13": {"class_type": "Trellis2Conditioning", "inputs": {"clip_vision_model": ["10", 0], "image": entrada_imagen}},
        # Cadena de modelo para la etapa de estructura.
        "20": {"class_type": "CFGOverride", "inputs": {"model": ["12", 0], "cfg": 1.0, "start_percent": 0.667, "end_percent": 1.0}},
        "21": {"class_type": "RescaleCFG", "inputs": {"model": ["20", 0], "multiplier": 0.7}},
        "22": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["21", 0], "shift": 5.0}},
        # Cadena de modelo para las etapas de forma y upsample.
        "23": {"class_type": "CFGOverride", "inputs": {"model": ["12", 0], "cfg": 1.0, "start_percent": 0.769, "end_percent": 1.0}},
        "24": {"class_type": "RescaleCFG", "inputs": {"model": ["23", 0], "multiplier": 0.5}},
        "30": {"class_type": "EmptyTrellis2LatentStructure", "inputs": {"batch_size": 1}},
        "31": {"class_type": "KSampler", "inputs": {
            "model": ["22", 0], "positive": ["13", 0], "negative": ["13", 1], "latent_image": ["30", 0],
            "seed": semilla, "steps": 12, "cfg": cfg, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "32": {"class_type": "VaeDecodeStructureTrellis2", "inputs": {"samples": ["31", 0], "vae": ["11", 0], "resolution": "32"}},
        "33": {"class_type": "Trellis2ShapeStage", "inputs": {"positive": ["13", 0], "negative": ["13", 1], "voxel": ["32", 0]}},
        "34": {"class_type": "KSampler", "inputs": {
            "model": ["24", 0], "positive": ["33", 0], "negative": ["33", 1], "latent_image": ["33", 2],
            "seed": semilla, "steps": pasos, "cfg": cfg, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "35": {"class_type": "Trellis2UpsampleStage", "inputs": {
            "positive": ["33", 0], "negative": ["33", 1], "shape_latent": ["34", 0], "vae": ["11", 0], "target_resolution": "1536"}},
        "36": {"class_type": "KSampler", "inputs": {
            "model": ["24", 0], "positive": ["35", 0], "negative": ["35", 1], "latent_image": ["35", 2],
            "seed": semilla, "steps": 12, "cfg": cfg, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "37": {"class_type": "VaeDecodeShapeTrellis", "inputs": {"samples": ["36", 0], "vae": ["11", 0]}},
        "82": {"class_type": "SaveGLB", "inputs": {"mesh": ["37", 0], "filename_prefix": prefijo}},
        **(rama_texturas(prefijo, semilla, textura_px) if texturas else {}),
    }


def rama_texturas(prefijo, semilla, textura_px=2048):
    """Color para TRELLIS.2: limpia la malla, genera el color y saca dos GLB.

    - <nombre>_textura: malla con UV y textura horneada -> vista previa para el cliente.
    - <nombre>_vertices: malla con color por vertice -> base para separar colores de
      impresion multicolor (ver scripts/colores_a_piezas.py).

    El remallado + decimado a 700k caras es el de la plantilla oficial: ademas de dejar
    la malla apta para el desplegado UV, evita las salidas de 100M+ de caras en bruto.
    """
    return {
        "60": {"class_type": "VAELoader", "inputs": {"vae_name": "trellis_2_texture_vae_bf16.safetensors"}},
        "61": {"class_type": "GetMeshInfo", "inputs": {"mesh": ["37", 0]}},
        # Aqui iba el RemeshMesh de la plantilla oficial, pero se midio que no cierra la
        # malla: con "udf" devuelve una cascara hueca y con "sdf" empeora los agujeros
        # (de 41.574 a 187.813 en la llave). El nodo propio rasteriza, rellena el interior
        # y reconstruye: deja 0 agujeros en todas las piezas probadas.
        "62": {"class_type": "ExoSolidificar", "inputs": {
            "mesh": ["61", 0], "resolucion": 320, "cerrar_grietas": 1, "suavizar_forma": 5}},
        "63": {"class_type": "DecimateMesh", "inputs": {"mesh": ["62", 0], "target_face_count": 700000, "placement_mode": "midpoint"}},
        "64": {"class_type": "MeshSmoothNormals", "inputs": {"mesh": ["63", 0], "crease_angle": 180.0}},
        # Muestreo del color sobre la forma ya generada.
        "65": {"class_type": "Trellis2TextureStage", "inputs": {"positive": ["35", 0], "negative": ["35", 1], "shape_latent": ["36", 0]}},
        "66": {"class_type": "KSampler", "inputs": {
            "model": ["12", 0], "positive": ["65", 0], "negative": ["65", 1], "latent_image": ["65", 2],
            "seed": semilla + 1, "steps": 12, "cfg": 1.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "67": {"class_type": "VaeDecodeTextureTrellis", "inputs": {"samples": ["66", 0], "vae": ["60", 0], "shape_subdivides": ["37", 1]}},
        # Salida 1: textura horneada en UV. El horneado a 2048 px se queda sin VRAM con
        # las mallas mas pesadas (el conejo, de 127M de caras, reventaba a 28,8 GiB).
        "68": {"class_type": "UnwrapMesh", "inputs": {"mesh": ["64", 0], "segmenter": "pec", "resolution": textura_px, "padding": 1, "weld_distance": 0.0002}},
        # La referencia es la malla ya solidificada (64), no la de 135M de caras que sale
        # del modelo (37): con esa, el horneado se quedaba sin VRAM y tumbaba la pieza.
        "69": {"class_type": "BakeTextureFromVoxel", "inputs": {"mesh": ["68", 0], "voxel_colors": ["67", 0], "texture_size": textura_px, "reference_mesh": ["64", 0]}},
        "70": {"class_type": "ApplyTextureToMesh", "inputs": {"mesh": ["68", 0], "base_color": ["69", 0]}},
        "71": {"class_type": "MeshToFile3D", "inputs": {"mesh": ["70", 0]}},
        "72": {"class_type": "Save3DAdvanced", "inputs": {
            "model_3d": ["71", 0], "filename_prefix": prefijo + "_textura", "viewport_state": "", "width": 1024, "height": 1024}},
        # Salida 2: color por vertice.
        "73": {"class_type": "PaintMesh", "inputs": {"mesh": ["64", 0], "voxel_colors": ["67", 0]}},
        "74": {"class_type": "MeshToFile3D", "inputs": {"mesh": ["73", 0]}},
        "75": {"class_type": "Save3DAdvanced", "inputs": {
            "model_3d": ["74", 0], "filename_prefix": prefijo + "_vertices", "viewport_state": "", "width": 1024, "height": 1024}},
    }


def workflow(motor, imagen, prefijo, pasos, cfg, res, semilla, sin_fondo=True, color_fondo="#FFFFFF", texturas=False, textura_px=2048):
    cfg_motor = MOTORES[motor]
    extra = recorte_fondo(color_fondo) if sin_fondo else {}
    entrada_imagen = ["92", 0] if sin_fondo else ["56", 0]
    if motor == "trellis2":
        return workflow_trellis2(imagen, prefijo, pasos, cfg, semilla, entrada_imagen, extra, texturas, textura_px)
    if texturas:
        raise SystemExit("--texturas solo esta disponible con --motor trellis2")
    return workflow_hunyuan(cfg_motor, imagen, prefijo, pasos, cfg, res, semilla, entrada_imagen, extra)


def peticion(ruta, datos=None, cabeceras=None):
    req = urllib.request.Request(SERVIDOR + ruta, data=datos, headers=cabeceras or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def subir_imagen(ruta):
    limite = uuid.uuid4().hex
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    cuerpo = (
        f"--{limite}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{ruta.name}\"\r\n"
        f"Content-Type: {tipo}\r\n\r\n"
    ).encode() + ruta.read_bytes() + (
        f"\r\n--{limite}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{limite}--\r\n"
    ).encode()
    r = peticion("/upload/image", cuerpo, {"Content-Type": f"multipart/form-data; boundary={limite}"})
    return r["name"]


class MedidorVRAM(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.pico_mb = 0
        self.parar = threading.Event()

    def run(self):
        while not self.parar.is_set():
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout
                self.pico_mb = max(self.pico_mb, int(out.strip().splitlines()[0]))
            except Exception:
                pass
            self.parar.wait(0.5)


def generar(ruta, args):
    nombre = subir_imagen(ruta)
    prefijo = f"3d/{args.motor}/{ruta.stem}" + ("" if args.sin_fondo else "_confondo")
    medidor = MedidorVRAM()
    medidor.start()
    inicio = time.time()
    grafo = workflow(args.motor, nombre, prefijo, args.pasos, args.cfg, args.res, args.semilla,
                     args.sin_fondo, args.color_fondo, args.texturas)
    respuesta = peticion("/prompt", json.dumps({"prompt": grafo}).encode(), {"Content-Type": "application/json"})
    # ComfyUI descarta las ramas que no validan y ejecuta el resto sin avisar.
    if respuesta.get("node_errors"):
        raise RuntimeError("nodos descartados: " + json.dumps(respuesta["node_errors"])[:800])
    pid = respuesta["prompt_id"]
    while True:
        historial = peticion(f"/history/{pid}")
        if pid in historial:
            break
        time.sleep(1)
    segundos = round(time.time() - inicio, 1)
    medidor.parar.set()
    estado = historial[pid].get("status", {})
    if estado.get("status_str") != "success":
        raise RuntimeError(json.dumps(estado.get("messages", []))[:1500])
    glb = None
    for salida in historial[pid]["outputs"].values():
        for lista in salida.values():
            for f in lista if isinstance(lista, list) else []:
                if isinstance(f, dict) and str(f.get("filename", "")).endswith(".glb"):
                    glb = SALIDA_COMFY / f.get("subfolder", "") / f["filename"]
    return segundos, round(medidor.pico_mb / 1024, 1), glb


def main():
    p = argparse.ArgumentParser()
    p.add_argument("origen", nargs="?", default=str(ENTRADA))
    p.add_argument("--motor", choices=sorted(MOTORES), default="hy2.0")
    p.add_argument("--pasos", type=int)
    p.add_argument("--cfg", type=float)
    p.add_argument("--res", type=int)
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--con-fondo", dest="sin_fondo", action="store_false", help="no recortar el fondo con BiRefNet")
    p.add_argument("--color-fondo", default="#FFFFFF", help="color detras del objeto recortado")
    p.add_argument("--texturas", action="store_true", help="genera color: GLB texturizado + GLB con color por vertice (solo trellis2)")
    args = p.parse_args()
    # Si no se indican, se usan los valores de la plantilla oficial del motor elegido.
    predeterminados = MOTORES[args.motor]
    args.pasos = args.pasos or predeterminados["pasos"]
    args.cfg = args.cfg or predeterminados["cfg"]
    args.res = args.res or predeterminados.get("res", 0)

    origen = Path(args.origen)
    imagenes = [origen] if origen.is_file() else sorted(f for f in origen.iterdir() if f.suffix.lower() in EXTENSIONES)
    if not imagenes:
        print(f"No hay imagenes en {origen}")
        return

    siguiente_id = sum(1 for _ in REGISTRO.open(encoding="utf-8")) if REGISTRO.exists() else 1
    for ruta in imagenes:
        print(f"-> {ruta.name} ...", flush=True)
        try:
            segundos, vram, glb = generar(ruta, args)
        except Exception as e:
            print(f"   ERROR: {e}")
            continue
        print(f"   OK {segundos}s | VRAM pico {vram} GB | {glb}")
        with REGISTRO.open("a", newline="", encoding="utf-8") as f:
            fondo = "sin fondo" if args.sin_fondo else "con fondo"
            csv.writer(f).writerow([siguiente_id, ruta.name, "", args.motor, args.pasos, 256, segundos, vram, "", "",
                                    f"{fondo} cfg={args.cfg} res={args.res} semilla={args.semilla}"])
        siguiente_id += 1


if __name__ == "__main__":
    main()

