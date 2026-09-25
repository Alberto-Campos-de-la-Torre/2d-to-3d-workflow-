# Flujo de trabajo - Exo filaments

## 0. Todo dentro de ComfyUI (via recomendada)

Arranca con `Iniciar_ComfyUI_3D.bat` y abre el flujo **"Exo - imagen a pieza imprimible"**
desde la barra lateral (icono de Workflows). Hace el recorrido completo: imagen -> recorte
de fondo -> geometria -> color -> paleta de filamentos -> informe -> STL y OBJ.

Solo hay que cargar la imagen en el nodo *Load Image* y pulsar Run.

Nodos propios (categoria `3d/exo filaments`):

| Nodo | Que hace |
|---|---|
| **Solidificar malla (Exo)** | Convierte la superficie en un solido cerrado: la lleva a una rejilla, cierra las grietas subiendo solo lo que haga falta, rellena el interior y reconstruye. Sustituye al `Remesh Mesh` nativo, que **no cierra** (con "udf" deja una cascara hueca y con "sdf" empeora los agujeros). Probado en 6 piezas: 0 agujeros en todas, 4-9 s. |
| **Paleta de filamentos (Exo)** | Reduce el color a los filamentos cargados. Con `paleta` vacia los elige solo. Absorbe manchas y alisa bordes. Muestra el reparto por filamento. |
| **Informe de impresion (Exo)** | Escala a mm y da medidas, volumen, peso estimado y si la malla esta cerrada. Si esta abierta **no da peso**: avisa de que hay que repararla. |
| **Revisar grosor de pared (Exo)** | Lanza rayos hacia dentro desde la superficie: avisa del %% de superficie por debajo del grosor minimo. Ponlo despues del informe (que es quien escala a mm). |
| **Guardar para imprimir (Exo)** | Escribe el STL y el OBJ+MTL con color en `output\exo\`. |

**Panel "Bobinas"** (barra lateral, icono de paleta): el inventario de filamentos. Marca
los que tengas cargados y pulsa *Aplicar al nodo*: escribe la paleta en el nodo sin que
tengas que escribir hex a mano. Se guarda en el navegador.

**Estudio Qwen** (barra lateral, icono de imagenes, o `http://127.0.0.1:8188/exo/estudio`):
texto -> imagen y edicion de imagen con Qwen-Image 2.1 (GGUF Q8_0 sin filtro de contenido,
codificador qwen3vl int8). ~25 s por imagen de 1 MP, ~35-40 s la primera o con referencia.
- *Pensada para pasar a 3D* anade al prompt: objeto entero, centrado, fondo liso.
- *Imagen de referencia* = modo edicion ("cambia el color a rojo, manten la forma").
- Galeria con veredicto (B buena / X descartar), estrellas 1-5, notas, filtros y
  comparacion lado a lado (Mayus+clic en dos imagenes). Las revisiones se guardan en
  `ComfyUI\user\default\exo_estudio\revisiones.json`; las imagenes en `output\qwen21\`.
- *Enviar a 3D* copia la imagen a `input\` para elegirla en el *Load Image* del flujo de pieza.
- El mismo grafo esta en el flujo **"Exo - Qwen-Image 2.1 (GGUF)"** (`scripts\crear_flujo_qwen.py`).
- **Licencia: Qwen Research License = solo uso NO comercial** (investigacion/evaluacion).
  Para usarlo en pedidos de clientes hace falta licencia comercial aparte
  (model-business@notice.qwencloud.com). FLUX.2 Klein 4B (Apache 2.0) si es comercial.

Los scripts de las secciones siguientes siguen sirviendo para trabajar en lote desde la
linea de comandos, y `preparar_impresion.py` sigue siendo la reparacion mas completa
(remallado por voxeles y control de grosor de pared).


ComfyUI debe estar arrancado: `D:\AI3D\Iniciar_ComfyUI_3D.bat` (solo accesible desde este PC).
Abreviatura usada abajo: `PY` = `D:\AI3D\ComfyUI_windows_portable\python_embeded\python.exe`

## 1. Modelo sin color (produccion normal)

    PY D:\AI3D\scripts\generar_3d.py <imagen o carpeta>

Usa Hunyuan3D 2.0 y quita el fondo automaticamente (obligatorio: sin eso el fondo, la
mesa o la sombra se convierten en geometria). Unos 30 s por pieza.
Si el resultado no convence: `--motor hy2.1` (segunda opinion, 30 s mas).

## 2. Modelo con color (vista previa para el cliente y/o multicolor)

    PY D:\AI3D\scripts\generar_3d.py <imagen> --motor trellis2 --texturas

Tarda de 3 a 8 minutos. Genera tres archivos en `output\3d\trellis2\`:

| Archivo | Para que sirve |
|---|---|
| `<nombre>_00001_.glb` | malla en bruto (decenas de millones de caras, poco util) |
| `<nombre>_textura_00001.glb` | **vista previa a color** para mandar al cliente |
| `<nombre>_vertices_00001.glb` | color por vertice: entrada del paso 3 |

Los dos ultimos vienen ya remallados y decimados a 700k caras. Ese paso deja la malla
mucho mas limpia: el cubo de Rubik paso de miles de aristas abiertas a **28**.

## 3. Separar colores para impresion multicolor (AMS)

    PY D:\AI3D\scripts\colores_a_piezas.py <modelo_vertices.glb> --paleta "#c41e3a,#ffd500,#0046ad,#1a1a1a" --altura-mm 60

**Usar siempre `--paleta` con los colores reales de tus bobinas**: el color que genera la
IA sale mas apagado que la foto original, y asi cada grupo se asigna al filamento que de
verdad tienes. Sin paleta, `--colores 4` agrupa solo y devuelve los colores que encuentre.

El agrupamiento es perceptual (Lab) con el brillo rebajado, para no separar luz y sombra
del mismo color. `--colores` es un maximo, no un objetivo: los grupos casi identicos o
muy pequenos se funden, asi que una manzana roja sale en 2 piezas aunque pidas 3.

Ajustes si hace falta:
- `--min-porcentaje 0.5` para conservar detalles pequenos (un logo blanco, por ejemplo;
  con el valor por defecto de 2 se funde con el color dominante).
- `--peso-luz 0.5` si quieres que separe tambien por claridad (util para degradados).

Escribe tres cosas:

1. **`<nombre>_color.obj` + `.mtl`** (via recomendada): lleva el color en los vertices y
   ademas los grupos de material. Creality Print 6.3, Bambu Studio y Orca abren con el
   un dialogo para emparejar cada color del modelo con un filamento cargado, sin trocear
   el modelo. **Copiar siempre el .obj y el .mtl juntos.**
2. Un **STL por color**, como alternativa si esa version del laminador no lo admite:
   importarlos a la vez y cargarlos como un solo objeto con varias piezas.
3. Un `colores.json` con el hex y el porcentaje de superficie de cada color.

En Bambu Studio / Orca Slicer:
1. Importar todos los STL a la vez y responder **si** a "cargar como un solo objeto".
2. Asignar a cada pieza el filamento de su color (el hex esta en `colores.json`).
3. Revisar que las piezas encajen y laminar.

## 4. Dejar la malla lista para imprimir

    "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe" -b -P D:\AI3D\scripts\preparar_impresion.py -- <modelo.glb> --altura-mm 90

Hace, en este orden: descartar trozos sueltos, cerrar agujeros, remallar por voxeles
(lo que convierte la superficie en un solido cerrado), decimar, escalar a milimetros y,
si se pide, cortar una base plana con `--base-plana 2`.

Escribe el STL y un informe JSON con:

- si la malla quedo **cerrada** (si no lo esta, no imprimir: el laminador rellena mal),
- medidas en mm, volumen y area,
- **grosor minimo y % de zonas finas** por debajo de `--grosor-min` (1,2 mm por defecto),
- **peso estimado en gramos** con el relleno indicado (`--relleno 15`), para presupuestar.

Ejemplo real (camara-tarta desde Hunyuan 2.0): cerrada, 90 x 61,8 x 84,8 mm, 259 cm3,
grosor minimo 4,62 mm, 0% de zonas finas, 81 g de PLA al 15%.

### Multicolor: como llevarlo al CFS / AMS

`preparar_impresion.py` saca tambien un `.obj` + `.mtl` con el color, ya sobre la malla
reparada. **Regla de oro: generar el modelo con los colores que vas a tener cargados.**

    ... preparar_impresion.py -- <modelo.glb> --altura-mm 60 --paleta "#1a1a1a,#f2f2f2,#c8bda0,#ffd500"

En Creality Print 6.3, al importar el OBJ sale el dialogo "Obj file Import color":

1. Pulsar **Color match** en Quick set **antes** de aceptar. Si no, el programa anade los
   colores como filamentos nuevos (5, 6, 7, 8...), la maquina no los tiene y el pintado
   no se aplica.
2. Revisar el emparejamiento y aceptar.

Opciones de limpieza del color (van por defecto, se desactivan con 0):

- `--min-mancha 0.3`: absorbe manchas de color que ocupen menos de ese % de las caras.
  Son sombras de la foto original que se colaron como color: en el cubo de Rubik quitaba
  manchas negras en mitad de las caras azules (7.607 caras reasignadas).
- `--suavizar-color 3`: alisa los bordes dentados entre colores.

## 5. Control de calidad de una malla

    "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe" -b -P D:\AI3D\scripts\revisar_glb.py -- <archivo.glb> <carpeta_salida>
    PY D:\AI3D\scripts\hoja_contacto.py <carpeta_salida> frente

Da caras, vertices, aristas abiertas, piezas sueltas y volumen, mas dos renders. Si el
GLB trae color por vertice, los renders salen a color.

**Una malla por ejecucion.** Con archivos de mas de 500 MB no lanzar varios a la vez:
son mallas de hasta 127 millones de caras.

## Que NO aceptar por generacion automatica

- Flores y estructuras ramificadas (fallan en los tres motores).
- Objetos casi planos: botones, placas, llaveros finos.
- Piezas con medidas exactas -> eso va a CAD, no a generacion.
