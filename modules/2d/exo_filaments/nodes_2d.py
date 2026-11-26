"""Nodos de imagen y prompts; no importa motores ni librerias de mallas."""
import json
import numpy as np
from comfy_api.latest import IO

def _a_pil(imagen):
    """IMAGE de ComfyUI (B,H,W,C en 0..1) -> PIL, primera del lote."""
    from PIL import Image

    datos = imagen[0].detach().cpu().numpy()
    return Image.fromarray(np.clip(datos * 255, 0, 255).astype(np.uint8))

class ExoRevisarImagen(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoRevisarImagen",
            display_name="Revisar imagen (Exo)",
            category="3d/exo filaments",
            description=(
                "Mira la imagen con tu IA local y busca lo que arruina la conversion a 3D: objeto "
                "recortado, varios objetos, marca de agua, partes finas, transparencias. En figuras y "
                "personajes revisa ademas la anatomia (extremidades de mas, partes fusionadas, manos). "
                "Devuelve el informe, si esta apta y una puntuacion para comparar intentos."
            ),
            inputs=[
                IO.Image.Input("image"),
                IO.Combo.Input("revisar_anatomia", options=["auto", "siempre", "nunca"], default="auto",
                               tooltip="'auto' la revisa solo si la IA ve una figura, un animal o un personaje."),
                IO.Int.Input("referencias", default=0, min=0, max=2,
                             tooltip="Referencias que se usaron al generar. Con 2, tener varios objetos "
                                     "deja de contar como defecto: puede ser justo lo que se pidio."),
                IO.Int.Input("ciclos", default=2, min=1, max=4,
                             tooltip="Cuantas veces insistir en cada pregunta de anatomia cuando la "
                                     "primera sale limpia. El modelo es inconstante: hay fallos que "
                                     "ve en una pasada y no en la siguiente. Se para en cuanto "
                                     "encuentra algo, asi que solo cuesta tiempo en las imagenes "
                                     "que estan bien."),
                IO.Boolean.Input("para3d", default=True,
                                 tooltip="Puesto, exige lo que necesita la conversion a pieza: un objeto "
                                         "entero, macizo, opaco y sobre fondo liso. Quitado, solo busca "
                                         "los fallos de cualquier imagen (anatomia, recortes, marcas de "
                                         "agua, encuadre)."),
            ],
            outputs=[
                IO.String.Output("informe"),
                IO.Boolean.Output("apto"),
                IO.Float.Output("puntuacion"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, image, revisar_anatomia, referencias=0, para3d=True, ciclos=2):
        from .critica import criticar, resumen

        modo = {"auto": "auto", "siempre": True, "nunca": False}[revisar_anatomia]
        informe = criticar(_a_pil(image), modo, int(referencias), bool(para3d), int(ciclos))
        texto = resumen(informe)
        return IO.NodeOutput(json.dumps(informe, ensure_ascii=False), bool(informe.get("apto")),
                             float(informe.get("puntuacion") or 0.0), ui={"text": (texto,)})

class ExoCorregirPrompt(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoCorregirPrompt",
            display_name="Corregir prompt (Exo)",
            category="3d/exo filaments",
            description=(
                "Toma el informe de 'Revisar imagen' y devuelve el prompt corregido, el negativo "
                "reforzado y una semilla nueva. Las correcciones son fijas por tipo de defecto, no "
                "improvisadas: cambiar la semilla es lo que mas arregla los fallos de anatomia."
            ),
            inputs=[
                IO.String.Input("prompt", multiline=True, default=""),
                IO.String.Input("informe", multiline=True, default="",
                                tooltip="La salida 'informe' del nodo Revisar imagen."),
                IO.String.Input("negativo", multiline=False, default=""),
                IO.Int.Input("semilla", default=0, min=0, max=0xFFFFFFFF),
            ],
            outputs=[
                IO.String.Output("prompt"),
                IO.String.Output("negativo"),
                IO.Int.Output("semilla"),
                IO.Int.Output("pasos"),
            ],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, prompt, informe, negativo, semilla):
        from .critica import corregir

        try:
            datos = json.loads(informe) if informe.strip() else {}
        except json.JSONDecodeError:
            datos = {}
        nuevo, nuevo_negativo, cambios = corregir(prompt, negativo, datos, semilla)
        defectos = datos.get("defectos") or []
        texto = (f"defectos: {', '.join(defectos) if defectos else 'ninguno'}\n"
                 f"semilla: {semilla} -> {cambios['seed']}\n"
                 f"pasos: {cambios.get('steps', 20)}\n\n{nuevo}")
        return IO.NodeOutput(nuevo, nuevo_negativo, int(cambios["seed"]), int(cambios.get("steps", 20)),
                             ui={"text": (texto,)})

class ExoPromptIA(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="ExoPromptIA",
            display_name="Prompt con IA (Exo)",
            category="3d/exo filaments",
            description=(
                "Convierte una idea corta en un prompt completo usando tu IA local. En modo '3d' "
                "obliga a lo que necesita la conversion a modelo: un objeto entero, centrado, fondo "
                "liso y sin formas imposibles de imprimir. Si el servidor no contesta, devuelve la "
                "idea tal cual y lo avisa, para no tumbar el flujo."
            ),
            inputs=[
                IO.String.Input("idea", multiline=True, default="un buho estilizado de ceramica",
                                tooltip="Lo que quieres, en una linea y en el idioma que prefieras."),
                IO.Combo.Input("modo", options=["3d", "imagen"], default="3d",
                               tooltip="'3d' anade las reglas para que la pieza salga imprimible; 'imagen' solo amplia la idea."),
                IO.String.Input("servidor", default="", multiline=False,
                                tooltip="Vacio = el de config_local.json o la variable EXO_IA_URL."),
                IO.String.Input("modelo", default="", multiline=False,
                                tooltip="Vacio = el primero que sirva el servidor."),
                IO.Float.Input("temperatura", default=0.8, min=0.0, max=2.0, step=0.1),
                IO.Int.Input("semilla", default=0, min=0, max=0xFFFFFFFF,
                             control_after_generate=True,
                             tooltip="Cambiala para obtener otra redaccion de la misma idea."),
                IO.Int.Input("referencias", default=0, min=0, max=2,
                             tooltip="Cuantas imagenes de referencia se van a usar. Con 1 el prompt "
                                     "describe el cambio; con 2 aplica las reglas medidas (el objeto "
                                     "sale de la referencia 1 y el atributo hay que nombrarlo)."),
            ],
            outputs=[IO.String.Output("prompt")],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, idea, modo, servidor, modelo, temperatura, semilla, referencias=0):
        from .prompt_ia import mejorar

        prompt, aviso = mejorar(idea, modo, servidor or None, modelo or None,
                                temperatura=temperatura, semilla=semilla or None,
                                referencias=int(referencias))
        texto = f"AVISO: {aviso}\n\n{prompt}" if aviso else prompt
        return IO.NodeOutput(prompt, ui={"text": (texto,)})

NODOS = [ExoPromptIA, ExoRevisarImagen, ExoCorregirPrompt]
