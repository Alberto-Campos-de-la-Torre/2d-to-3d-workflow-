# Requisitos

## Equipo

| | Minimo probado | Notas |
|---|---|---|
| GPU | NVIDIA 16 GB (RTX 5070 Ti) | El pico de VRAM llega a 15,5 GB con TRELLIS.2 y color. Con 12 GB habria que bajar la resolucion de textura. |
| RAM | 32 GB | Las mallas en bruto de TRELLIS.2 pasan de 100 M de caras. |
| Disco | 60 GB libres | Solo los modelos ocupan unos 30 GB. |
| SO | Windows 10/11 | Los scripts usan rutas de Windows. |

## Programas

| Programa | Version probada | Para que |
|---|---|---|
| ComfyUI portable (NVIDIA) | 0.36 - 0.37 | El motor de todo. Usar la compilacion con CUDA 12.8 o superior en tarjetas RTX 50. |
| Blender | 5.2 LTS | Solo para los scripts de reparacion y de render de control. Los nodos no lo necesitan. |
| 7-Zip | cualquiera | Para descomprimir ComfyUI portable. |

Python, PyTorch y numpy/scipy vienen dentro de ComfyUI portable: **no hay que instalar
nada con pip**. Los scripts se ejecutan con el interprete embebido:

    ComfyUI_windows_portable\python_embeded\python.exe scripts\generar_3d.py ...

## Modelos

`scripts\descargar_modelos.ps1` los baja con verificacion de checksum y reanudacion si se
corta la conexion. Total: unos 30 GB.

### Imprescindibles

| Archivo | Carpeta de ComfyUI | Tamano | Origen |
|---|---|---|---|
| `birefnet.safetensors` | `models/background_removal/` | 424 MB | Comfy-Org/BiRefNet |
| `hunyuan3d-dit-v2_fp16.safetensors` | `models/checkpoints/` | 4,7 GB | Comfy-Org/hunyuan3D_2.0_repackaged |

Con esto ya funciona el flujo de imagen a 3D sin color (Hunyuan3D 2.0, unos 30 s por pieza).

### Para color y multicolor (TRELLIS.2)

| Archivo | Carpeta | Tamano |
|---|---|---|
| `trellis_2_int8_convrot.safetensors` | `models/diffusion_models/` | 5,0 GB |
| `trellis_2_shape_vae_bf16.safetensors` | `models/vae/` | 1,0 GB |
| `trellis_2_texture_vae_bf16.safetensors` | `models/vae/` | 905 MB |
| `dino_v3_L_naf_fp32.safetensors` | `models/clip_vision/` | 1,2 GB |
| `moge_2_vitl_normal_fp16.safetensors` | `models/geometry_estimation/` | 631 MB |

### Opcionales

| Archivo | Carpeta | Tamano | Para que |
|---|---|---|---|
| `hunyuan_3d_v2.1.safetensors` | `models/checkpoints/` | 7,0 GB | Segunda opinion cuando 2.0 falla |
| `flux-2-klein-base-4b-fp8.safetensors` | `models/diffusion_models/` | 3,9 GB | Editar la foto del cliente (Apache 2.0, uso comercial) |
| `qwen_3_4b.safetensors` | `models/text_encoders/` | 7,7 GB | Codificador de texto de FLUX.2 Klein |
| `full_encoder_small_decoder.safetensors` | `models/vae/` | 238 MB | VAE de FLUX.2 Klein |

### Solo para el flujo de texto a pieza (uso NO comercial)

| Archivo | Carpeta | Para que |
|---|---|---|
| `qwen-image-2.1-*.gguf` | `models/unet/` | Generador de imagen a partir del prompt |
| `qwen3vl_8b_int8_convrot.safetensors` | `models/text_encoders/` | Su codificador de texto |
| `qwen_image_2.1_vae_bf16.safetensors` | `models/vae/` | Su VAE |

Necesita ademas el nodo [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF).
**Licencia Qwen Research: solo investigacion y evaluacion, no pedidos de pago.**

## Comprobar que todo esta

Con ComfyUI arrancado:

    python scripts\pruebas\probar_grosor.py        # valida la medicion de pared
    python scripts\pruebas\probar_solidificar.py   # valida el cerrado solido
