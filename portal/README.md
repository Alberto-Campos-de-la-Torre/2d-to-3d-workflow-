# Portal multiusuario · cola y trabajador local

Portal independiente de los motores: sesiones, referencias privadas, cola SQLite y
descargas por propietario. El trabajador local construye exclusivamente las plantillas
2D y 3D distribuidas con el proyecto. No se acepta un grafo del navegador.

## Arranque

Desde la raiz del repositorio, con Python 3.11 o posterior:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r portal/requirements.txt
.venv/Scripts/python -m portal crear-usuario administracion --rol administrador
.venv/Scripts/python -m portal servir --local-http
```

La contraseña se solicita sin mostrarla y sin ponerla en argumentos. No hay una
clave predeterminada ni registro abierto. Abre `http://localhost:8090`.
En otros sistemas utiliza el interprete correspondiente del entorno virtual.

En otra terminal, con ComfyUI ya iniciado y sus modelos y nodos instalados:

```powershell
.venv/Scripts/python -m portal trabajador --comfyui <carpeta-ComfyUI>
```

La carpeta indicada debe contener `main.py`, `input/` y `output/`. Se necesita un
ComfyUI que acepte `prompt_id` proporcionado por el cliente (probado con 0.37.1).
Usa los perfiles 2D, 3D o ambos de `instalar.py` segun los trabajos que ofreceras.
Los pesos se instalan por separado; el portal no los descarga ni importa librerias GPU.
En el servidor del portal, `servir --perfil 2d` o `--perfil 3d` limita los flujos
ofrecidos y valida tambien las solicitudes API; el valor predeterminado es `ambos`.

Portal y trabajador deben usar la misma carpeta de datos y ejecutarse en el mismo
equipo que ComfyUI en esta etapa. `EXO_PORTAL_DATA` o `--datos` permiten elegirla;
por defecto se guarda en `.exo-portal` dentro de la carpeta del usuario, fuera de Git.
Los argumentos globales van antes de `crear-usuario`, `servir` o `trabajador`.
`EXO_COMFY_URL` o `--comfy-url` configuran el puerto del motor; solo se admite loopback
y se rechazan credenciales incrustadas en esa URL. No pongas datos reales en los ejemplos.

## Cola, limites y recuperacion

- Una reserva global de GPU para este portal, compartida por los trabajos 2D y 3D.
  Un segundo trabajador no puede utilizar la misma reserva. Si ComfyUI tiene trabajos
  externos, el portal espera a que termine su uso del motor.
  La reserva no controla otras aplicaciones GPU del equipo: comprueba que haya
  memoria y recursos suficientes antes de arrancar el trabajador.
- Hasta dos trabajos pendientes/activos por cuenta, pasos entre 8 y 30 y hasta tres
  intentos por trabajo. Los reintentos tras un fallo son explicitos, no bucles infinitos.
- Estados y etapas persistentes; la interfaz consulta solo los trabajos del usuario.
- Se guarda el UUID de ComfyUI antes de enviar. Tras reiniciar se consulta ese UUID,
  la cola y el historial antes de continuar. No se reenvia un trabajo a ciegas.
- Una cancelacion elimina/interrumpe exclusivamente el UUID del trabajo. No se usa
  interrupcion global. La reserva sigue ocupada hasta confirmar que el motor termino.
- El limite temporal por defecto es de 30 minutos, configurable con `--tiempo-maximo`.
- Si desaparecen tanto el trabajo como su historial despues de un envio incierto,
  se marca **requiere revision** y se bloquea la cola hasta reconciliar o resolverlo.
  No se garantiza ejecucion exactamente una vez ante cualquier fallo del motor.

Para resolver una perdida, detiene primero el trabajador y verifica el motor. La
siguiente accion local exige que no haya trabajos ni historial recuperable:

```powershell
.venv/Scripts/python -m portal resolver-perdida <id-trabajo> --comfyui <carpeta-ComfyUI> --confirmar-perdida
```

El trabajo pasa a fallido y su propietario podra reintentar si queda presupuesto de
intentos. Esta accion no se publica como endpoint para clientes.

## Archivos y privacidad

Las referencias y resultados del portal son privados y tienen identificadores
aleatorios. El propietario se obtiene de la sesion, no del cuerpo de la solicitud.
Administradores pueden gestionar los trabajos explicitamente; operadores y clientes
solo gestionan los suyos. Las imagenes generadas terminadas pueden alimentar un
trabajo 3D del mismo propietario.

Los archivos de ComfyUI se generan temporalmente en `input/exo_portal/` y
`output/exo_portal/`, separados de las galerias generales. Se importan unicamente
salidas del intento correspondiente. Las salidas parciales no se pueden descargar.
Al importar se elimina la metadata de PNG; despues se limpian las copias temporales
y el historial de ese UUID. Los resultados quedan en la carpeta privada del portal.
No se importan grafos, trazas ni errores crudos de ComfyUI al historial del cliente.

El flujo 3D entrega STL, GLB, vista PNG y, con color, 3MF. Omite la malla en bruto
y el horneado UV pesado. La vista puede conservar mas tonos que la paleta de
impresion. Reparacion y cierre no garantizan fidelidad ni imprimibilidad fisica:
revisar colores, grosor, orientacion y laminado antes de fabricar.

Borrar un trabajo elimina sus resultados y referencias sin otros usos. Un resultado
que alimenta otro trabajo impide borrar el origen hasta quitar el dependiente.
Una referencia compartida se conserva hasta su ultimo uso. La migracion desde la
etapa 1 es aditiva y convierte las solicitudes pendientes de motor en pendientes.

## Red

Cookies HttpOnly, SameSite=Strict y Secure por defecto, CSRF y comprobacion de origen.
`--local-http` solo se permite con localhost. El perfil privado de la etapa 3
acepta identidad de Tailscale exclusivamente desde el backend ligado a loopback,
con host/origen HTTPS configurados y lista local de identidades. La identidad no
reemplaza el login ni los roles. X-Forwarded-For no se usa para autorizar.

Ver [piloto privado](../docs/PILOTO_PRIVADO.md) para preparar, publicar y retirar
un puerto Serve independiente sin tocar otros servicios. Funnel sigue desactivado.
La conexion de un trabajador remoto a un VPS requiere otro protocolo privado,
no compartir SQLite.

## Validacion

```powershell
python -m unittest discover -s portal/tests -v
```

Las pruebas usan carpetas temporales y un servidor HTTP de protocolo; no simulan
calidad de inferencia. Tambien se validaron las plantillas 2D, edicion con referencia
y 3D con/sin color mediante el validador real de ComfyUI instalado, sin ejecutar pesos.
No se ejecutaron nuevas inferencias durante esta entrega por la carga GPU existente.
Una prueba de inferencia en tu equipo y la prueba en movil siguen siendo necesarias
antes de abrir el servicio a usuarios remotos.
