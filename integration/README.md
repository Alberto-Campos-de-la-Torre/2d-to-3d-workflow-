# Conectar 2D y 3D

La interfaz de intercambio es una imagen PNG/JPEG, no un modelo ni una credencial.

- En instalaciones distintas: exporta la imagen de 2D y cargala como referencia de
  entrada en el flujo 3D de ComfyUI. No se comparten carpetas privadas automaticamente.
- En una misma instalacion: instala `--perfil ambos`; el Estudio conserva **Enviar a
  3D** y `/exo/pieza` permite elegir la imagen. El workflow integrado requiere ambos
  perfiles y los modelos correspondientes. No ejecutes dos copias del plugin con
  los mismos identificadores de nodo en un mismo ComfyUI.

Al incorporar el segundo modulo, detiene ComfyUI y ejecuta el instalador con
`--perfil ambos --actualizar`. Se conserva una copia del plugin anterior en
`user/default/exo_backups/`. Los resultados y modelos no son parte del plugin.
