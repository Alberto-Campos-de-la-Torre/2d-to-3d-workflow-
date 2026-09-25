# Tutorial: de una idea a una pieza impresa

Guia de taller. Para los comandos sueltos y las opciones finas, ver `FLUJO.md`.

Arrancar siempre con **`D:\AI3D\Iniciar_ComfyUI_3D.bat`** y abrir `http://127.0.0.1:8188`.

---

## Camino A: el cliente manda una foto

Es el camino normal del negocio, y el unico que puedes cobrar sin mirar licencias.

### 1. Prepara la imagen

Lo que decide el resultado no son los ajustes, es la foto. De las pruebas:

**Funciona bien**
- Un solo objeto, entero y visible.
- Vista de tres cuartos (ni de frente plano ni desde arriba).
- Luz pareja, sin sombras duras ni reflejos fuertes.
- Objetos macizos: figuras, mascotas, bustos, objetos decorativos.

**Da problemas**
- Fotos de banco de imagenes con marca de agua: **la marca sale como geometria**.
- Vidrio, agua, cosas transparentes: la licorera fallo en forma y en color.
- Dibujos e ilustraciones planas: la geometria sale, el color sale sucio.
- Flores y estructuras muy ramificadas: salen imprimibles, pero se parecen poco.
- Objetos casi planos (botones, placas, llaveros finos): mejor hacerlos en CAD.

No hace falta recortar el fondo a mano: el flujo lo hace con BiRefNet. Pero si el fondo
es oscuro o muy cargado, recortar antes mejora el resultado.

### 2. Carga la imagen y ejecuta

1. Barra lateral -> **Workflows** -> **"Exo - imagen a pieza imprimible"**.
2. En el nodo **Load Image**, pulsa *choose file to upload* y elige la foto.
3. En **Informe de impresion (Exo)**, pon la **altura_mm** que quieres que tenga la pieza.
4. Si va a ser multicolor, abre el panel **Bobinas** (icono de paleta), marca los
   filamentos que tengas cargados y pulsa *Aplicar al nodo*.
5. **Run**.

Tarda entre 1 y 8 minutos segun la complejidad de la pieza.

### 3. Lee los cuatro informes antes de imprimir

Los nodos muestran su resultado en el propio grafo:

| Nodo | Que mirar |
|---|---|
| **Solidificar malla** | `agujeros` tiene que ser **0**. Si no, sube `cerrar_grietas`. |
| **Paleta de filamentos** | Cuantos colores y que porcentaje ocupa cada uno. |
| **Informe de impresion** | `malla cerrada`, medidas, y el **peso en gramos**: ese es tu presupuesto. |
| **Revisar grosor de pared** | `zonas finas` por debajo del 5% esta bien. Por encima, la pieza tendra partes fragiles: sube la altura o avisa al cliente. |

### 4. Lleva los archivos al laminador

Quedan en `output\final\` (o donde diga el nodo *Guardar para imprimir*):

- **`.stl`** para impresion de un solo color.
- **`.obj` + `.mtl`** para multicolor. **Los dos archivos van juntos.**

En Creality Print 6.3, al importar el OBJ sale el dialogo *Obj file Import color*:
pulsa **Color match** antes de aceptar. Si no lo haces, anade los colores como filamentos
5, 6, 7, 8... que la maquina no tiene, y el pintado no se aplica.

### 5. Antes de cobrar

Mira la pieza en el laminador. El sistema garantiza que **se puede imprimir**, no que
**se parezca** a lo que pidio el cliente. Ese juicio es tuyo, y es justo lo que se cobra
como retoque.

---

## Camino B: de un texto, sin foto

Flujo **"Exo - texto a pieza (Qwen)"**. Escribes una descripcion y sale el STL, sin tocar
nada intermedio: el generador de imagen entrega la imagen directamente al 3D.

> **Licencia: Qwen-Image 2.1 es de uso NO comercial** (Qwen Research License). Vale para
> tus propias piezas, catalogo, pruebas y muestras. Para un pedido de pago, la imagen
> tiene que venir del cliente o de FLUX.2 Klein (Apache 2.0).

### Que escriba el prompt tu IA local

El nodo **Prompt con IA (Exo)** convierte una idea corta ("un zorro sentado, figura de
resina") en un prompt completo con las reglas que necesita la conversion a 3D. Va delante
del generador de imagen y tarda un par de segundos.

- **modo `3d`**: obliga a objeto entero, centrado, fondo liso, luz pareja, y evita formas
  imposibles de imprimir (telas al viento, humo, pelo suelto, transparencias).
- **modo `imagen`**: solo amplia la idea, sin restricciones, para cuando la imagen es el
  producto final.
- **semilla**: cambiala para obtener otra redaccion de la misma idea.

Desde la linea de comandos va activado por defecto:

    PY scripts\texto_a_pieza.py "un zorro sentado, figura de resina" --altura 75
    PY scripts\prompt_ia.py "un buho de ceramica"            # solo ver el prompt
    PY scripts\prompt_ia.py "cartel retro de cafe" --modo imagen

Con `--sin-ia` se salta la IA y solo anade las indicaciones de encuadre; con `--tal-cual`
se usa el texto exactamente como lo escribiste.

**Configuracion**: la direccion del servidor va en `config_local.json` (en la raiz, junto
al .bat), o en la variable de entorno `EXO_IA_URL`. Ese archivo no se publica. Ejemplo:

    {
      "ia_url": "http://LA-IP-DE-TU-SERVIDOR:8080/v1",
      "ia_modelo": "",
      "ia_temperatura": 0.8
    }

Sirve cualquier servidor con API compatible con OpenAI: llama.cpp, LM Studio, Ollama,
vLLM. Si `ia_modelo` esta vacio, usa el primero que sirva el servidor. **Si la IA no
responde, el flujo sigue con la idea tal cual y lo avisa**: no se queda parado.

### Generar hasta que salga bien (revisa y se corrige solo)

El boton **"Generar hasta que salga bien"** genera, **mira la imagen** con tu IA local y, si
encuentra defectos, reescribe el prompt y vuelve a intentarlo. Debajo aparece la tira de
intentos con la puntuacion y lo que fallaba en cada uno; al pulsar una miniatura se recupera
el prompt que la genero.

Que busca:

| Familia | Que detecta |
|---|---|
| Encuadre y material | objeto recortado, varios objetos, fondo sucio, sombras duras, marca de agua, partes finas, vidrio o transparencias |
| Anatomia (solo en figuras, animales y personajes) | extremidades de mas, partes fusionadas, manos mal resueltas, asimetrias y proporciones imposibles |

Como corrige: anade instrucciones al prompt segun el defecto, refuerza el prompt negativo y
**cambia la semilla** (lo que mas arregla los fallos de anatomia). Con partes finas o manos
sube los pasos de 20 a 28. El `cfg` no lo toca: este modelo va destilado a 1,0.

Se detiene al primer intento sin defectos, o cuando agota los intentos. **Devuelve el mejor,
no el ultimo**, porque a veces el siguiente sale peor.

**Que NO hace**: no arregla lo que es imposible. Con un girasol de petalos finos corrigio el
encuadre (de 5/10 a 8/10) pero las partes finas siguieron ahi en los tres intentos: un
girasol es fino por naturaleza. Cuando un defecto se repite en todos los intentos, la
respuesta suele ser cambiar de tema, no insistir.

Tambien esta como nodos —**Revisar imagen (Exo)** y **Corregir prompt (Exo)**— para montarlo
en un grafo propio. Un pase por ejecucion, sin bucle.

**Limite conocido**: caza los defectos evidentes, no todos. En pruebas detecto una cabeza
duplicada, pero no vio una franja de brazo repetida mas sutil. Es una red de seguridad, no
un control de calidad: la ultima revision sigue siendo tuya.

### Como escribir el prompt a mano

El generador crea imagenes bonitas; nosotros necesitamos imagenes **utiles para 3D**. La
diferencia esta en cuatro cosas, que el flujo ya anade solas cuando usas el script:

    single complete object, centered, plain neutral background, soft even lighting, no text

Ejemplos que funcionan:

| Idea | Prompt |
|---|---|
| Figura | `small vinyl-toy style dragon figurine sitting` |
| Mascota | `ceramic figurine of a sitting corgi, smooth surfaces` |
| Objeto | `vintage brass desk lamp, single object` |
| Busto | `stylized bust of an astronaut, clean shapes` |

Evita: escenas ("un dragon sobre una montana"), varios objetos, primeros planos que
recorten la pieza, y estilos planos tipo ilustracion.

### Desde la interfaz

1. **Workflows** -> **"Exo - texto a pieza (Qwen)"**.
2. Escribe la descripcion en el nodo **TextEncodeQwenImage21** (campo `prompt`).
3. Ajusta `altura_mm` y, si toca, la paleta.
4. **Run**. Unos 25 s de imagen mas el tiempo de la pieza.

La imagen queda guardada en `output\qwen21\`, asi que si te gusta la figura pero quieres
otro tamano, puedes repetir solo la parte 3D con esa imagen.

### Desde la linea de comandos

    PY D:\AI3D\scripts\texto_a_pieza.py "un buho estilizado sentado, figura de ceramica" --altura 70

Opciones: `--semilla` (otra variante de la misma idea), `--paleta` (colores de tus
bobinas), `--tal-cual` (no anadir las indicaciones de encuadre).

`PY` = `D:\AI3D\ComfyUI_windows_portable\python_embeded\python.exe`

---

## Si algo sale mal

| Sintoma | Que hacer |
|---|---|
| La pieza sale con el fondo pegado | La imagen tenia fondo cargado: recortalo antes. |
| `agujeros` distinto de 0 | Sube `cerrar_grietas` a 2 o 3 en *Solidificar malla*. |
| Muchas `zonas finas` | Sube `altura_mm`: el grosor crece con el tamano de la pieza. |
| Sin peso en el informe | La malla llego abierta; revisa que *Solidificar* este antes. |
| Se queda sin memoria al hornear textura | Baja el tamano de textura a 1024 px. |
| Los colores no se aplican en Creality | Olvidaste **Color match** al importar el OBJ. |
| El archivo pesa 33 MB | Normal: son 700.000 caras. Se puede bajar sin perder calidad de impresion. |
| La pieza sale escalonada, como con curvas de nivel | Son los escalones de la rejilla. Sube **`suavizar_forma`** en *Solidificar malla* (5 por defecto; hasta 8). Es lo que mas se nota y no cuesta tiempo. Solo si se pierde detalle fino, sube tambien `resolucion`. |
| Se pierde detalle pequeno | Sube **`resolucion`**. El escalon mide `altura_mm / resolucion`, asi que la regla es `resolucion = altura_mm x 4`: 80 mm -> 320, 150 mm -> 600. Cuesta tiempo y caras: de 320 a 640 el archivo se cuadruplica. |
| Un cubo o una caja salen con las aristas redondeadas | Demasiado suavizado: baja `suavizar_forma` a 2. |
| La pieza entra tumbada en el laminador | El STL ya sale de pie (opcion `poner_de_pie` del nodo de guardado). Si viene de una tanda antigua: `PY scripts\poner_de_pie.py <carpeta>`. El OBJ se deja como esta a proposito: lleva su propia convencion de ejes y el laminador lo endereza solo. |

## Lo que NO acepta el sistema

Rechaza estos encargos o cotizalos como modelado manual, no como generacion:

- Piezas con medidas exactas (encajes, roscas, soportes): eso es CAD.
- Objetos de vidrio o transparentes.
- Ilustraciones planas, si el cliente espera color fiel.
- Cualquier cosa con marca registrada: el riesgo legal es tuyo.
