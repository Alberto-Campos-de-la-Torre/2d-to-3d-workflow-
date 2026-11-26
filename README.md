# Exo: imagen 2D y modelos 3D locales

Dos modulos de ComfyUI que pueden usarse por separado o conectarse mediante imagenes.
Se comparte codigo, configuracion de ejemplo, workflows y pruebas. No se incluyen
pesos, modelos generados, fotos, pedidos, inventarios ni configuracion privada.

| Perfil | Entrada y salida | Interfaz |
|---|---|---|
| [2D](modules/2d/README.md) | Prompt/referencias → imagen | `/exo/estudio` |
| [3D](modules/3d/README.md) | Imagen → malla y archivos de impresion | `/exo/pieza` |
| [Ambos](integration/README.md) | Prompt → imagen → modelo | Ambas |

## Instalar

Requiere una instalacion de ComfyUI compatible. El codigo se probo originalmente
con ComfyUI 0.37.1; los nodos de los modelos y ComfyUI-GGUF se instalan aparte.

```powershell
python instalar.py --comfyui <carpeta-ComfyUI> --perfil 2d
# o: --perfil 3d / --perfil ambos
# Usar el interprete de ComfyUI para instalar sus requisitos:
<python-ComfyUI> -m pip install -r <carpeta-ComfyUI>/custom_nodes/exo_filaments/requirements.txt
```

Consulta [REQUISITOS.md](REQUISITOS.md) para los nombres de modelos y dependencias.
El instalador no descarga pesos, no copia datos y no cambia una instalacion existente
sin `--actualizar`. Para actualizar se debe detener ComfyUI; se guarda un respaldo.

## Configuracion privada

Copia `config_local.ejemplo.json` como `config_local.json` en la carpeta de ComfyUI,
o establece `EXO_CONFIG` con su ruta. Configura `EXO_IA_URL` para tu LLM compatible
con OpenAI. Los endpoints y precios de ejemplo no son datos de una instalacion real.
`EXO_HOME` permite elegir la carpeta de datos de los scripts independientes.

Para iniciar con los `.bat`, establece `EXO_COMFYUI` (carpeta que contiene main.py)
y `EXO_PYTHON` (Python de ComfyUI). El inicio LAN solo debe usarse en una red de
confianza; no incorpora autenticacion y permite generar y borrar archivos.

## Flujo e impresion

[TUTORIAL.md](TUTORIAL.md) recoge el uso de taller y sus limitaciones. El cierre de una
malla no garantiza fidelidad, resistencia ni una impresion correcta. Revisa color,
escala, estabilidad, grosor y el laminado antes de fabricar.

La paleta puede proponerse desde la imagen y ajustarse a las bobinas. Un CFS con
cuatro filamentos necesita reducir colores. El borrado muestra el alcance antes
de confirmar y conserva referencias compartidas. Las relaciones nuevas se guardan
en un catalogo local que nunca se publica.

## Desarrollo y seguridad

- `modules/2d`, `modules/3d`: codigo de cada perfil.
- `modules/common`: utilidades compartidas, incluidas por el instalador.
- `integration`: conexion y workflow integrado opcionales.
- `custom_nodes/` y `workflows/`: version anterior conservada para compatibilidad;
  la instalacion modular usa exclusivamente `modules/` e `integration/`.
- `scripts/pruebas`: pruebas; no contienen resultados ni imagenes del taller.
- [SECURITY.md](SECURITY.md): revision antes de compartir y limites de la auditoria.

Cada modelo externo conserva su licencia: consulta su distribucion antes de usarlo.
Este repositorio no concede derechos sobre modelos ni imagenes de terceros.
