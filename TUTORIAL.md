> Instalacion modular: consulta primero [README.md](README.md) y elige perfil 2D,
> 3D o ambos con `instalar.py`. Las rutas fijas y el copiado manual que aparecen
> mas abajo corresponden al montaje anterior, conservado como referencia de taller.

# Tutorial: de una idea a una pieza impresa

Guia de taller. Para los comandos sueltos y las opciones finas, ver `FLUJO.md`.

Arrancar siempre con **`D:\AI3D\Iniciar_ComfyUI_3D.bat`** y abrir `http://localhost:8188`.

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
| **Revisar pieza terminada** | La unica revision que mira la PIEZA y no los numeros. Da las cuatro vistas renderizadas, si se parece a lo pedido, y **cuanto llena de su caja**. |

#### Como se mide el volumen (y por que importa al cobrar)

El volumen se sacaba con la formula del teorema de la divergencia, que es exacta **si** la
superficie esta cerrada y todas las caras miran hacia el mismo lado. Lo segundo no siempre
se cumple despues de solidificar y decimar, y cuando falla no falla poco: en el dragon de
prueba daba **22,1 cm3 cuando el solido real son 98,5**, y el peso salia en 27,4 g en vez de
56,3. Cobrando por gramos, eso es la mitad de lo que toca.

Ahora se mide de las dos formas y se contrastan. Si la firmada se queda muy por debajo, es
que la superficie no esta bien orientada y se usa una medida por voxeles, que no depende de
la orientacion; el informe lo dice cuando pasa. Validado contra cubo, esfera y cilindro, con
las caras bien y con la mitad invertidas a proposito: con la malla buena el error es del
0,2 %, y con la malla rota —donde la formula firmada da **cero**— la de voxeles queda entre
el 2 % y el 4 %, siempre por arriba, que para calcular material es el lado seguro. La prueba
esta en `scripts\pruebas\probar_volumen.py`.

#### El dato del llenado, que es el que mas sorprende

`llena X de su caja` compara el volumen de la pieza con el de la caja que la envuelve.
Por debajo de **0,10** es una cascara hueca: se imprimira como un papel aunque todos los
demas controles esten en verde. Ejemplos medidos:

| Pieza | Llenado | Lectura |
|---|---|---|
| Zorro | 0,23 | maciza, normal |
| Camara-tarta | 0,52 | maciza |
| Conejo | 0,07 | **cascara hueca** |
| Girasol | 0,05 | **cascara hueca** |

Ni el informe de impresion ni el grosor de pared lo detectaban, y en el render tampoco se
ve: una cascara y un macizo se dibujan igual. Si sale hueca, sube `cerrar_grietas` en
*Solidificar malla* o acepta que esa figura no tiene interior (pasa con esculturas caladas).

**Lo que este control NO garantiza**: juzga el parecido, y con piezas abstractas o muy
estilizadas se equivoca. Con el conejo llego a decir "no reconocible como conejo" cuando
las orejas y la postura se ven perfectamente. Ademas varia algo entre ejecuciones. Tomalo
como una alerta para mirar tu, no como un veredicto.

### 4. Lleva los archivos al laminador

Quedan en `output\final\` (o donde diga el nodo *Guardar para imprimir*):

- **`.stl`** para impresion de un solo color.
- **`.obj` + `.mtl`** para multicolor. **Los dos archivos van juntos.**

En Creality Print 6.3, al importar el OBJ sale el dialogo *Obj file Import color*:
asigna cada material a una plaza distinta del CFS (1 a 4). **Color match** puede
asignar varios colores a una misma bobina; revisa el mapa antes de aceptar.
Conserva el MTL junto al OBJ y verifica el pintado en la vista laminada.

### 5. Antes de cobrar

Mira la pieza en el laminador. Las comprobaciones del sistema ayudan a detectar defectos; confirma
soportes, paredes, estabilidad y resultado en el laminador y con una prueba fisica. Ese juicio es tuyo, y es justo lo que se cobra
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

**En el Estudio, el interruptor es la casilla "Esta imagen se va a imprimir en 3D"**, y es
la que mas cambia el resultado, asi que conviene marcarla antes de empezar. No decide solo
como se escribe el prompt: manda sobre las tres etapas.

| | Casilla marcada (para imprimir) | Casilla sin marcar (imagen normal) |
|---|---|---|
| La IA escribe el prompt | con las reglas de la conversion: un objeto entero, centrado, tres cuartos, fondo liso, nada de humo ni telas al viento | amplia la idea libremente, con la composicion y el estilo que pidas |
| Al generar | anade esas mismas condiciones al final del prompt | no anade nada |
| La revision | exige que la pieza se pueda imprimir: partes finas, cristales, varios objetos y fondos con escenario cuentan como defecto | solo busca los fallos de cualquier imagen: anatomia, recortes, marcas de agua, encuadre |
| El corrector | mete "thick solid forms", "opaque matte material", "one single object"… | no toca el material ni la composicion |

El mismo girasol, revisado de las dos maneras: **8/10 y no apto** para imprimir por los
petalos finos, **10/10 y apto** como imagen, con los petalos anotados como observacion en
vez de como defecto. Y una escultura de cristal, corrigiendola en modo 3D, acaba pidiendo
material opaco; en modo imagen sigue siendo de cristal, que es lo que se pidio.

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

### Referencias: una o dos imagenes

El Estudio admite **dos imagenes de referencia**. Probado con una bateria de 10 casos, de
la que salen dos reglas que conviene respetar:

**Regla 1: el objeto sale siempre de la referencia 1.** No se puede pedir que el sujeto
venga de la segunda. Con una llave en el hueco 1 y un cubo de Rubik en el 2, pedir "el
objeto de la SEGUNDA imagen en plateado" devolvio la llave plateada, no el cubo. La
referencia 2 sirve para aportar color, patron, fondo o un segundo objeto.

**Regla 2: nombra el atributo, no la imagen.** "Con los colores de la segunda imagen"
funciona solo si esos colores son vivos y evidentes; con una camara negra no hizo nada. La
misma pareja, pidiendo "matte black and dark grey like the camera", dio una manzana negra
perfecta. Di el color o el patron con palabras.

Lo que funciona bien (7 de 8 casos utiles):

| Que quieres | Como pedirlo | Resultado medido |
|---|---|---|
| Objeto de 1 con color de 2 | "the camera, painted in the red and green colors of the apple" | camara mitad roja mitad verde |
| Objeto de 1 con patron de 2 | "the key covered with the colorful square pattern of the second image" | llave con cuadros de Rubik |
| Objeto de 1 sobre fondo de 2 | "the button placed on top of the flower from the second image" | boton en el centro del girasol |
| Los dos objetos juntos | "both objects together side by side" | camara y manzana, fieles las dos |
| Color concreto de 2 | "the key, but bright yellow like the flower" | llave amarilla |

**Regla 3: la referencia 2 no puede prestar una pose, una accion ni una escena.** Esta se
midio aparte, con 22 imagenes (`scripts\pruebas\probar_condiciones.py`), y es la que mas
caro sale si no se sabe. Con un dragon de plastico en el hueco 1 y una figura de anime en
el 2, pedir "el dragon con la pose de la chica" devolvio **a la chica**, sentada encima del
dragon, que quedo de asiento. Paso en las cuatro formas de pedirlo, y tambien poniendo
"girl, woman, human, person" en el prompt negativo. Con dos objetos no hay secuestro pero
tampoco transferencia: el dragon y el flexo salieron **fusionados** en una sola pieza.

Lo que si funciona es **describir la condicion con palabras y quitar la referencia 2**:

| Como se pide | Pose | Actividad | Sustitucion |
|---|---|---|---|
| Citando la segunda imagen | mal | mal | mal |
| En palabras, con la referencia 2 puesta | mal | bien | bien |
| En palabras, **sin** la referencia 2 | **bien** | **bien** | **bien** |

Sin la referencia 2 salieron los tres a la primera y **en la mitad de tiempo** (41 s frente
a 86 s), porque solo hay que codificar una imagen. La expresion de la cara es la excepcion:
esa si se transfiere citando la segunda imagen, porque una cara no compite por ser el
sujeto. El dragon copio la sonrisa y los ojos grandes sin dejar de ser el dragon.

En resumen: **la referencia 2 presta atributos sin cuerpo** —color, patron, material,
acabado, estilo, fondo, expresion, o un segundo objeto que acompana—. Todo lo que lleve
cuerpo se escribe con palabras y se suelta la segunda imagen.

**El escritor de prompts ya conoce estas reglas.** Si pulsas "Escribir con IA" con
referencias cargadas, se le indican cuantas hay y **se le adjuntan las imagenes**, porque el
modelo es multimodal: asi describe lo que hay de verdad en la segunda en vez de inventarselo
(sin verlas escribia poses que no estaban ahi). Con una referencia describe el cambio ("turn
the key into a matte yellow figurine, keeping the same shape"); con dos, nombra el atributo;
y si le pides una pose, una accion o una sustitucion, la escribe con palabras, no cita la
segunda imagen y te avisa de que la quites. Tampoco arrastra lo que no pediste: si pides
solo la pose, no te trae ademas el libro y el pulpo que salian en la otra foto.

Y no pide lo contrario de lo que cambia. Escribia "painted in bright yellow ... keeping its
own colors", dos ordenes opuestas que dejaban el color a medias; ahora la frase que blinda
la identidad nombra solo lo que se queda igual.

El tamano de salida lo manda la referencia 1, asi que con referencias el selector de
formato se desactiva. Cada generacion con dos referencias tarda unos 90 s.

El nodo admite hasta 16 referencias; la interfaz expone dos porque es lo que se usa en el
taller. La bateria de pruebas esta en `scripts\pruebas\probar_dos_referencias.py`, con
las hojas comparativas en `pruebas\dos_referencias`.

### Decirle a la IA que falla (tu ojo manda sobre el suyo)

Debajo de cada imagen, en el visor, hay un cuadro: **"¿Que le falla a esta imagen?"**.
Escribes con tus palabras lo que has visto mal y pulsas **"Corregir el prompt con esto"**.
La IA **mira la imagen mientras lee tu comentario**, asi que puedes senalar sitios: "la mano
de la derecha", "el fondo de arriba", "el brazo de la nina de gris no se conecta a nadie".

Que hace con eso: enumera una por una las cosas que le dices, las busca en la imagen, y
reescribe el prompt y el negativo. Si lo que falla es anatomia —manos, dedos,
extremidades— **cambia la semilla**, porque no hay palabra que coloque unos dedos: hay que
volver a tirar. El prompt corregido aparece en el formulario, con "Deshacer" al lado.

Sirve en los dos modos:

- **Generar una vez**: corriges, miras el prompt, y vuelves a darle a Generar.
- **Generar hasta que salga bien**: lo que hayas escrito en el cuadro **se arrastra en todas
  las vueltas**, y pesa mas que lo que encuentre la revision automatica. Sin eso, la vuelta
  siguiente deshacia lo que pediste. En la tira de intentos se ve, en cada vuelta, que
  cambio por lo que dijiste tu.

Ejemplo real, de dos vueltas: "el brazo que pasa por encima del hombro de la nina de gris no
se conecta a ningun cuerpo, y el texto de la camiseta rosa son letras sin sentido". El
prompt paso a incluir "a plain solid pink t-shirt with no text or graphics" y describir el
brazo apoyado en el hombro. La segunda imagen salio con la camiseta lisa y el brazo
conectado.

**Lo importante: pideselo en afirmativo, y deja que ella lo traduzca.** El prompt negativo
**casi no funciona** con este modelo, que va destilado a cfg 1. Se comprobo pidiendo quitar
un platano por el negativo: el platano seguia ahi, con cfg 1 y con cfg 2,5. Por eso la IA
mete las correcciones en el prompt positivo ("a plain t-shirt with no writing on it" en vez
de un negativo "text") y usa el negativo solo como refuerzo. Si alguna vez te preguntas por
que poner algo en el negativo no cambio nada, esa es la razon.

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

**Como mira la anatomia cuando hay mas de una figura.** Preguntar por la imagen entera no
sirve con dos personas: "cuatro brazos" es lo normal con dos cuerpos y tambien es el
sintoma de que a uno le sobra uno, y el modelo resuelve la duda siempre a favor de "esta
bien". Con seis imagenes de dos personas, la version anterior dio **todo correcto en las
seis**, incluidas dos con fallos claros. Ahora la revision va en tres etapas:

1. **Cuenta las figuras** y las describe por lo que las distingue ("nina camiseta gris",
   "hombre camisa azul pantalon marino").
2. **Una pasada por figura**, sobre un recorte ampliado de cada una, mirando solo a esa y
   siguiendo cada brazo y cada pierna desde la mano o el pie hasta el hombro o la cadera.
   Ahi salen los miembros que no llegan a ningun cuerpo, que es el fallo tipico.
3. **Una pasada por la zona de contacto**, donde los cuerpos se tocan, que es donde
   aparecen las manos de nadie. Da un veredicto de tres niveles —limpio, sospechoso,
   fallo— y **solo "fallo" puntua**: lo sospechoso se anota como "a revisar a ojo". Sin ese
   nivel intermedio llamaba fallo a un apreton de manos bien hecho, que es solo dos manos
   tapandose.

El selector **"miradas"** al lado de los intentos es cuantas veces insiste en cada pregunta
cuando la imagen sale limpia. El modelo es inconstante: el mismo brazo mal conectado lo vio
en una pasada y no en la siguiente. Se para en cuanto encuentra algo, asi que insistir solo
cuesta tiempo en las imagenes que estan bien. Con dos figuras y 2 miradas, revisar tarda
unos 55 s; con una figura, unos 12 s.

**Lo que da de si, medido.** Sobre esas seis imagenes, con dos fallos reales comprobados a
ojo: la version anterior encontro **0 de 2**; esta encuentra **1 o 2 de 2** segun la
ejecucion, y de vez en cuando marca como defecto unas manos borrosas que no lo son. Hay
ruido real entre ejecuciones: el mismo codigo dio 5 de 6 y 4 de 6 en dos pasadas seguidas.
Se ha dejado inclinado a marcar de mas: corregir de mas cuesta una generacion, y corregir
de menos cuesta una impresion. Un fallo pequeno —una mano deforme que ocupa 60 pixeles en
una foto de dos cuerpos enteros— se le sigue escapando la mitad de las veces. **La revision
final sigue siendo tuya.**

Como corrige: anade instrucciones al prompt segun el defecto, refuerza el prompt negativo y
**cambia la semilla** (lo que mas arregla los fallos de anatomia). Con partes finas o manos
sube los pasos de 20 a 28. El `cfg` no lo toca: este modelo va destilado a 1,0.

Se detiene al primer intento sin defectos, o cuando agota los intentos. **Devuelve el mejor,
no el ultimo**, porque a veces el siguiente sale peor.

**Con referencias cargadas cambia de criterio**, y conviene saberlo: con dos referencias
deja de contar "varios objetos" como defecto, porque pedir las dos cosas juntas es un
encargo legitimo, y tampoco cuenta que el objeto salga pequeno o descentrado, que es
inevitable cuando caben dos cosas en el cuadro. No anade frases de fondo ni de luz, que
pelearian con la imagen de partida en vez de arreglar nada. Si el prompt no menciona la
segunda imagen, se la recuerda al corregir para no perder la combinacion; y si lo que pide
es una condicion —pose, gesto, accion, material, estilo—, en vez de repetir la formula del
atributo refuerza la identidad del objeto, para que no lo sustituya por el de la segunda.

**Y suelta la referencia 2 cuando estorba.** Si al corregir ve que el prompt pide una pose,
una accion o una sustitucion, quita la segunda referencia del grafo y sigue con la
condicion escrita en palabras, que es lo unico que funciona (regla 3, arriba). Lo deja
escrito en la tira de intentos, para que veas por que cambio.

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

## Usarlo desde el movil y desde otros equipos de la red

Hay dos lanzadores, y la diferencia importa:

| Archivo | Quien puede entrar |
|---|---|
| `Iniciar_ComfyUI_3D.bat` | solo este PC (localhost). Es el de siempre. |
| `Iniciar_ComfyUI_LAN.bat` | cualquier equipo de tu red local: moviles, tablets, otros PC. |

El de red escucha en todas las interfaces. Desde el movil, usa el nombre de red
del PC y el puerto configurado, seguido de `/exo/estudio` o `/exo/pieza`.

**Falta un paso que solo puedes dar tu**, porque necesita permisos de administrador: abrir
el puerto en el cortafuegos de Windows. Se hace una vez. En PowerShell **como
administrador**:

    New-NetFirewallRule -DisplayName "ComfyUI Exo (LAN)" -Direction Inbound `
      -Protocol TCP -LocalPort 8188 -Action Allow -Profile Private `
      -RemoteAddress LocalSubnet

`-Profile Private` lo deja fuera de las redes marcadas como publicas, y `-RemoteAddress
LocalSubnet` lo limita a tu propia red. Para quitarlo:
`Remove-NetFirewallRule -DisplayName "ComfyUI Exo (LAN)"`.

**Lo que hay que tener claro antes de abrirlo: ComfyUI no pide contrasena.** Quien alcance
ese puerto puede generar, ver todo lo que hayas generado, subir archivos y lanzar flujos que
leen y escriben en las carpetas de ComfyUI. En la red del taller o de casa es razonable; en
una wifi compartida o abriendo el puerto en el router, no. Cuando no lo necesites, vuelve al
lanzador de siempre.

**En el movil.** La interfaz se adapta sola por debajo de 560 px: los botones pasan a ancho
completo y con altura de dedo, la galeria a dos columnas, los atajos de teclado se ocultan y
el visor ocupa media pantalla con la ficha debajo. Al subir una referencia, el telefono
ofrece la camara o la galeria. Lo probado a 375x812: no hay desbordes ni scroll horizontal,
y se puede generar, revisar, puntuar y escribir observaciones igual que en el PC.

Las miniaturas de la galeria van comprimidas al vuelo (webp, calidad 70): **61 KB en vez de
1,5 MB**, con lo que abrir la galeria entera pasa de 88 MB a 3,5 MB. Por wifi es la
diferencia entre usable y no usable. El visor sigue mostrando el PNG completo, que es donde
se miran los dedos.

Lo que **no** cambia por estar en red: la GPU sigue siendo la de este PC, asi que generar
desde el movil tarda lo mismo y ocupa la misma cola. Dos personas generando a la vez se
turnan.

### De imagen a pieza, tambien desde el movil

`http://<la direccion>:8188/exo/pieza`, o el enlace **"Imagen → pieza 3D"** que hay en la
cabecera del Estudio. El grafo de ComfyUI no se maneja con el dedo —nodos diminutos, cables
y zoom—, asi que esta pagina hace el mismo flujo con cuatro controles:

1. **La imagen**: lo generado en el Estudio y lo que haya en `input/`. Se toca y se elige.
2. **Como se va a imprimir**: altura en mm, material, relleno, pared minima, y si lleva
   color. Con color se usan los filamentos que le digas y se reparten los colores de la
   pieza entre ellos, que es la base de la impresion multicolor.
3. **Convertir**. Tarda unos 5 minutos. Puedes cerrar el movil y volver: el trabajo sigue
   en el PC, lo unico que se pierde es el seguimiento en pantalla.
4. **El resultado**: las cuatro vistas de la pieza renderizadas, los cuatro informes
   (solidificacion, medidas y peso, grosor de paredes, revision de la pieza) y los botones
   para descargar el STL y el OBJ.

Es el mismo flujo medido de siempre, no una version reducida: solidifica, mide y revisa
igual. Lo que cambia es que cabe en una pantalla de telefono.

**Sin color tambien solidifica.** Si quitas el color se usa la misma cadena de limpieza
—solidificar, decimar, suavizar— por separado, porque la malla en bruto del generador no es
imprimible: sale como cascara hueca y con agujeros. En el dragon de prueba: 163.748 agujeros
de entrada, 0 de salida, solido cerrado.

---

## Antes de mandarla a la impresora

El informe de medidas dice que la malla esta cerrada y que las paredes dan el ancho. Eso no
basta: la pieza puede no caber, estar llena de voladizos o caerse sola. El nodo **Revisar
que se pueda imprimir (Exo)** mide las tres, con la pieza ya puesta como se va a imprimir, y
sale en la pagina del movil como **"Se puede imprimir"**.

| Dato | Que significa |
|---|---|
| `cabe` | Contra tu cama (350 x 350 x 350 por defecto, se cambia en la pagina). Si no cabe, dice a que altura habria que bajarla. Se supone que puedes girarla sobre la cama. |
| `voladizos` | Superficie que mira hacia abajo mas de 45 grados. No cuenta lo apoyado en la cama, que se imprime contra el cristal. Por encima del 5 % hara falta soporte; por encima del 15 %, soportes por toda la pieza. |
| `apoyo` | Cuantos mm2 tocan la cama y que parte de su sombra son. Poca huella = se despega o se cae. |
| `estabilidad` | A cuantos mm del borde de la huella cae el centro de masa. **Negativo significa que vuelca sola.** |

El angulo se puede subir si tu impresora refrigera bien. Validado contra formas de
respuesta conocida (`scripts\pruebas\probar_imprimibilidad.py`): una esfera da 15,0 % de
voladizo contra el 14,6 % que sale por geometria, y una torre inclinada sale con el centro
de masa 19,6 mm **fuera** de la huella.

El informe de grosor dice ahora **donde** estan las zonas finas, no solo cuantas: repartidas
en tres alturas y con el tramo en mm. No es lo mismo que esten en la peana, que se arregla
engordandola, que en la cara.

### Presupuesto

El nodo **Presupuesto (Exo)** convierte el peso en precio: material, maquina, preparacion,
mermas y margen. Los numeros de tu negocio van en `config_local.json`, que **no se publica**:

    "precio_filamento_kg": 25.0, "moneda": "USD", "coste_hora_maquina": 1.20,
    "gramos_por_hora": 14.0, "preparacion": 3.00, "margen": 1.6, "fallos_pct": 8.0

Mientras no los pongas, el presupuesto sale con los de ejemplo y **lo dice en el propio
informe**, para que no se cuele un precio inventado en una factura. `fallos_pct` es el
porcentaje de impresiones que se pierden: no es mala suerte, es un coste, y lo pagan las que
salen bien.

### Guardar el encargo

Al terminar una pieza, en la pagina del movil hay un cuadro para ponerle nombre al encargo.
Guarda el STL, el OBJ, las vistas, la imagen de partida y todos los informes en
`encargos\<fecha>-<nombre>`, que es lo que hace falta tener a mano cuando el cliente
pregunta tres semanas despues. Esa carpeta no se publica.

## Mantenimiento

**Limpiar las pruebas.** `scripts\limpiar.py` ensena que ocupan las salidas de prueba
agrupadas y, con `--borrar`, las quita. Por defecto **no borra nada**: hay que pedirselo. No
toca los modelos, ni `input\`, ni el repositorio, y respeta siempre los 5 archivos mas
recientes de cada grupo y todo lo de los ultimos 7 dias (`--conservar` y `--dias`).

    PY scripts\limpiar.py                  # solo mirar
    PY scripts\limpiar.py --borrar         # borrar de verdad
    PY scripts\limpiar.py --dias 30        # mas agresivo

**Que ComfyUI se levante solo.** `scripts\vigilante.py` comprueba cada minuto que el
servidor **responde**, no solo que el proceso existe: ya paso una vez que la consola entro
en modo seleccion, Windows congelo el proceso y el puerto seguia abierto con el servidor
muerto. Si no responde, mata lo que haya y arranca de nuevo, y lo apunta en
`vigilante_log.txt`.

    PY scripts\vigilante.py --lan          # vigilando, accesible en la red
    PY scripts\vigilante.py --una-vez      # comprobar y salir (para el Programador de tareas)

Para que arranque con el equipo, en el Programador de tareas de Windows: tarea nueva, al
iniciar sesion, que ejecute `python_embeded\python.exe` con `scripts\vigilante.py --lan`.

## Si algo sale mal

| Sintoma | Que hacer |
|---|---|
| La pieza sale con el fondo pegado | La imagen tenia fondo cargado: recortalo antes. |
| `agujeros` distinto de 0 | Sube `cerrar_grietas` a 2 o 3 en *Solidificar malla*. |
| Muchas `zonas finas` | Sube `altura_mm`: el grosor crece con el tamano de la pieza. |
| Sin peso en el informe | La malla llego abierta; revisa que *Solidificar* este antes. |
| Se queda sin memoria al hornear textura | Baja el tamano de textura a 1024 px. |
| Los colores no se aplican en Creality | Revisar MTL, mapa a las plazas 1 a 4 y topologia del OBJ. |
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


### Proteccion de presupuestos y archivos

Los presupuestos rechazan numeros no finitos, cantidades negativas y ritmo o multiplicador de precio cero. Los encargos tienen un identificador unico y conservan en `archivos/` las rutas relativas de OBJ, MTL y texturas; una dependencia ausente impide el archivado. La limpieza conserva conjuntos completos (incluidas dependencias compartidas), respeta `encargos/` y no sigue enlaces fuera de la carpeta. `--conservar` cuenta conjuntos. Pruebas: `python scripts/pruebas/probar_robustez.py`.


### Plan de impresion para K2 Plus + CFS (diagnostico)

En `/exo/pieza`, el bloque **Plan de impresion** compara entero multicolor, separado por color e hibrido. Configuracion inicial: K2 Plus, cama 350 x 350 x 350 mm, CFS con 4 filamentos y capa de 0.2 mm. Cambia la capacidad si hay mas unidades CFS. La version instalada de Creality Print sigue pendiente de confirmar.

Las nuevas conversiones incluyen el nodo `ExoPlanImpresion`, su informe y un JSON descargable que se conserva al guardar el encargo. Tambien puedes seleccionar un OBJ ya generado y pulsar **Analizar complejidad**, sin regenerarlo. Se procesa una malla a la vez; limite 800000 caras y 160 MB para OBJ.

El analisis mide superficie por color, conectividad y presencia de colores por intervalos de altura. La asignacion aproximada usa hasta 8 colores y la primera esquina de cada triangulo, como la exportacion OBJ actual. Una region de al menos 3 % de superficie y dos dimensiones de al menos 2 mm es candidata a *revisar*, no una pieza automaticamente separable: no mide su espesor ni reconoce cabeza, pelo o manos. No hace cortes, encajes o vista explosionada. Las regiones pequenas se mantienen como detalles a revisar. Los indicadores de capas NO son cambios reales de filamento ni garantizan ahorro. Purga, soportes, tiempo y precio quedan pendientes del perfil y del laminado real. TPU no se recomienda para alimentacion por CFS segun Creality.

Documentacion oficial consultada:
- [Pintado de regiones, relleno de huecos y laminado](https://www.creality.com/help/help-introduction-to-the-color-painting-feature)
- [K2 Plus + CFS: materiales compatibles](https://forum.creality.com/t/creality-k2-plus-cfs-frequently-asked-questions-you-should-know/21698)
- [Versiones de Creality Print y mejoras de purga](https://github.com/CrealityOfficial/CrealityPrint/releases)

Verificacion: `python scripts/pruebas/probar_plan_impresion.py` (10 casos sinteticos). Incluye colores por altura, coexistencia lateral, detalles, regiones desconectadas, limite de filamentos, TPU, dimensiones e inputs invalidos. La comparacion real de coste queda para integrar el laminador; esta etapa solo recomienda que estrategias evaluar.


### Separacion guiada por planos

En `/exo/pieza`, selecciona una pieza en **Plan de impresion**, pulsa **Ver plano sobre la pieza** y ajusta eje y posicion (1 a 99 % de la dimension correspondiente). La proyeccion muestra hasta 5000 vertices; es orientativa, no una seleccion anatomica ni un visor de solidos. **Generar dos piezas cerradas** usa Manifold en un proceso separado con limite de 120 segundos. Se conserva el original. No se hacen encajes ni se rellenan cavidades deliberadamente.

Solo se aceptan mallas triangulares cerradas manifold, de hasta 800000 caras y OBJ de hasta 160 MB. Los colores deben estar reducidos a 16 o menos. Se valida cierre y winding de las salidas y conservacion de volumen a 0.1 %. STL queda colocado sobre su cara de corte con coordenadas Z arriba; OBJ+MTL mantiene coordenadas de montaje Y arriba y paleta aproximada. `montaje.json` incluye transformaciones, dimensiones, componentes y advertencias. La carpeta completa se puede guardar como encargo y la limpieza la trata como un conjunto. Los componentes desconectados se reportan; dos mitades pueden contener mas de dos componentes fisicos. Debes laminar para verificar soportes, paredes, estabilidad, cama y montaje. Un corte global puede afectar varias partes del personaje.

La prueba descubrio que los cinco OBJ anteriores contienen aristas no manifold pese a no tener bordes abiertos (entre 58 y 822). El corte los rechaza: esos modelos necesitan una reparacion topologica adicional antes de poder separarlos. No se presentan como piezas listas para ensamblar.

Dependencias: `python -m pip install -r custom_nodes/exo_filaments/requirements.txt`. Pruebas: `python scripts/pruebas/probar_cortes.py`. Incluye 9 casos, con cavidad interna, winding incorrecto, componentes multiples, colores, volumen y proteccion frente a sobrescritura.

Referencias tecnicas: [Manifold SplitByPlane](https://manifoldcad.org/docs/html/classmanifold_1_1_manifold.html), [Trimesh: winding y normales](https://trimesh.org/trimesh.repair.html).


## Textura y exportacion CFS: control de fidelidad

La textura generada y la paleta de impresion son pasos independientes. La vista previa
conserva todo el color; OBJ/MTL exporta como maximo las plazas configuradas (4 por defecto).
La paleta escrita por el usuario prevalece; se rechaza si supera el numero de plazas.
La reduccion perceptual conserva la diferencia entre materiales claros y oscuros; no es
una segmentacion anatomica. STL no guarda colores. Importar OBJ junto a su MTL en Creality
Print y asignar los materiales a las bobinas del CFS; no se ha verificado este nuevo OBJ
en el laminador durante esta correccion.

En /exo/pieza se puede elegir una semilla de textura independiente de la geometria y
entre 12 y 40 pasos. El revisor recibe la imagen original junto con las cuatro vistas,
busca cambios graves de color y manchas, y si los detecta se reintenta solo la textura
hasta dos veces con otras semillas. La geometria y sus parametros se mantienen; ComfyUI
reutiliza su cache cuando sigue disponible. No se vuelve a guardar el GLB bruto en los
reintentos. Si sigue fallando, se muestra un aviso de revision manual, no una aprobacion.
Si el LLM no responde o no emite un veredicto, se indica color sin verificar.

El boton Regenerar solo el color permite otro intento de una conversion con textura de
la sesion actual. Tras reiniciar el servidor se pierde el historial de trabajos de esta
interfaz; una regeneracion puede recalcular geometria si ya no esta en cache.

Diagnostico del Funko probado: la semilla de textura 43 produjo la cara oscura tanto con
12 como con 20 pasos. La semilla 44 recupero la familia de color piel con ambos valores.
La forma, reparacion y asignacion de colores se mantuvieron identicas. El defecto aparece
en el campo de textura generado, antes de UV/OBJ; el muestreo sobre la malla reparada lo
acentua. No es un fallo de exportacion ni se arregla aumentando pasos. El nuevo tono de
piel aun difiere de la iluminacion/color exactos de la referencia: revisar antes de cobrar
una reproduccion fiel. Una transferencia alternativa desde puntos originales se probo,
no corrigio el defecto y no se incorporo al flujo.

Pruebas: scripts/pruebas/probar_exportacion_colores.py (limite/materiales/paleta) y
scripts/pruebas/probar_reintentos_color.py (aprobado/reintento/limite/IA ausente).

Correccion 2026-10-06: el OBJ usa materiales por cara y no duplica vertices para
separar colores. Se normaliza la topologia con Manifold y se conserva la etiqueta
de cada cara. Ka=0 evita que Creality 6.3 sume luz ambiental al color Kd.
El Funko de prueba conserva 457.692 caras, cuatro materiales y medidas; el OBJ
serializado tiene cero bordes abiertos y cero aristas con mas de dos caras.
Ocho pruebas de exportacion pasaron. La importacion visual en Creality sigue pendiente.
Los STL no conservan indices: contactos geometricos entre superficies pueden requerir
revision adicional al soldar durante la importacion. No se garantiza su impresion.


### Validacion real del juez y reintentos (2026-10-01)

La API local respondio a texto y vision con el modelo multimodal configurado. El error
previo de conexion fue causado por el proxy del entorno restringido del agente. No era
un fallo del servidor LLM.

Se ejecutaron seis texturas del Funko (semillas 43-48) mediante dos trabajos reales de la
interfaz, incluida Regenerar solo el color. El juez detecto cambios de tono/manchas; ambos
trabajos terminaron con color pendiente de revision tras dos reintentos, sin aprobar la
pieza. La geometria fue identica en los seis grafos y se reutilizo en cache tras el primer
ensayo. El control limpio de un cubo uniforme fue aprobado. Los OBJ de ambos trabajos
conservaron medidas/caras y cuatro materiales/colores exactos. Pasaron 23 pruebas de
regresion. Esto valida el control del pipeline, no la fidelidad de color del Funko: el
resultado aun requiere correccion.

Creality Print 6.3 leyo el OBJ en modo CLI como un objeto con un volumen, pero no se
obtuvo una exportacion 3MF verificable ni una confirmacion visual de asignacion CFS.
La herramienta de captura de ventanas fallo en dos intentos; los proyectos abiertos no
se modificaron. La compatibilidad visual de la nueva exportacion sigue pendiente.


### Detalle y color despues de reparar

En `/exo/pieza`, **Detalle de reparacion** controla la rejilla de solidificacion:
384 es el valor equilibrado; 448 y 512 conservan mas detalle y consumen mas RAM.
TRELLIS sigue generando la forma a 1536; la reparacion es una etapa distinta.
La superficie se reconstruye con marching cubes, en CPU, y dos pasadas de suavizado.
Suavizar no recupera detalles perdidos por una rejilla demasiado gruesa.

El nodo **Transferir color de superficie (Exo)** consulta primero la geometria original
y despues su color. Esto evita recoger colores interiores cuando la reparacion desplaza
la superficie. La reduccion a filamentos asigna cada cara por mayoria de sus vertices,
sin inventar mezclas RGB en las fronteras. La textura usa 24 pasos por defecto.
Una textura incorrecta de origen aun debe regenerarse: la transferencia no la corrige.

El 3MF guarda pintura por filamento; se abre como proyecto en Creality Print.
Un CFS con cuatro bobinas requiere reducir la imagen a cuatro colores: tonos adicionales
de ropa, dientes o accesorios pueden desaparecer. La paleta no garantiza conservar cada
detalle cromatico de la referencia. Revisar las vistas antes de imprimir.


### Recuperar color de una referencia frontal

En `/exo/pieza`, activa **Corregir colores con la foto frontal** cuando el modelo
este alineado con una referencia frontal. La foto se proyecta sobre las caras visibles.
**Completar manchas oscuras de los perfiles** extiende el tono de regiones conectadas
cuando hay evidencia suficiente en la referencia. Los colores ocultos se infieren:
revisa perfiles, cabello, cuello y prendas antes de imprimir. No usar esta opcion
para fotos de perfil, poses diferentes o composiciones con varios sujetos.

Selecciona cuatro filamentos para un CFS. La vista de impresion y el 3MF usan esa
paleta; ropa multicolor y dientes pueden cambiar de tono al reducirla. El juez
conserva la comparacion con la referencia y puede pedir revision de esos cambios.
La correccion frontal no reemplaza una textura correcta para una presentacion
a todo color. La exportacion coloreada incluye automaticamente un 3MF; abrirlo
como proyecto en Creality Print y asignar sus cuatro colores a las bobinas reales.


### Proponer filamentos desde los colores de la imagen

En `/exo/pieza`, selecciona la imagen y el numero de filamentos disponibles; pulsa
**Analizar colores del sujeto**. BiRefNet excluye el fondo y un agrupamiento perceptual
propone los colores predominantes del sujeto. Se muestran las regiones y su porcentaje
del area visible. Cada selector ajusta un color propuesto al filamento que tengas;
la miniatura se actualiza y la paleta se aplica a la conversion y al 3MF.

Los porcentajes no son consumo de filamento. Con pocas plazas se pierden tonos
minoritarios, y la foto no permite conocer colores ocultos. Revisa el recorte y
las regiones; una mascara incorrecta contamina la propuesta. Al cambiar de imagen
se limpia la paleta anterior; al cambiar el numero de filamentos, vuelve a analizar.
El analisis comparte la cola de ComfyUI, pero no genera geometria ni llama al juez.
No se impone una paleta fija para piel, ropa u otros objetos.


### Borrar resultados y referencias locales

En el Estudio, cada tarjeta de imagen tiene **Borrar**. En `/exo/pieza`, la seccion
**Resultados guardados** permite borrar los modelos y vistas desde PC o movil.
Se muestra una lista de archivos, referencias, historial y espacio a liberar antes
de confirmar. El borrado es permanente; elimina los archivos reales, las notas
del Estudio y las entradas relacionadas del historial de ComfyUI.

Se incluyen STL, OBJ/MTL, texturas, GLB, 3MF, vistas y referencias vinculadas al
resultado. Las referencias y salidas compartidas se conservan mientras otro
resultado las utiliza. No se permite borrar durante una generacion, bucle o analisis.
El catalogo persistente conserva la relacion entre cada nueva ejecucion y sus
archivos despues de reiniciar.

Los archivos anteriores al catalogo aparecen identificados como antiguos: solo
se eliminan los archivos cuya asociacion puede comprobarse (por ejemplo, OBJ,
MTL, textura y STL del mismo resultado). No se adivina que GLB o vista pertenece
a una ejecucion antigua sin historial. Sus otros archivos se pueden borrar desde
sus propias entradas. Las copias guardadas como encargos son archivos separados
y se conservan. Las rutas de modelos de IA, configuraciones y codigo quedan
fuera del borrado.
