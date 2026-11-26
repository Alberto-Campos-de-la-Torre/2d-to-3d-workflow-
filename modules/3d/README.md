# Modulo 3D

Imagen a malla, textura, reparacion, colores predominantes y filamentos, exportacion
STL/OBJ/3MF/GLB, comprobaciones, plan y cortes. No carga Qwen ni el Estudio 2D.

Instalar: `python instalar.py --comfyui <carpeta-ComfyUI> --perfil 3d`.
Instala sus requisitos usando el Python de ComfyUI y abre `/exo/pieza`.
Los motores y BiRefNet se descargan aparte (consulta REQUISITOS.md).
Recibe un PNG/JPEG propio, o uno exportado por el modulo 2D. El LLM de revision es
opcional: un fallo del juez deja el color sin verificar y requiere revision humana.
