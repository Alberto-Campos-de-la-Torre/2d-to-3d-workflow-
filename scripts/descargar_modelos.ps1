# Descarga modelos de Hugging Face a las carpetas de ComfyUI, con reanudacion y verificacion SHA256.
$modelos = @(
  # FLUX.2 Klein (editar imagen a partir de instrucciones) - Apache 2.0
  @{ repo='black-forest-labs/FLUX.2-klein-base-4b-fp8'; ruta='flux-2-klein-base-4b-fp8.safetensors'; destino='diffusion_models\flux-2-klein-base-4b-fp8.safetensors' }
  @{ repo='Comfy-Org/z_image_turbo'; ruta='split_files/text_encoders/qwen_3_4b.safetensors';   destino='text_encoders\qwen_3_4b.safetensors' }
  @{ repo='black-forest-labs/FLUX.2-small-decoder'; ruta='full_encoder_small_decoder.safetensors'; destino='vae\full_encoder_small_decoder.safetensors' }
  @{ repo='Comfy-Org/BiRefNet';   ruta='background_removal/birefnet.safetensors';            destino='background_removal\birefnet.safetensors' }
  @{ repo='Comfy-Org/hunyuan3D_2.1_repackaged'; ruta='hunyuan_3d_v2.1.safetensors';          destino='checkpoints\hunyuan_3d_v2.1.safetensors' }
  @{ repo='Comfy-Org/TRELLIS.2';  ruta='diffusion_models/trellis_2_int8_convrot.safetensors'; destino='diffusion_models\trellis_2_int8_convrot.safetensors' }
  @{ repo='Comfy-Org/Pixal3D';    ruta='vae/trellis_2_shape_vae_bf16.safetensors';           destino='vae\trellis_2_shape_vae_bf16.safetensors' }
  @{ repo='Comfy-Org/Pixal3D';    ruta='vae/trellis_2_texture_vae_bf16.safetensors';         destino='vae\trellis_2_texture_vae_bf16.safetensors' }
  @{ repo='Comfy-Org/Pixal3D';    ruta='clip_vision/dino_v3_L_naf_fp32.safetensors';         destino='clip_vision\dino_v3_L_naf_fp32.safetensors' }
  @{ repo='Comfy-Org/MoGe';       ruta='geometry_estimation/moge_2_vitl_normal_fp16.safetensors'; destino='geometry_estimation\moge_2_vitl_normal_fp16.safetensors' }
)
$base = 'D:\AI3D\ComfyUI_windows_portable\ComfyUI\models'

foreach ($m in $modelos) {
  $destino = Join-Path $base $m.destino
  New-Item -ItemType Directory -Force (Split-Path $destino) | Out-Null
  $meta = (Invoke-RestMethod "https://huggingface.co/api/models/$($m.repo)/tree/main/$(Split-Path $m.ruta -Parent)") |
            Where-Object { $_.path -eq $m.ruta }
  $sha = $meta.lfs.oid
  if ((Test-Path $destino) -and (Get-Item $destino).Length -eq $meta.size) {
    if ((Get-FileHash $destino -Algorithm SHA256).Hash.ToLower() -eq $sha) { "YA ESTABA  $($m.destino)"; continue }
  }
  $url = "https://huggingface.co/$($m.repo)/resolve/main/$($m.ruta)"
  "DESCARGANDO $($m.destino) ($([math]::Round($meta.size/1MB)) MB)"
  for ($i = 1; $i -le 20; $i++) {
    curl.exe -L --fail -s -C - --retry 5 --retry-all-errors -o $destino $url
    if ($LASTEXITCODE -eq 0) { break }
    "  reintento $i (codigo $LASTEXITCODE)"
  }
  if ((Get-FileHash $destino -Algorithm SHA256).Hash.ToLower() -eq $sha) { "OK         $($m.destino)" }
  else { "CHECKSUM MAL $($m.destino)" }
}
