"""Entrada de ComfyUI para perfiles 2D y 3D independientes."""
from comfy_api.latest import ComfyExtension
from .perfil import MODULOS

NODOS=[]
if "2d" in MODULOS:
    from .nodes_2d import NODOS as NODOS_2D
    NODOS.extend(NODOS_2D)
    from . import estudio
if "3d" in MODULOS:
    from .nodes import NODOS as NODOS_3D
    NODOS.extend(NODOS_3D)
    from . import pieza
from . import resultados
WEB_DIRECTORY="./js"

class ExtensionExoFilaments(ComfyExtension):
    async def get_node_list(self):
        return NODOS

async def comfy_entrypoint():
    return ExtensionExoFilaments()
