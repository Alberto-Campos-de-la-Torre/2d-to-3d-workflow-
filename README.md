# 2D a 3D: de una foto a una pieza imprimible

Flujo completo y local para convertir una imagen (o un texto) en un STL listo para
imprimir, montado sobre [ComfyUI](https://github.com/comfyanonymous/ComfyUI). Sin servicios
de pago y sin subir nada a la nube.

Lo que aporta este repositorio sobre los flujos que ya trae ComfyUI:

- **Nodos propios** que resuelven lo que faltaba para pasar de "malla bonita" a "pieza
  imprimible": cerrado solido, reduccion de color a los filamentos cargados, informe de
  peso y medidas, y revision del grosor de pared.
- **Flujos listos** para los tres casos: foto del cliente, texto, y solo imagen.
- **Guia de taller** (`TUTORIAL.md`) con lo que funciona y lo que no, medido sobre piezas
  reales.

## Resultado medido

10 imagenes de prueba (objetos, figuras, organicos), de punta a punta y sin retoque manual:

| | Resultado |
|---|---|
| Piezas cerradas (imprimibles) | **10 de 10** · 0 agujeros |
| Zonas por debajo del grosor minimo | 0 a 1,4 % de la superficie |
| Tiempo por pieza (con color) | 48 s a 453 s |
| Equipo | RTX 5070 Ti 16 GB · Ryzen 7 9700X · 32 GB RAM |

## Los nodos

Categoria `3d/exo filaments` dentro de ComfyUI:

| Nodo | Que hace |
|---|---|
| **Solidificar malla** | Convierte la superficie en un solido cerrado: rasteriza a una rejilla de voxeles, cierra las grietas subiendo la dilatacion sola hasta que el relleno prende, rellena el interior y reconstruye. Sustituye al `Remesh Mesh` nativo, que **no cierra** las mallas. |
| **Paleta de filamentos** | Reduce el color del modelo a los filamentos que hay cargados. Agrupa en espacio perceptual (CIELab con la luminosidad rebajada) para separar colores y no luces y sombras. Absorbe manchas y alisa los bordes. |
| **Informe de impresion** | Escala a milimetros y calcula medidas, volumen, estanqueidad y **peso estimado**. Si la malla llega abierta no da peso: avisa. |
| **Revisar grosor de pared** | Lanza rayos hacia dentro desde la superficie y mide que porcentaje esta por debajo del grosor minimo. |
| **Guardar para imprimir** | Escribe el STL (ya de pie, eje Z arriba) y el OBJ+MTL con color para impresion multicolor. |

Ademas, un panel lateral **"Bobinas"** con el inventario de filamentos, que escribe la
paleta en el nodo sin tener que teclear codigos hexadecimales.

## Instalacion rapida

1. ComfyUI portable para Windows con NVIDIA (probado en 0.36-0.37).
2. Copiar `custom_nodes/exo_filaments/` dentro de `ComfyUI/custom_nodes/`.
3. Copiar `workflows/*.json` en `ComfyUI/user/default/workflows/`.
4. Descargar los modelos: ver **`REQUISITOS.md`** (`scripts/descargar_modelos.ps1` lo hace
   con verificacion de checksum y reanudacion).
5. Arrancar con `Iniciar_ComfyUI_3D.bat` y abrir el flujo desde la barra lateral.

> **Las rutas estan fijadas a `D:\AI3D`** en los scripts y el .bat. Si instalas en otro
> sitio, busca y reemplaza esa ruta. Los nodos de ComfyUI no dependen de ella.

## Uso

Guia completa en **`TUTORIAL.md`**; comandos y opciones finas en **`FLUJO.md`**.

    # de una imagen
    python scripts/generar_3d.py <imagen>

    # de un texto, hasta el STL
    python scripts/texto_a_pieza.py "un buho estilizado sentado, figura de ceramica" --altura 70

(`python` = el interprete embebido de ComfyUI: `ComfyUI_windows_portable\python_embeded\python.exe`)

## Licencias de los modelos

El codigo de este repositorio es libre, pero **los modelos que usa no todos lo son**:

| Modelo | Licencia | Uso comercial |
|---|---|---|
| TRELLIS.2 | MIT | Si |
| Hunyuan3D 2.0 / 2.1 | Tencent Hunyuan Community | Si, **salvo en UE, Reino Unido y Corea del Sur** |
| BiRefNet | MIT | Si |
| FLUX.2 Klein 4B | Apache 2.0 | Si |
| Qwen-Image 2.1 | Qwen Research | **No**: solo investigacion y evaluacion |

El flujo de texto a pieza usa Qwen, asi que **no sirve para pedidos de pago** tal cual.
Para eso, la imagen debe venir del cliente o generarse con FLUX.2 Klein.

## Lo que este sistema no resuelve

Garantiza que la pieza **se puede imprimir**, no que **se parezca** a lo que se pidio. Esa
revision sigue siendo humana. Y hay casos que conviene rechazar de entrada: piezas con
medidas exactas (eso es CAD), objetos de vidrio, ilustraciones planas si se espera color
fiel, y cualquier cosa con marca registrada.
